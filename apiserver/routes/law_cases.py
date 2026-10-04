"""法学判例导入与打标路由 — /api/domains/law。

卷163 交付（导入）：
- ``POST /api/domains/law/import-cases``：上传本地导出文件（.docx/.pdf/.xlsx），
  规则抽取后批量入 papers（law 包 id_fields: flk_id / case_no）。
- ``POST /api/domains/law/import-flk``：从国家法律法规数据库同步法规（低频、串行）。
- ``GET  /api/domains/law/queue``：查看待补录队列。

卷164 交付（打标层）：
- ``auto_tag`` 参数：导入时顺带自动打标（默认 true）。
- ``POST /api/domains/law/tag-pending``：手动批量为「无标签」判例打标。
- ``POST /api/domains/law/tag-cases``：指定 id 批量打标（供进度条/可取消）。
- ``GET  /api/domains/law/tag-queue``：查看低置信待人工复核队列。
- ``POST /api/domains/law/tag-confirm``：人工确认/改选标签（置信记 1.0(人工)）。
- ``GET  /api/domains/law/von-status``：Von 在线/离线状态（前端徽章用）。

**领域隔离**：本模块只服务 law 包；不给核心 papers 路由加 `if domain == "law"`。
领域包加载器（``apiserver/domain_pack``）保持与具体领域无关。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..domain_pack import get_pack
from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/domains/law", tags=["law-cases"])
logger = logging.getLogger(__name__)

#: 本路由只对 law 包生效。
_LAW_PACK = "law"


def _ensure_law_pack() -> None:
    """确认 law 领域包存在；缺失则 503（提示安装/挂载该包）。"""
    if get_pack(_LAW_PACK) is None:
        raise HTTPException(
            status_code=503,
            detail=f"领域包 {_LAW_PACK!r} 未加载，无法使用判例导入",
        )


def _load_importer():
    """延迟导入判例导入器（避免 law 包缺失时拖垮整个 apiserver 启动）。"""
    try:
        from domains.law.importers import case_import  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise HTTPException(
            status_code=503, detail=f"判例导入器不可用：{exc}"
        ) from exc
    return case_import


def _load_tagging():
    """延迟导入打标管线（Von 不可用/未部署时不影响其他端点）。"""
    try:
        from domains.law.importers import tagging  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"打标管线不可用：{exc}") from exc
    return tagging


# ===========================================================================
# 卷164：打标辅助（本模块内共用，不污染核心 papers 路由）
# ===========================================================================


def _von_status() -> dict[str, Any]:
    """读取 Von 状态；导入失败时返回「禁用」而非抛异常。"""
    try:
        from ..von_client import get_von_client
    except ImportError as exc:  # pragma: no cover
        return {
            "enabled": False, "alive": False, "endpoint": "",
            "breaker": "closed", "message": f"Von 客户端不可用：{exc}",
        }
    try:
        return get_von_client().status()
    except Exception as exc:  # noqa: BLE001 - 状态查询永不炸
        logger.warning("[law-cases] Von 状态查询失败: %s", exc)
        return {
            "enabled": False, "alive": False, "endpoint": "",
            "breaker": "closed", "message": f"Von 状态未知：{exc}",
        }


def _case_from_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """把 papers 行还原成打标所需的判例字段。

    规则抽取的法院/程序/案由在 ``notes``（卷163 约定）；AI 标签在 ``tags``。
    """
    content = paper.get("abstract") or paper.get("notes") or ""
    # 判例正文落盘在 md_path（卷163 未落盘时退回 abstract/notes）
    md_path = paper.get("md_path")
    if md_path:
        try:
            from pathlib import Path

            p = Path(str(md_path))
            if p.is_file():
                content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - 读取失败退回元数据
            logger.warning("[law-cases] 读取判例正文失败 %s: %s", md_path, exc)

    notes = paper.get("notes") or ""
    tags = _as_tag_list(paper.get("tags"))
    return {
        "case_no": paper.get("case_no") or "",
        "court": _note_field(notes, "法院") or paper.get("journal") or "",
        "cause_of_action": _note_field(notes, "案由") or _cause_from_tags(tags),
        "parties": _note_parties(notes),
        "trial_level": _note_field(notes, "程序") or _trial_from_tags(tags),
        "content": content,
    }


def _as_tag_list(tags: Any) -> list[str]:
    """把 tags 归一化成 list[str]（兼容 sqlite 原始 JSON 字符串）。"""
    if isinstance(tags, list):
        return [t for t in tags if isinstance(t, str)]
    if isinstance(tags, str) and tags.strip():
        try:
            parsed = json.loads(tags)
        except (TypeError, ValueError):
            return [tags]
        if isinstance(parsed, list):
            return [t for t in parsed if isinstance(t, str)]
    return []


def _note_field(notes: str, label: str) -> str:
    """从 notes 文本中取 ``label: value`` 行。"""
    prefix = f"{label}:"
    for line in str(notes).splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _note_parties(notes: str) -> list[str]:
    raw = _note_field(notes, "当事人")
    return [p for p in (x.strip() for x in raw.split("、")) if p]


def _tag_keys(question: str) -> str:
    return question


def _cause_from_tags(tags: Any) -> str:
    """从已存 tags 里回读案由（喂料参考用；非打标依据）。"""
    if not isinstance(tags, list):
        return ""
    for t in tags:
        if isinstance(t, str) and t.startswith("案由分类:"):
            return t.split(":", 1)[1]
        if isinstance(t, str) and t.startswith("案由:"):
            return t.split(":", 1)[1]
    return ""


def _trial_from_tags(tags: Any) -> str:
    if not isinstance(tags, list):
        return ""
    for t in tags:
        if isinstance(t, str) and t.startswith("审理程序:"):
            return t.split(":", 1)[1]
    return ""


def _tag_one(conn: Any, paper: dict[str, Any], tagging: Any) -> dict[str, Any]:
    """对单条 paper 打标并写库；返回结果摘要。

    低置信标签不入库，整条判例进 ``_queue/`` 待人工复核。
    """
    from ..von_client import VonError

    fields = _case_from_paper(paper)
    try:
        result = tagging.tag_case(**fields)
    except VonError as exc:
        # Von 离线/熔断：不进队（非数据问题），仅报告跳过
        return {
            "id": paper.get("id"),
            "case_no": fields["case_no"],
            "status": "von_unavailable",
            "error": str(exc),
        }

    accepted = result.accepted_tags()
    tags_list = result.tags_list()
    confidence_json = result.confidence_field()

    if result.low_confidence:
        queued_path = tagging.enqueue_low_confidence(result, filename=fields["case_no"])
        if accepted:
            # 部分标签可入库，低置信部分另进队列
            conn.execute(
                "UPDATE papers SET tags = ?, tag_confidence = ? WHERE id = ?",
                (
                    _dump_json_safe(tags_list),
                    confidence_json,
                    paper.get("id"),
                ),
            )
        return {
            "id": paper.get("id"),
            "case_no": fields["case_no"],
            "status": "low_confidence",
            "tags": tags_list,
            "low_confidence": list(result.low_confidence),
            "queued_path": str(queued_path) if queued_path else None,
            "confidence": confidence_json,
        }

    conn.execute(
        "UPDATE papers SET tags = ?, tag_confidence = ? WHERE id = ?",
        (_dump_json_safe(tags_list), confidence_json, paper.get("id")),
    )
    return {
        "id": paper.get("id"),
        "case_no": fields["case_no"],
        "status": "tagged",
        "tags": tags_list,
        "confidence": confidence_json,
    }


def _dump_json_safe(value: Any) -> str:
    """list → JSON 文本（与 papers._dump_json 同约定）。"""
    import json

    if not isinstance(value, list):
        value = [value] if value is not None else []
    return json.dumps(value, ensure_ascii=False)


@router.post("/import-cases")
async def import_cases(
    files: Annotated[list[UploadFile], File(description="待导入的 .docx/.pdf/.xlsx 文件")],
    source: Annotated[str, Form(description="来源标识（如 pkulaw / wkinfo / manual）")] = "manual",
    license_note: Annotated[str, Form(description="版权说明")] = "",
    auto_tag: Annotated[bool, Form(description="入库后自动 AI 打标（卷164，默认开）")] = True,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """批量导入本地导出判例文件（工单 A1）。

    - 单批上限：≤50 文件 / ≤200MB（超限 413）。
    - 逐文件抽取，**单文件失败不炸整批**：失败项写入 ``_queue/`` 待补录，
      响应里通过 ``queued`` 列表返回。
    - ``.xlsx`` 按一行一案处理（一个文件可产出多条）。
    - ``auto_tag=true``（默认）：入库后自动打标；Von 离线时**静默跳过**
      （不影响导入本身），响应里通过 ``tagging`` 段报告。
    """
    _ensure_law_pack()
    case_import = _load_importer()

    payload: list[tuple[str, bytes]] = []
    for f in files:
        payload.append((f.filename or "unnamed", await f.read()))

    try:
        result = case_import.process_batch(
            payload, source=source or "manual", license_note=license_note
        )
    except ValueError as exc:
        # 批量上限超限
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    # 入库（本路由负责 DB 写；导入器保持 DB 无关、可独立单测）
    from .papers import _db, _insert_paper  # 复用核心 papers 写入

    inserted: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    with _db() as conn:
        for item in result.items:
            if item.ok:
                for case in item.cases:
                    data = case.to_paper_dict(
                        source=source or "manual", license_note=license_note
                    )
                    try:
                        paper = _insert_paper(conn, data)
                        inserted.append({
                            "filename": item.filename,
                            "id": paper["id"],
                            "case_no": case.case_no,
                            "court": case.court,
                            "title": paper.get("title"),
                        })
                    except Exception as exc:  # noqa: BLE001 - 单条失败不炸整批
                        logger.warning("[law-cases] 入库失败 %s: %s", item.filename, exc)
                        queued.append({
                            "filename": item.filename,
                            "case_no": case.case_no,
                            "error": f"入库失败：{exc}",
                        })
            else:
                queued.append({
                    "filename": item.filename,
                    "error": item.error,
                    "queued_path": item.queued_path,
                })

    # 卷164：可选的导入后自动打标（Von 离线则跳过，不影响导入结果）
    tagging_summary: dict[str, Any] = {"enabled": False, "attempted": 0, "skipped": True}
    if auto_tag and inserted:
        tagging_summary = _auto_tag_after_import(inserted)

    return {
        "success": True,
        "domain": _LAW_PACK,
        "total_files": result.total,
        "imported": len(inserted),
        "queued_count": len(queued),
        "inserted": inserted,
        "queued": queued,
        "tagging": tagging_summary,
    }


def _auto_tag_after_import(inserted: list[dict[str, Any]]) -> dict[str, Any]:
    """导入后自动打标（卷164）。Von 离线则报告跳过，绝不抛异常。"""
    status = _von_status()
    if not inserted:
        return {"enabled": status.get("enabled", False), "attempted": 0, "skipped": True}
    if not status.get("alive"):
        return {
            "enabled": bool(status.get("enabled")),
            "attempted": 0,
            "skipped": True,
            "reason": status.get("message") or "Von 未在线",
        }

    tagging = _load_tagging()
    from .papers import _db  # noqa: PLC0415 - 延迟导入避免环

    tagged = low = failed = 0
    with _db() as conn:
        for item in inserted:
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = ?", (item["id"],)
            ).fetchone()
            if paper is None:
                continue
            res = _tag_one(conn, dict(paper), tagging)
            if res["status"] == "tagged":
                tagged += 1
            elif res["status"] == "low_confidence":
                low += 1
            else:
                failed += 1
    return {
        "enabled": True,
        "attempted": len(inserted),
        "tagged": tagged,
        "low_confidence": low,
        "failed": failed,
        "skipped": False,
    }


@router.post("/import-flk")
async def import_flk(
    body: dict[str, Any] | None = None,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """从国家法律法规数据库（flk.npc.gov.cn）同步法规。

    低频礼貌抓取：请求间隔 ≥3s、标准 UA、失败重试 ≤2 次、**严禁并发**。
    请求体可选 ``{"names": ["中华人民共和国民法典", ...]}``；缺省用 pack.yaml
    声明的清单。
    """
    _ensure_law_pack()
    try:
        from domains.law.importers import flk  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"flk 导入器不可用：{exc}") from exc

    names = None
    if isinstance(body, dict):
        raw_names = body.get("names")
        if isinstance(raw_names, list) and raw_names:
            names = [str(n) for n in raw_names]

    summary = await flk.sync_regulations(names)

    # 入库成功抓取的法规
    from .papers import _db, _insert_paper

    inserted: list[dict[str, Any]] = []
    items = summary.get("items") or []
    if items:
        with _db() as conn:
            for it in items:
                try:
                    paper = _insert_paper(conn, it.to_paper_dict())
                    inserted.append({"id": paper["id"], "title": it.title})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[law-cases] 法规入库失败 %s: %s", it.title, exc)
    summary["inserted"] = inserted
    summary["imported"] = len(inserted)
    return summary


@router.get("/queue")
async def get_queue(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """查看判例待补录队列。"""
    _ensure_law_pack()
    case_import = _load_importer()
    items = case_import.list_queue()
    return {"success": True, "count": len(items), "items": items}


# ===========================================================================
# 卷164：打标端点
# ===========================================================================


class TagCasesRequest(BaseModel):
    """指定 id 批量打标请求。"""

    ids: list[int] = Field(default_factory=list, description="要打标的 papers.id 列表")
    limit: int = Field(0, ge=0, le=500, description="不指定 ids 时最多处理条数（0=不限）")
    only_untagged: bool = Field(
        True, description="仅处理无标签判例（False 则全部重打）"
    )


class TagConfirmRequest(BaseModel):
    """人工复核确认请求。"""

    id: int = Field(description="papers.id")
    question: str = Field(description="标签键（如 案由分类）")
    value: Any = Field(description="人工确认/改选的值")


def _is_untagged(paper: dict[str, Any]) -> bool:
    """无任何 AI/人工标签（tags 为空/空串/空数组）。

    兼容两种入参：``_row_to_dict`` 解码后的 list，以及 sqlite 原始行里的
    JSON 字符串（``"[]"`` / ``'["案由分类:合同纠纷"]'``）。
    """
    tags = paper.get("tags")
    if isinstance(tags, str):
        raw = tags.strip()
        if not raw:
            return True
        try:
            tags = json.loads(raw)
        except (TypeError, ValueError):
            # 非 JSON 文本（如历史 ``|`` 拼接串）→ 有内容即视为已打标
            return not raw
    if isinstance(tags, list):
        return not any(isinstance(t, str) and t.strip() for t in tags)
    if isinstance(tags, dict):
        return not tags
    return True


@router.get("/von-status")
async def von_status(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """Von 打标后端在线状态（前端状态徽章）。

    Von 离线**不是错误**：返回 ``alive=false`` 供前端置灰按钮。
    """
    _ensure_law_pack()
    return {"success": True, **_von_status()}


@router.get("/tag-queue")
async def tag_queue(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """查看低置信待人工复核队列（卷164；与判例补录队列同目录、不同前缀）。"""
    _ensure_law_pack()
    tagging = _load_tagging()
    items = tagging.list_low_confidence_queue()
    return {"success": True, "count": len(items), "items": items}


@router.get("/tag-pending-preview")
async def tag_pending_preview(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """预览待打标判例数量（进度条/按钮可用态用）。"""
    _ensure_law_pack()
    from .papers import _db

    with _db() as conn:
        rows = conn.execute("SELECT id, tags FROM papers").fetchall()
    pending = [dict(r)["id"] for r in rows if _is_untagged(dict(r))]
    status = _von_status()
    return {
        "success": True,
        "pending": len(pending),
        "total": len(rows),
        "von": status,
    }


@router.post("/tag-cases")
async def tag_cases(
    body: TagCasesRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """批量打标（卷164）。

    - 指定 ``ids`` 则按 id 打标；否则处理全部（``only_untagged=false`` 时含已打标）。
    - Von 离线：返回 ``von_available=false``，不写库、不报错（前端据此提示）。
    - 低置信项不入库，进 ``_queue/`` 待人工复核。

    可取消：前端按 id 分批调用本端点，取消即停止后续批次。
    """
    _ensure_law_pack()
    status = _von_status()
    if not status.get("alive"):
        return {
            "success": True,
            "von_available": False,
            "message": status.get("message") or "Von 未在线",
            "processed": 0,
            "results": [],
        }

    tagging = _load_tagging()
    from .papers import _db

    with _db() as conn:
        if body.ids:
            marks = ",".join("?" * len(body.ids))
            rows = conn.execute(
                f"SELECT * FROM papers WHERE id IN ({marks})", tuple(body.ids)
            ).fetchall()
        else:
            sql = "SELECT * FROM papers ORDER BY id"
            if body.limit:
                sql += f" LIMIT {int(body.limit)}"
            rows = conn.execute(sql).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            paper = dict(row)
            if body.only_untagged and not _is_untagged(paper):
                continue
            results.append(_tag_one(conn, paper, tagging))

    tagged = sum(1 for r in results if r["status"] == "tagged")
    low = sum(1 for r in results if r["status"] == "low_confidence")
    return {
        "success": True,
        "von_available": True,
        "processed": len(results),
        "tagged": tagged,
        "low_confidence": low,
        "results": results,
    }


@router.post("/tag-pending")
async def tag_pending(
    body: TagCasesRequest | None = None,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """处理全部**无标签**判例（工单 A3 手动批量入口）。

    :func:`tag_cases` 的语义化别名：``only_untagged`` 恒为 true。
    前端进度条按 id 分批调用本端点即可实现「可取消」。
    """
    req = body or TagCasesRequest()
    req.only_untagged = True
    return await tag_cases(req, _auth)


@router.post("/tag-confirm")
async def tag_confirm(
    body: TagConfirmRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """人工复核确认/改选标签（卷164）。

    置信度改记 ``1.0(人工)``，写回 ``papers.tag_confidence``；
    若该标签原本因低置信在队列中，同时从队列移除对应条目。
    """
    _ensure_law_pack()
    tagging = _load_tagging()
    from .papers import _db

    with _db() as conn:
        paper = conn.execute("SELECT * FROM papers WHERE id = ?", (body.id,)).fetchone()
        if paper is None:
            raise HTTPException(status_code=404, detail=f"判例 {body.id} 不存在")
        paper = dict(paper)
        new_conf = tagging.human_confirm(
            paper.get("tag_confidence"), body.question, body.value
        )

        # 同步 papers.tags（把人工确认值写进标签列表）
        tags = paper.get("tags") if isinstance(paper.get("tags"), list) else []
        tags = [t for t in tags if not (
            isinstance(t, str) and t.split(":", 1)[0] == body.question
        )]
        if isinstance(body.value, bool):
            if body.value:
                tags.append(f"{body.question}:是")
        else:
            tags.append(f"{body.question}:{body.value}")
        conn.execute(
            "UPDATE papers SET tags = ?, tag_confidence = ? WHERE id = ?",
            (_dump_json_safe(tags), new_conf, body.id),
        )
        updated = conn.execute(
            "SELECT * FROM papers WHERE id = ?", (body.id,)
        ).fetchone()

    # 从复核队列清除对应条目（尽力而为）
    removed = _remove_queue_entry(tagging, paper.get("case_no"))

    from .papers import _row_to_dict

    return {
        "success": True,
        "id": body.id,
        "question": body.question,
        "value": body.value,
        "confidence": tagging.HUMAN_CONFIRMED_CONFIDENCE,
        "source": tagging.HUMAN_CONFIRMED_SOURCE,
        "queue_entry_removed": removed,
        "paper": _row_to_dict(updated) if updated else None,
    }


def _remove_queue_entry(tagging: Any, case_no: str | None) -> bool:
    """把人工已确认的判例从低置信复核队列移除。"""
    if not case_no:
        return False
    queue_dir = getattr(tagging, "QUEUE_DIR", None)
    if queue_dir is None:
        return False
    import json
    from pathlib import Path

    removed = False
    for p in Path(queue_dir).glob("*__tag__*.json"):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 损坏文件跳过
            continue
        if meta.get("case_no") == case_no:
            try:
                p.unlink()
                removed = True
            except OSError as exc:  # pragma: no cover
                logger.warning("[law-cases] 队列清理失败 %s: %s", p.name, exc)
    return removed
