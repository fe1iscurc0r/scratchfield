"""
V-01: ELN 实验记录本（Obsidian-based）— /api/eln 路由。

职责：
  - 以 Obsidian vault 中的 Markdown 文件为存储单元，每条实验记录一个 `.md`
  - 记录头部使用 YAML frontmatter（字段 ≥8：日期/课题/状态/目的/药品与用量/
    条件/结果/照片附件/结论/关联文献），正文按模板分节
  - 附件统一存 `experiments/attachments/`，正文以相对路径引用
  - vault 路径可配置：环境变量 `LUMO_VAULT_DIR`，未设置时回退 `~/LumoVault`
  - 与 experimental-design 打通：`POST /api/eln/from-design` 依据因子水平
    生成 2^k 全因子设计矩阵并落为一条 ELN 记录

存储约定：
  - vault/
      experiments/            # 记录文件（<id>.md）
      experiments/attachments/ # 附件（照片/图）
      experiments/_templates/  # 记录模板
      README.md

硬约束：不硬编码绝对路径（vault 走环境变量）；不破坏既有笔记（只写入
experiments/ 子目录，文件以 id 命名避免覆盖）；附件相对路径引用。
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from typing import Annotated

import numpy as np
import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..domain_pack import get_eln_fields
from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/eln", tags=["eln"])
logger = logging.getLogger(__name__)

# 改造前 frontmatter 字段顺序（回归红线）。
#
# 卷162：字段列表由领域包提供 —— 唯一来源是 `domain_pack._LEGACY_ELN_FIELDS`
# 与各包 pack.yaml。本文件不再自持字段常量，避免两处快照漂移。
#
# 顺序语义（务必区分，改造前二者本就不同）：
#   · 后端 frontmatter 顺序：date, topic, status, purpose, reagents,
#     conditions, results, attachments, conclusion, references（见 domain_pack）
#   · 前端 ElnView 表单顺序：topic, date, ...（见 domains/default/pack.yaml）
# `_frontmatter_fields()` 只服务前者，故 default 下必须返回 date 在前的快照。


def _frontmatter_fields(pack: str | None = None) -> list[str]:
    """按领域包解析 frontmatter 字段（顺序敏感）。

    委托 `domain_pack.get_eln_fields()`：default → 改造前顺序快照；
    law 等新领域 → 各自 pack.yaml 声明顺序；未知包 → default 快照。
    该函数在领域包机制挂掉时也不会抛异常（内部逐级回退），保证不回归。
    """
    return get_eln_fields(pack)


_DEFAULT_STATUS = "进行中"


# ============ vault 路径 ============


def get_vault_dir() -> Path:
    """返回 Obsidian vault 根目录。

    优先级：环境变量 `LUMO_VAULT_DIR` > `~/LumoVault`。
    目录不存在则创建（仅创建自身，不递归触碰既有笔记）。
    """
    env = os.environ.get("LUMO_VAULT_DIR")
    if env:
        root = Path(env).expanduser()
    else:
        root = Path.home() / "LumoVault"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _experiments_dir() -> Path:
    d = get_vault_dir() / "experiments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _attachments_dir() -> Path:
    d = _experiments_dir() / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _templates_dir() -> Path:
    d = _experiments_dir() / "_templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_filename(name: str) -> str:
    """清理文件名中的路径分隔符/控制字符，避免路径穿越。"""
    return re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip(" .")


# ============ 模型 ============


class ElnRecordIn(BaseModel):
    """新建/更新记录请求体（除 topic 外均可空，逐步补充）。"""

    date: str = ""
    topic: str = Field(..., min_length=1, max_length=256, description="课题/标题")
    status: str = _DEFAULT_STATUS
    purpose: str = ""
    reagents: str = ""
    conditions: str = ""
    results: str = ""
    attachments: list[str] = Field(default_factory=list, description="附件相对路径列表")
    conclusion: str = ""
    references: str = ""


class ElnRecordOut(BaseModel):
    """记录响应体（含 id 与全部 frontmatter 字段）。"""

    id: str
    date: str
    topic: str
    status: str
    purpose: str
    reagents: str
    conditions: str
    results: str
    attachments: list[str]
    conclusion: str
    references: str


class FromDesignIn(BaseModel):
    """experimental-design 打通：由因子水平生成设计并落为 ELN 记录。"""

    topic: str = Field(..., min_length=1, max_length=256)
    factors: dict[str, tuple[float, float]] = Field(
        ..., description="因子名 -> (low, high) 两水平", min_length=1
    )
    date: str = ""
    status: str = _DEFAULT_STATUS


# ============ frontmatter 读写 ============


def _frontmatter_to_markdown(record: dict) -> str:
    """把记录 dict 序列化为「frontmatter + 分节正文」的 Markdown。"""
    fields = _frontmatter_fields(record.get("_pack"))
    fm = {k: record.get(k, "") for k in fields}
    fm["attachments"] = list(record.get("attachments") or [])
    header = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip() + "\n---\n"
    body = "\n".join(
        [
            f"# {record.get('topic', '')}",
            "",
            "## 目的",
            record.get("purpose", "") or "",
            "",
            "## 药品与用量",
            record.get("reagents", "") or "",
            "",
            "## 条件",
            record.get("conditions", "") or "",
            "",
            "## 结果",
            record.get("results", "") or "",
            "",
            "## 照片附件",
            _attachments_markdown(record.get("attachments") or []),
            "",
            "## 结论",
            record.get("conclusion", "") or "",
            "",
            "## 关联文献",
            record.get("references", "") or "",
            "",
        ]
    )
    return header + body


def _attachments_markdown(attachments: list[str]) -> str:
    if not attachments:
        return ""
    return "\n".join(f"- ![]({a})" for a in attachments)


def _parse_frontmatter(text: str) -> dict:
    """从 Markdown 文本解析 frontmatter（YAML），失败返回空 dict。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning(f"[eln] frontmatter 解析失败: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _record_path(record_id: str) -> Path:
    safe = _sanitize_filename(record_id)
    return _experiments_dir() / f"{safe}.md"


def _read_record(record_id: str) -> dict | None:
    path = _record_path(record_id)
    if not path.exists():
        return None
    record = _parse_frontmatter(path.read_text(encoding="utf-8"))
    record["id"] = path.stem
    return record


def _write_record(record_id: str, record: dict) -> None:
    path = _record_path(record_id)
    record = {**record, "id": record_id}
    path.write_text(_frontmatter_to_markdown(record), encoding="utf-8")


def _record_to_out(record: dict) -> dict:
    out = {"id": record.get("id", "")}
    for f in _frontmatter_fields(record.get("_pack")):
        out[f] = record.get(f, "")
    out["attachments"] = list(record.get("attachments") or [])
    return out


# ============ 端点 ============


@router.get("/records")
async def list_records(
    q: str = Query("", description="按课题/内容模糊搜索"),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """列出全部实验记录（可按关键词模糊搜索课题与各字段内容）。"""
    records: list[dict] = []
    exp_dir = _experiments_dir()
    for path in sorted(exp_dir.glob("*.md")):
        record = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not record:
            continue
        record["id"] = path.stem
        if q:
            haystack = " ".join(
                str(record.get(k, "")) for k in _frontmatter_fields(record.get("_pack"))
            ).lower()
            if q.lower() not in haystack:
                continue
        records.append(_record_to_out(record))
    return {"ok": True, "count": len(records), "records": records}


@router.post("/records", status_code=201)
async def create_record(
    body: ElnRecordIn,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """新建实验记录，返回 id 与完整记录。"""
    record_id = uuid.uuid4().hex[:12]
    record = body.model_dump()
    _write_record(record_id, record)
    logger.info(f"[eln] create id={record_id} topic={body.topic[:32]}")
    return {"ok": True, "record": _record_to_out({**record, "id": record_id})}


@router.get("/records/{record_id}")
async def get_record(
    record_id: str,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """按 id 读取单条记录。"""
    record = _read_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True, "record": _record_to_out(record)}


@router.put("/records/{record_id}")
async def update_record(
    record_id: str,
    body: ElnRecordIn,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """更新记录：覆盖传入字段，保留未传附件时原附件（附件缺失视为清空由前端显式传）。"""
    existing = _read_record(record_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    merged = {**existing, **body.model_dump()}
    _write_record(record_id, merged)
    return {"ok": True, "record": _record_to_out({**merged, "id": record_id})}


@router.get("/records/{record_id}/export")
async def export_record(
    record_id: str,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """导出单条记录为完整 Markdown 报告（单文件，含 frontmatter + 正文）。"""
    record = _read_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    markdown = _frontmatter_to_markdown(record)
    return {
        "ok": True,
        "record_id": record_id,
        "filename": f"{record_id}.md",
        "markdown": markdown,
    }


@router.get("/templates")
async def list_templates(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """列出 `experiments/_templates/` 下的模板文件名。"""
    tpl_dir = _templates_dir()
    templates = [p.name for p in sorted(tpl_dir.glob("*.md"))]
    return {"ok": True, "count": len(templates), "templates": templates}


@router.post("/records/{record_id}/attachments", status_code=201)
async def upload_attachment(
    record_id: str,
    file: UploadFile = File(...),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """上传附件到 `experiments/attachments/`，并把相对路径追加到记录 frontmatter。

    附件文件以 `<record_id>_<原文件名>` 命名，避免跨记录同名覆盖；
    正文引用相对路径 `attachments/<filename>`。
    """
    record = _read_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    safe_name = _sanitize_filename(file.filename or "attachment")
    stored_name = f"{record_id}_{safe_name}"
    dest = _attachments_dir() / stored_name
    content = await file.read()
    dest.write_bytes(content)
    rel = f"attachments/{stored_name}"
    attachments = list(record.get("attachments") or [])
    if rel not in attachments:
        attachments.append(rel)
    record["attachments"] = attachments
    _write_record(record_id, record)
    return {"ok": True, "record_id": record_id, "attachment": rel, "bytes": len(content)}


@router.get("/attachments/{filename}")
async def download_attachment(
    filename: str,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> FileResponse:
    """下载 `experiments/attachments/` 下的附件（V-02 图预览用）。

    仅取 basename 防目录穿越；不存在返回 404。
    """
    safe_name = Path(filename).name
    dest = _attachments_dir() / safe_name
    if not dest.exists():
        raise HTTPException(status_code=404, detail="附件不存在")
    return FileResponse(dest, media_type="image/png")


@router.post("/from-design", status_code=201)
async def from_design(
    body: FromDesignIn,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """experimental-design 打通：按因子水平生成 2^k 全因子设计矩阵并落为 ELN 记录。

    因子为 {名称: (low, high)}，用 numpy 生成编码矩阵并解码到真实单位，
    以 Markdown 表格写入记录「条件」字段，供后续实验逐行执行。
    """
    names = list(body.factors)
    low_high = [body.factors[n] for n in names]
    # 2^k 全因子：-1/+1 编码矩阵
    coded = np.array(np.meshgrid(*[[-1.0, 1.0]] * len(names))).T.reshape(-1, len(names))
    rows = []
    for i in range(coded.shape[0]):
        run = {}
        for j, name in enumerate(names):
            low, high = low_high[j]
            run[name] = (high + low) / 2.0 + coded[i, j] * (high - low) / 2.0
        rows.append(run)

    # Markdown 表格
    header = "| 序号 | " + " | ".join(names) + " |"
    sep = "| --- | " + " | ".join(["---"] * len(names)) + " |"
    lines = [header, sep]
    for i, run in enumerate(rows, start=1):
        cells = " | ".join(_fmt_num(run[n]) for n in names)
        lines.append(f"| {i} | {cells} |")
    table = "\n".join(lines)

    record_id = uuid.uuid4().hex[:12]
    record = {
        "date": body.date,
        "topic": body.topic,
        "status": body.status,
        "purpose": f"全因子实验设计（{len(names)} 因子，{len(rows)} 次运行）",
        "reagents": "",
        "conditions": table,
        "results": "",
        "attachments": [],
        "conclusion": "",
        "references": "experimental-design / 2^k full factorial",
    }
    _write_record(record_id, record)
    logger.info(f"[eln] from-design id={record_id} factors={names} runs={len(rows)}")
    return {
        "ok": True,
        "record": _record_to_out({**record, "id": record_id}),
        "runs": len(rows),
    }


def _fmt_num(v: float) -> str:
    """数值格式化：整数去小数，小数保留 4 位。"""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")
