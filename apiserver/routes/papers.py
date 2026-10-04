"""文献管理器路由（W-02 / SPEC-16 模块 C）。

职责：
- papers 表 CRUD + 搜索（标题/作者/标签/期刊/DOI/笔记）
- DOI 导入（crossref API 拉元数据，网络失败可手动补全）
- 云服论文流水线同步入口：POST /api/papers/import（JSON 数组对齐云服产物）
- 文献 ↔ ELN 关联：papers.linked_experiments（实验 ID 列表）

存储：SQLite（get_data_dir()/papers/papers.db，WAL）。crossref 拉取为纯 stdlib
urllib，超时失败降级为「手动补全」提示，不抛 500。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from system.config import get_data_dir

from ..domain_pack import get_id_fields
from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/papers", tags=["文献"])
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

# JSON 数组字段（DB 存 JSON 文本，出入参为 list）
_JSON_ARRAY_FIELDS = ("authors", "tags", "linked_experiments")

# 导入 item 中「md 内容」的候选键名（云服流水线产物字段对齐）
_MD_CONTENT_KEYS = ("md", "md_content", "content")


class CrossrefError(RuntimeError):
    """crossref 拉取失败（网络/无结果），可降级为手动补全。"""


# ============ 存储 ============


def _db_path() -> str:
    """返回 SQLite 文件路径（数据目录下 papers/papers.db）。"""
    return str(get_data_dir() / "papers" / "papers.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL,
    doi                TEXT,
    authors            TEXT,
    journal            TEXT,
    year               INTEGER,
    tags               TEXT,
    notes              TEXT,
    abstract           TEXT,
    md_path            TEXT,
    linked_experiments TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
"""

# 卷162：领域包声明的主键列（default: doi/arxiv_id；law: flk_id/case_no）。
# 这些列不属于基础 schema，按需 ALTER TABLE 追加，存量库兼容。
_EXTRA_COLUMNS: dict[str, str] = {
    "arxiv_id": "TEXT",
    "flk_id": "TEXT",
    "case_no": "TEXT",
    # 卷163 版权标注机制所需（本卷先建列，保证后续增量可用）
    "source": "TEXT",
    "license_note": "TEXT",
    # 卷164 打标置信度（本卷先建列）
    "tag_confidence": "TEXT",
}

#: 存量数据的默认领域包归属（无 pack 字段的旧记录）。
_LEGACY_PACK = "default"


def _migrate_extra_columns(conn: sqlite3.Connection) -> list[str]:
    """按需给 papers 表补齐扩展列（存量库兼容）。

    只做 ADD COLUMN，不重建表、不迁移数据；已存在的列跳过。
    返回本次实际新增的列名。
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(papers)")}
    added: list[str] = []
    for column, coltype in _EXTRA_COLUMNS.items():
        if column in existing:
            continue
        # 列名/类型均来自本模块常量，非外部输入，无注入风险
        conn.execute(f"ALTER TABLE papers ADD COLUMN {column} {coltype}")
        added.append(column)
    if added:
        logger.info("[papers] 迁移新增列: %s", ", ".join(added))
    return added


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    _migrate_extra_columns(conn)
    return conn


@contextmanager
def _db():
    """打开连接，正常提交，finally 关闭（避免 Windows 下临时目录句柄泄漏）。"""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dump_json(value: Any) -> str | None:
    """list/str → JSON 文本（DB 存储）。"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value]
        value = parsed
    if not isinstance(value, list):
        value = [value]
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: Any) -> Any:
    """JSON 文本 → list/None（出参）。"""
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for f in _JSON_ARRAY_FIELDS:
        d[f] = _load_json(d.get(f))
    return d


