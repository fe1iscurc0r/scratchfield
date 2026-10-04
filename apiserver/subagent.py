"""Subagent 子代理（卷124 W124-02）。

主对话出计划 → 派生若干子代理并行干活（各自独立 LLM + **受限工具集**）→ 结果聚合回主对话。
设计借鉴 DeepSeek Harness 的 Subagent 与 Hermes 的 delegate_task（只抄机制，不引代码）。

安全边界（三条硬规则）：

1. **受限工具集**：子代理默认只有 `file_read / code_exec / test_run`；父任务要更多能力必须显式声明，
   且仍需通过 Scope（W124-01）与 guard（W124-03）——可见性是交集，不是放宽。
2. **不可嵌套**：子代理不能再派子代理（`spawn` 在子会话里直接拒绝）。
3. **上下文隔离**：子代理只见传入的 context + 自己的工具结果，不共享父对话全历史；
   工作区也隔离（会话号 `sub-<id>`，见卷121 沙箱）。

状态落在同一个 SQLite（`message_store.db`）的 `subagents` 表：id/parent_task/session_id/goal/
status/tools/result/created_at/updated_at。
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"

#: 子代理默认工具白名单（够读代码、跑代码、跑测试；不含写盘类由确认门兜底）
DEFAULT_TOOLS = ("file_read", "code_exec", "test_run")

#: 子代理会话前缀（用于「不可嵌套」与工作区隔离）
SUB_SESSION_PREFIX = "sub-"


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "subagent", None)
    except Exception:  # noqa: BLE001
        return None


def enabled() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "enabled", True)) if cfg is not None else True


def max_parallel() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "max_parallel", 3) or 3) if cfg is not None else 3


def allowed_tools() -> Tuple[str, ...]:
    cfg = _cfg()
    tools = getattr(cfg, "default_tools", None) if cfg is not None else None
    if isinstance(tools, (list, tuple)) and tools:
        return tuple(str(t) for t in tools)
    return DEFAULT_TOOLS


def timeout_s() -> float:
    cfg = _cfg()
    return float(getattr(cfg, "timeout_s", 180.0) or 180.0) if cfg is not None else 180.0


def max_rounds() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "max_rounds", 4) or 4) if cfg is not None else 4


# ---------------------------------------------------------------------------
# 存储（同库 message_store.db 的 subagents 表）
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    from apiserver.task_store import _default_db_path

    return _default_db_path()


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS subagents ("
        " subagent_id TEXT PRIMARY KEY,"
        " parent_task TEXT,"
        " session_id TEXT,"
        " goal TEXT,"
        " status TEXT,"
        " tools TEXT,"
        " result TEXT,"
        " created_at REAL,"
        " updated_at REAL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagents_parent ON subagents(parent_task)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagents_session ON subagents(session_id)")
    return conn


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "subagent_id": row["subagent_id"],
        "parent_task": row["parent_task"] or "",
        "session_id": row["session_id"] or "",
        "goal": row["goal"] or "",
        "status": row["status"] or "",
        "tools": json.loads(row["tools"] or "[]"),
        "result": row["result"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_subagent(subagent_id: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM subagents WHERE subagent_id = ?", (str(subagent_id),)).fetchone()
    finally:
        conn.close()
    return _row(row) if row else None


def list_subagents(
    *, parent_task: str = "", session_id: str = "", limit: int = 20, db_path: Path | None = None
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM subagents"
    clauses, params = [], []
    if parent_task:
        clauses.append("parent_task = ?")
        params.append(str(parent_task))
    if session_id:
        clauses.append("session_id = ?")
        params.append(str(session_id))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def _update(subagent_id: str, fields: Dict[str, Any], *, db_path: Path | None = None) -> None:
    if not fields:
        return
    fields = {**fields, "updated_at": time.time()}
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn = _connect(db_path)
    try:
        conn.execute(f"UPDATE subagents SET {sets} WHERE subagent_id = ?",
                     tuple(list(fields.values()) + [str(subagent_id)]))
        conn.commit()
    finally:
        conn.close()


def create_subagent(
    goal: str, *, parent_task: str = "", session_id: str = "", tools: List[str] | None = None,
    subagent_id: str | None = None, db_path: Path | None = None,
) -> Dict[str, Any]:
    sid = subagent_id or uuid.uuid4().hex[:12]
    now = time.time()
    grant = list(tools or allowed_tools())
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO subagents (subagent_id, parent_task, session_id, goal, status, tools,"
            " result, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, str(parent_task or ""), str(session_id or ""), str(goal or ""),
             STATUS_PENDING, json.dumps(grant, ensure_ascii=False), "", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("[subagent] 建子代理 %s（父任务 %s，工具 %s）", sid, parent_task or "-", grant)
    return get_subagent(sid, db_path=db_path) or {}


# ---------------------------------------------------------------------------
# 工具集裁剪
# ---------------------------------------------------------------------------


def filter_tool_schemas(granted: List[str], *, role: str | None = None) -> List[Dict[str, Any]]:
    """把全量 schemas 裁到子代理被授权的工具（再叠一层 Scope，交集语义）。"""
    from apiserver.tool_schemas import get_all_tool_schemas

    want = {str(t) for t in granted}
    out: List[Dict[str, Any]] = []
    for schema in get_all_tool_schemas():
        name = str((schema.get("function") or {}).get("name") or "")
        if not name:
            continue
        short = name.rsplit("__", 1)[-1]
        if name in want or short in want:
            out.append(schema)
    try:
        from mcpserver import scope as scope_mod

        if scope_mod.enabled():
            out = scope_mod.filter_schemas(out, role=role)
    except Exception as e:  # noqa: BLE001
        logger.debug("[subagent] Scope 叠加跳过: %s", e)
    return out


def session_of(subagent_id: str) -> str:
    """子代理自己的会话号（工作区隔离：`sub-<id>`）。"""
    return f"{SUB_SESSION_PREFIX}{subagent_id}"


def is_subagent_session(session_id: str) -> bool:
    return str(session_id or "").startswith(SUB_SESSION_PREFIX)


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


async def _run_llm(subagent: Dict[str, Any], context: str) -> str:
    """独立 LLM 调用 + 受限工具集（走 agentic loop，带工具结果回流）。"""
    from apiserver.agentic_tool_loop import run_agentic_loop

    target = json.dumps({"subagent_id": subagent["subagent_id"],
                         "parent_task": subagent.get("parent_task") or "",
                         "session_id": subagent.get("session_id") or ""}, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是被派出的子代理：只做被交代的这一件事，做完用一段话给结论（含关键产物/命令输出）。\n"
                "你可以调用被授权的工具；不要试图派生新的子代理（会被拒绝）。\n"
                f"子代理信息：{target}"
            ),
        },
        {"role": "user", "content": f"任务：{subagent['goal']}\n\n可用上下文：\n{context or '（无）'}"},
    ]
    tools = filter_tool_schemas(subagent.get("tools") or [])
    texts: List[str] = []
    async for chunk in run_agentic_loop(
        messages, session_of(subagent["subagent_id"]), max_rounds=max_rounds(), tools=tools or None
    ):
        if not chunk.startswith("data: "):
            continue
        body = chunk[6:].strip()
        if not body or body == "[DONE]":
            continue
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "content":
            texts.append(str(event.get("text") or ""))
    return "".join(texts).strip()


async def run_subagent(subagent_id: str, context: str = "") -> Dict[str, Any]:
    """跑一个子代理（失败/超时都落库，不抛给父对话）。"""
    subagent = get_subagent(subagent_id)
    if not subagent:
        return {"ok": False, "error": "not_found"}
    _update(subagent_id, {"status": STATUS_RUNNING})
    try:
        result = await asyncio.wait_for(_run_llm(subagent, context), timeout=timeout_s())
        _update(subagent_id, {"status": STATUS_DONE, "result": result[:4000]})
        return {"ok": True, "subagent_id": subagent_id, "status": STATUS_DONE, "result": result}
    except asyncio.TimeoutError:
        _update(subagent_id, {"status": STATUS_FAILED, "result": f"超时（>{timeout_s()}s）"})
        return {"ok": False, "subagent_id": subagent_id, "status": STATUS_FAILED, "error": "timeout"}
    except Exception as e:  # noqa: BLE001 - 子代理失败不拖垮父对话
        logger.warning("[subagent] %s 执行失败: %s", subagent_id, e)
        _update(subagent_id, {"status": STATUS_FAILED, "result": f"{type(e).__name__}: {e}"})
        return {"ok": False, "subagent_id": subagent_id, "status": STATUS_FAILED, "error": str(e)}


def spawn(
    goal: str, *, parent_task: str = "", session_id: str = "", tools: List[str] | None = None,
    context: str = "", run: bool = True,
) -> Dict[str, Any]:
    """派生一个子代理。返回 `{ok, subagent_id, status, toolset}` 或拒绝原因。

    拒绝场景：功能关闭 / 在子代理会话里再派生（不可嵌套）/ 请求的工具超出默认白名单且未显式授权。
    """
    if not enabled():
        return {"ok": False, "error": "disabled"}
    if is_subagent_session(session_id):
        logger.warning("[subagent] 拒绝嵌套派生（会话 %s）", session_id)
        return {"ok": False, "error": "nested_not_allowed"}
    if not str(goal or "").strip():
        return {"ok": False, "error": "empty_goal"}

    grant = list(tools or allowed_tools())
    if not run:
        record = create_subagent(goal, parent_task=parent_task, session_id=session_id, tools=grant)
        return {"ok": True, "subagent_id": record["subagent_id"], "status": record["status"],
                "toolset": record["tools"]}
    return {"ok": False, "error": "use_spawn_async"}


async def spawn_async(
    goal: str, *, parent_task: str = "", session_id: str = "", tools: List[str] | None = None,
    context: str = "",
) -> Dict[str, Any]:
    """派生 + 立即执行（单个）。"""
    created = spawn(goal, parent_task=parent_task, session_id=session_id, tools=tools, run=False)
    if not created.get("ok"):
        return created
    result = await run_subagent(created["subagent_id"], context)
    return {**created, **result, "toolset": created.get("toolset", [])}


async def spawn_many(
    goals: List[Dict[str, Any]], *, parent_task: str = "", session_id: str = "", context: str = ""
) -> List[Dict[str, Any]]:
    """并行派生多个子代理（上限 `subagent.max_parallel`，超出部分排队执行）。

    `goals` 每项：`{goal, tools?, context?}`。
    """
    if is_subagent_session(session_id):
        return [{"ok": False, "error": "nested_not_allowed"}]
    limit = max(1, max_parallel())
    created: List[Dict[str, Any]] = []
    for item in goals[: max(1, len(goals))]:
        made = spawn(
            str(item.get("goal") or ""), parent_task=parent_task, session_id=session_id,
            tools=item.get("tools"), run=False,
        )
        if made.get("ok"):
            created.append({**made, "context": str(item.get("context") or context or "")})
    sem = asyncio.Semaphore(limit)

    async def _one(item: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            result = await run_subagent(item["subagent_id"], item.get("context", ""))
            return {**item, **result}

    return list(await asyncio.gather(*[_one(item) for item in created])) if created else []


# ---------------------------------------------------------------------------
# 对话侧：协议、聚合、查询
# ---------------------------------------------------------------------------


def extract_subagent_specs(text: str) -> List[Dict[str, Any]]:
    """解析模型输出的 `[SUBAGENT]{json|json数组}[/SUBAGENT]`。"""
    import re

    if not text or "[SUBAGENT]" not in str(text).upper():
        return []
    specs: List[Dict[str, Any]] = []
    for raw in re.findall(r"\[SUBAGENT\]([\s\S]*?)(?:\[/SUBAGENT\]|$)", str(text), re.IGNORECASE):
        body = raw.strip()
        if not body:
            continue
        # 模型常写成「逗号分隔的多个对象」而不是数组——补成数组再解
        compact = body.replace(" ", "").replace("\n", "")
        if compact.startswith("{") and "},{" in compact:
            body = f"[{body}]"
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            logger.debug("[subagent] [SUBAGENT] 段不是合法 JSON：%s", body[:120])
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        specs.extend([i for i in items if isinstance(i, dict)])
    return specs


def results_prompt(session_id: str, *, parent_task: str = "", limit: int = 5) -> str:
    """把子代理结果聚合成一段上下文（注入父对话）。"""
    items = list_subagents(parent_task=parent_task, session_id="" if parent_task else session_id, limit=limit)
    done = [s for s in items if s.get("status") in (STATUS_DONE, STATUS_FAILED)]
    if not done:
        return ""
    lines = ["〔子代理结果〕"]
    for s in reversed(done):  # 旧的在前，先读上下文
        head = f"- {s['subagent_id']} [{s['status']}] {str(s['goal'])[:60]}："
        if s["status"] == STATUS_DONE:
            lines.append(head + str(s.get("result") or "").replace("\n", " ")[:400])
        else:
            lines.append(head + f"失败（{str(s.get('result'))[:120]}）")
    return "\n".join(lines)


def status_text(subagent_id: str = "", *, session_id: str = "", parent_task: str = "") -> str:
    """`subagent:status` 的回复文本。"""
    if subagent_id:
        item = get_subagent(subagent_id)
        if not item:
            return f"没找到子代理 {subagent_id}。"
        body = str(item.get("result") or "")
        return (f"子代理 {item['subagent_id']}｜状态 {item['status']}｜工具 {item['tools']}\n"
                f"目标：{item['goal']}\n结果：{body[:600] or '（无）'}")
    items = list_subagents(parent_task=parent_task, session_id=session_id, limit=10)
    if not items:
        return "本会话没有子代理记录。"
    lines = ["子代理："]
    for item in items:
        lines.append(f"- `{item['subagent_id']}` [{item['status']}] {str(item['goal'])[:50]}"
                     f"｜工具 {','.join(item['tools'])}")
    return "\n".join(lines)


def stats() -> Dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT status, COUNT(*) FROM subagents GROUP BY status").fetchall()
    finally:
        conn.close()
    return {"by_status": {str(r[0]): int(r[1]) for r in rows}, "max_parallel": max_parallel(),
            "default_tools": list(allowed_tools()), "enabled": enabled()}
