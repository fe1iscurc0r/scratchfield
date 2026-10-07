"""任务级工具调用链摘要 —— Paired Replay 审计的证据链（工单205 任务一）。

背景（威胁模型 §一.3）：授权边界通常在**会话级**设定，但决策发生在**任务级**；
缺任务级证据链时事后无法回答"这一步是谁授权的"。

本模块**只落盘不分析**：
    - 数据源：`mcpserver/telemetry.py` 的 `tool_calls` 表（ts / tool / agent / caller /
      duration_ms / status / error_kind）——**复用现成埋点，不新增采集路径**；
    - 落盘：`<store_dir>/<caller>.jsonl`（append-only，每行一个任务的摘要）；
    - 落盘目录默认 `<telemetry db 同级>/tool_chain_audit/`（可环境变量覆盖）。

调用方（agentserver 会话收尾）只需一句：
    from mcpserver.tool_chain_audit import audit_and_write
    audit_and_write(caller=session_id)
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_STORE_ENV = "LUMO_TOOL_CHAIN_AUDIT_DIR"


def _telemetry_db() -> Path:
    """复用 telemetry 的库路径（默认同址）。"""
    try:
        from mcpserver import telemetry as _t

        return Path(_t._default_db_path())
    except Exception:  # noqa: BLE001 - telemetry 不可用时回退到 data_dir 约定
        return Path.home() / ".lumo" / "tool_calls.db"


def default_store_dir() -> Path:
    env = os.environ.get(DEFAULT_STORE_ENV, "").strip()
    if env:
        return Path(env)
    return _telemetry_db().parent / "tool_chain_audit"


def build_chain_summary(caller: str, *, db_path: str | Path | None = None,
                        since_ts: float | None = None,
                        limit: int = 2000) -> dict[str, Any]:
    """按 caller 聚合工具调用序列 → 摘要（**只读**，不改任何表）。

    返回：
        {caller, step_count, tools: [去重有序], steps: [{ts, tool, status, error_kind, ms}],
         errors: [...], started_at, ended_at, duration_s}
    """
    key = str(caller or "").strip()
    if not key:
        return {"caller": "", "step_count": 0, "tools": [], "steps": [], "errors": [],
                "empty_reason": "empty_caller"}
    db = Path(db_path) if db_path is not None else _telemetry_db()
    if not db.exists():
        return {"caller": key, "step_count": 0, "tools": [], "steps": [], "errors": [],
                "empty_reason": "no_telemetry_db", "db": str(db)}
    sql = ("SELECT ts, tool, agent, status, error_kind, duration_ms FROM tool_calls "
           "WHERE caller = ?")
    params: list[Any] = [key]
    if since_ts is not None:
        sql += " AND ts >= ?"
        params.append(float(since_ts))
    sql += " ORDER BY ts ASC LIMIT ?"
    params.append(int(limit))
    try:
        with sqlite3.connect(str(db), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
    except Exception as exc:  # noqa: BLE001 - 审计不得影响主流程
        return {"caller": key, "step_count": 0, "tools": [], "steps": [], "errors": [],
                "empty_reason": f"query_failed: {type(exc).__name__}: {exc}"}

    steps: list[dict[str, Any]] = []
    tools: list[str] = []
    errors: list[dict[str, Any]] = []
    agents: set[str] = set()
    for r in rows:
        tool = str(r["tool"])
        steps.append({"ts": r["ts"], "tool": tool, "status": r["status"],
                      "error_kind": r["error_kind"] or "", "ms": r["duration_ms"]})
        if tool not in tools:
            tools.append(tool)                    # 去重但保持首次出现顺序（= 调用链形状）
        if str(r["status"]) not in ("ok", ""):
            errors.append({"ts": r["ts"], "tool": tool, "status": r["status"],
                           "error_kind": r["error_kind"] or ""})
        if r["agent"]:
            agents.add(str(r["agent"]))

    started = steps[0]["ts"] if steps else None
    ended = steps[-1]["ts"] if steps else None
    return {
        "caller": key,
        "step_count": len(steps),
        "tools": tools,
        "tool_set_size": len(tools),
        "agents": sorted(agents),
        "steps": steps,
        "errors": errors,
        "started_at": started,
        "ended_at": ended,
        "duration_s": round((ended - started), 3) if (started and ended) else None,
    }


def write_summary(summary: dict[str, Any], store_dir: str | Path | None = None) -> Path:
    """把摘要追加到 `<store_dir>/<caller>.jsonl`（append-only，返回落盘路径）。"""
    root = Path(store_dir) if store_dir is not None else default_store_dir()
    root.mkdir(parents=True, exist_ok=True)
    caller = str(summary.get("caller") or "unknown")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in caller)[:80] or "unknown"
    path = root / f"{safe}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return path


def summarize_steps(caller: str, steps: list[dict[str, Any]] | list[str], *,
                    agents: list[str] | None = None) -> dict[str, Any]:
    """**显式序列入口**：调用方直接传入本任务实际调用过的工具序列 → 摘要。

    ⚠️ 为什么需要它（2026-10-07 实测）：telemetry 的 `caller` 字段当前被填成
    **tool_name**（`mcpserver/mcp_manager.py:113`），**不是任务/会话维度** ——
    按 `build_chain_summary(caller=...)` 聚合会得到"每个 caller 只有一个工具"，
    无法还原任务级链。因此任务级审计有两个可选路径：

    1. **本函数（推荐，立即可用）**：调用方在任务收尾时把它**自己记录**的工具序列传进来；
    2. 或待 `caller` 语义修正为会话/任务 ID 后，改用 `build_chain_summary()`。

    steps 支持两种形态：`["tool_a", "tool_b"]` 或 `[{"tool":..., "ts":..., "status":...}]`。
    """
    key = str(caller or "").strip()
    norm: list[dict[str, Any]] = []
    for s in steps or []:
        if isinstance(s, str):
            norm.append({"ts": None, "tool": s, "status": "ok", "error_kind": "", "ms": None})
        elif isinstance(s, dict):
            norm.append({"ts": s.get("ts"), "tool": str(s.get("tool") or ""),
                         "status": str(s.get("status") or "ok"),
                         "error_kind": str(s.get("error_kind") or ""), "ms": s.get("ms")})
    tools: list[str] = []
    errors: list[dict[str, Any]] = []
    for st in norm:
        if st["tool"] and st["tool"] not in tools:
            tools.append(st["tool"])
        if st["status"] not in ("ok", ""):
            errors.append({"ts": st["ts"], "tool": st["tool"], "status": st["status"],
                           "error_kind": st["error_kind"]})
    ts_vals = [s["ts"] for s in norm if isinstance(s["ts"], (int, float))]
    return {
        "caller": key,
        "step_count": len(norm),
        "tools": tools,
        "tool_set_size": len(tools),
        "agents": sorted(agents or []),
        "steps": norm,
        "errors": errors,
        "started_at": min(ts_vals) if ts_vals else None,
        "ended_at": max(ts_vals) if ts_vals else None,
        "duration_s": round(max(ts_vals) - min(ts_vals), 3) if len(ts_vals) > 1 else None,
        "source": "explicit_steps",
    }


def audit_and_write(caller: str, *, db_path: str | Path | None = None,
                    store_dir: str | Path | None = None,
                    since_ts: float | None = None) -> dict[str, Any]:
    """一步到位：聚合 + 落盘。**任何异常都不向调用方抛**（审计是旁路）。"""
    try:
        summary = build_chain_summary(caller, db_path=db_path, since_ts=since_ts)
        if summary.get("step_count"):
            summary["written_to"] = str(write_summary(summary, store_dir))
        return summary
    except Exception as exc:  # noqa: BLE001
        return {"caller": str(caller or ""), "step_count": 0, "error":
                f"audit_failed: {type(exc).__name__}: {exc}"}