# ============ crossref ============


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def fetch_crossref(doi: str, timeout: float = 10.0) -> dict[str, Any]:
    """从 crossref API 拉取单条 DOI 元数据；失败抛 CrossrefError。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(
        url, headers={"User-Agent": "lumo-papers/0.1 (mailto:research@example.com)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001 - 网络失败统一降级为手动补全
        raise CrossrefError(f"crossref 请求失败: {type(e).__name__}: {e}") from e

    msg = data.get("message") or {}
    title = (msg.get("title") or [""])[0] or ""
    journal = (msg.get("container-title") or [""])[0] or None
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in msg.get("author", []) or []
    ]
    authors = [a for a in authors if a] or None
    year = None
    date_parts = (msg.get("published") or {}).get("date-parts") or (msg.get("issued") or {}).get("date-parts")
    if date_parts and date_parts[0]:
        try:
            year = int(date_parts[0][0])
        except (TypeError, ValueError, IndexError):
            year = None
    abstract = _strip_html(msg.get("abstract") or "") or None

    if not title:
        raise CrossrefError(f"crossref 未返回 DOI {doi!r} 的标题（可能不存在）")
    return {
        "title": title,
        "journal": journal,
        "authors": authors,
        "year": year,
        "abstract": abstract,
        "doi": doi,
    }


def _save_md_content(content: str) -> str:
    """把 md 内容落盘到数据目录 papers/md/，返回文件路径（供 md_path 使用）。"""
    base = Path(_db_path()).parent / "md"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"paper_{uuid.uuid4().hex[:8]}.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ============ 请求模型 ============


class PaperCreate(BaseModel):
    title: str
    doi: str | None = None
    authors: list[str] | None = None
    journal: str | None = None
    year: int | None = None
    tags: list[str] | None = None
    notes: str | None = None
    abstract: str | None = None
    md_path: str | None = None
    linked_experiments: list[str] | None = None


class PaperUpdate(BaseModel):
    title: str | None = None
    doi: str | None = None
    authors: list[str] | None = None
    journal: str | None = None
    year: int | None = None
    tags: list[str] | None = None
    notes: str | None = None
    abstract: str | None = None
    md_path: str | None = None
    linked_experiments: list[str] | None = None


class DoiImportRequest(BaseModel):
    doi: str
    tags: list[str] | None = None


class LinkExperimentsRequest(BaseModel):
    experiment_ids: list[str]


# ============ 数据访问 ============


def _insert_paper(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    fields = ["title", "doi", "authors", "journal", "year", "tags", "notes", "abstract", "md_path", "linked_experiments"]
    # 卷162：领域包声明的主键列与来源标注列，存在即写入（缺省 None，不破坏旧调用）。
    for extra in _EXTRA_COLUMNS:
        if extra in data:
            fields.append(extra)
    values = [data.get(f) for f in fields]
    cur = conn.execute(
        f"INSERT INTO papers ({', '.join(fields)}, created_at) VALUES ({', '.join('?' * len(fields))}, ?)",
        (*[_dump_json(v) if f in _JSON_ARRAY_FIELDS else v for f, v in zip(fields, values)], now),
    )
    return _get_paper(conn, int(cur.lastrowid))


def _get_paper(conn: sqlite3.Connection, paper_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _row_to_dict(row) if row else None


def _list_papers(
    conn: sqlite3.Connection,
    *,
    q: str | None,
    tag: str | None,
    year: int | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        like = f"%{q}%"
        clauses.append(
            "(title LIKE ? OR authors LIKE ? OR tags LIKE ? OR journal LIKE ? OR doi LIKE ? OR notes LIKE ?)"
        )
        params.extend([like] * 6)
    if tag:
        clauses.append("tags LIKE ?")
        params.append(f"%{tag}%")
    if year is not None:
        clauses.append("year = ?")
        params.append(year)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = int(conn.execute(f"SELECT COUNT(*) FROM papers{where}", params).fetchone()[0])
    rows = conn.execute(
        f"SELECT * FROM papers{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [_row_to_dict(r) for r in rows], total


# ============ 端点 ============


@router.get("")
async def list_papers(
    q: str | None = Query(None, description="搜索关键词（标题/作者/标签/期刊/DOI/笔记）"),
    tag: str | None = Query(None, description="按标签过滤"),
    year: int | None = Query(None, description="按年份过滤"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """列出文献条目（支持搜索/标签/年份过滤 + 分页）。"""
    with _db() as conn:
        papers, total = _list_papers(conn, q=q, tag=tag, year=year, limit=limit, offset=offset)
    return {"success": True, "papers": papers, "total": total}


@router.post("")
async def create_paper(
    body: PaperCreate,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """手动新建文献条目（title 必填，其余可空）。"""
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title 不能为空")
    with _db() as conn:
        paper = _insert_paper(conn, body.model_dump())
    return {"success": True, "paper": paper}


@router.get("/{paper_id}")
async def get_paper(
    paper_id: int,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """获取单条文献；不存在返回 404。"""
    with _db() as conn:
        paper = _get_paper(conn, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
    return {"success": True, "paper": paper}


@router.put("/{paper_id}")
async def update_paper(
    paper_id: int,
    body: PaperUpdate,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """部分更新文献条目（只更新传入字段）。"""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"success": True, "paper": None}
    with _db() as conn:
        if _get_paper(conn, paper_id) is None:
            raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [
            _dump_json(v) if k in _JSON_ARRAY_FIELDS else v
            for k, v in updates.items()
        ]
        conn.execute(f"UPDATE papers SET {set_clause} WHERE id = ?", (*params, paper_id))
        paper = _get_paper(conn, paper_id)
    return {"success": True, "paper": paper}


@router.delete("/{paper_id}")
async def delete_paper(
    paper_id: int,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """删除文献条目；不存在返回 404。"""
    with _db() as conn:
        if _get_paper(conn, paper_id) is None:
            raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    return {"success": True, "deleted": paper_id}


@router.post("/import")
async def import_papers(
    items: Annotated[list[Any], Body(..., description="云服论文流水线产物 JSON 数组")],
    domain: str = Query("", description="领域包名（卷162）；空则用 default"),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """云服论文流水线同步入口：批量导入 title/doi/abstract/md 内容。

    每条 item 需含 title；坏 item（非对象 / 缺 title）跳过并记入 skipped，
    不使整批失败（坏 JSON 降级）。

    卷162：`domain` 指定领域包后，按该包 `papers.id_fields` 声明的字段
    读写主键（law 包为 flk_id/case_no）。未指定时行为与改造前一致。
    """
    id_fields = get_id_fields(domain or None)
    ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    with _db() as conn:
        for index, item in enumerate(items):
            try:
                if not isinstance(item, dict):
                    raise ValueError("不是对象")
                title = item.get("title")
                if not isinstance(title, str) or not title.strip():
                    raise ValueError("缺少 title 字段")

                md_path = item.get("md_path")
                md_content = next((item.get(k) for k in _MD_CONTENT_KEYS if item.get(k)), None)
                if md_content and not md_path:
                    md_path = _save_md_content(str(md_content))

                data = {
                    "title": title.strip(),
                    "doi": item.get("doi"),
                    "authors": item.get("authors"),
                    "journal": item.get("journal"),
                    "year": item.get("year"),
                    "tags": item.get("tags"),
                    "abstract": item.get("abstract"),
                    "md_path": md_path,
                    "notes": item.get("notes"),
                    "linked_experiments": item.get("linked_experiments"),
                }
                # 按领域包声明的主键字段取值（存量的 doi/arxiv_id 路径不变）
                for idf in id_fields:
                    if idf in _EXTRA_COLUMNS or idf == "doi":
                        if item.get(idf) is not None:
                            data[idf] = item.get(idf)
                # 来源与版权标注（卷163 消费；未提供时按包预设/默认值补齐）
                data.setdefault("source", item.get("source") or "manual")
                if item.get("license_note"):
                    data["license_note"] = item.get("license_note")

                paper = _insert_paper(conn, data)
                ids.append(paper["id"])
            except (ValueError, TypeError) as e:
                skipped.append({"index": index, "error": str(e)})

    return {"success": True, "imported": len(ids), "ids": ids, "skipped": skipped,
            "id_fields": id_fields}


@router.post("/import-doi")
async def import_doi(
    body: DoiImportRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """DOI 导入：crossref 拉元数据并建条目；失败降级为「手动补全」提示。"""
    doi = body.doi.strip()
    if not doi:
        raise HTTPException(status_code=422, detail="doi 不能为空")
    try:
        meta = fetch_crossref(doi)
    except CrossrefError as e:
        logger.warning("[papers] DOI 导入失败（可手动补全）: %s", e)
        return {"success": False, "doi": doi, "error": str(e), "fallback": "manual"}
    with _db() as conn:
        paper = _insert_paper(conn, {**meta, "tags": body.tags})
    return {"success": True, "paper": paper}


@router.put("/{paper_id}/experiments")
async def link_experiments(
    paper_id: int,
    body: LinkExperimentsRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """文献 ↔ ELN 关联：设置该文献引用的实验 ID 列表。"""
    with _db() as conn:
        if _get_paper(conn, paper_id) is None:
            raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
        conn.execute(
            "UPDATE papers SET linked_experiments = ? WHERE id = ?",
            (_dump_json(body.experiment_ids), paper_id),
        )
        paper = _get_paper(conn, paper_id)
    return {"success": True, "paper": paper}
