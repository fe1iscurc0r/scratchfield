"""运行时审计层 —— 所有 agent 调用以 JSONL 追加落盘，供离线分析「冒充 / 注入」模式。

工单 241 §2 任务一第 1 条 + §3 验收 4（**铁律**）：

    审计 log **必须**用 append 每次写一行，**禁止** ``json.dump`` 一次性写整个文件。
    理由：进程被杀（峰谷切换、超时、OOM）时一次性 dump 会让整个历史审计丢失，
    而 append 最坏只坏**末行** —— ``read_events`` 因此显式容忍末行截断。

落点：环境变量 ``AGENT_AUDIT_DIR`` → 否则 ``~/.hermes/audit``（工单原文口径）。
⚠️ 本机（开发机）**没有** ``~/.hermes``（工单 §4 第 3 条也要求 ``.hermes/config.yaml`` 仅读不写），
因此本地 e2e 一律用 ``AGENT_AUDIT_DIR`` 指向临时目录；真实生效位置是云服/沈遥侧。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from mcpserver.agent_governance.errors import E_AUDIT_UNWRITABLE, GovernanceError

ENV_AUDIT_DIR = "AGENT_AUDIT_DIR"
DEFAULT_AUDIT_DIR = "~/.hermes/audit"
AUDIT_FILENAME = "agent_calls.jsonl"

# 事件类型（稳定契约；新增类型请追加，不要改既有字面量）
EVENT_AGENT_CALL = "agent_call"
EVENT_UNAUTHORIZED = "unauthorized_attempt"
EVENT_RE_SIGN = "re_sign"
EVENT_IDENTITY_REJECTED = "identity_rejected"

KNOWN_EVENTS: frozenset[str] = frozenset(
    {EVENT_AGENT_CALL, EVENT_UNAUTHORIZED, EVENT_RE_SIGN, EVENT_IDENTITY_REJECTED}
)


def utc_now_iso(now: datetime | None = None) -> str:
    """UTC ISO-8601 秒级时间戳 —— 单调可回放，能被 trace_audit 的时间戳解析器吃下。"""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def resolve_audit_dir(environ: dict[str, str] | None = None) -> Path:
    """解析审计目录：``AGENT_AUDIT_DIR`` 优先，否则 ``~/.hermes/audit``。"""
    env = os.environ if environ is None else environ
    raw = env.get(ENV_AUDIT_DIR, "").strip()
    return Path(raw).expanduser() if raw else Path(DEFAULT_AUDIT_DIR).expanduser()


def resolve_audit_path(environ: dict[str, str] | None = None) -> Path:
    """审计 JSONL 文件的完整路径。"""
    return resolve_audit_dir(environ) / AUDIT_FILENAME


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """逐行读 JSONL；**跳过**空行与无法解析的行（含被杀的末行截断）。"""
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def read_events(path: Path | str | None = None, *, limit: int | None = None) -> list[dict[str, Any]]:
    """读取审计事件（时间序）。``limit`` 取**最后** N 条，便于看最近调用。"""
    target = Path(path) if path is not None else resolve_audit_path()
    if not target.exists():
        return []
    events = list(iter_jsonl(target))
    return events[-limit:] if limit else events


def count_events(path: Path | str | None = None, *, event: str | None = None) -> int:
    """统计事件条数；``event`` 给定时只数该类事件。"""
    events = read_events(path)
    if event is None:
        return len(events)
    return sum(1 for e in events if e.get("event") == event)


def tail(path: Path | str | None = None, n: int = 10) -> list[dict[str, Any]]:
    """最近 n 条事件。"""
    return read_events(path, limit=n)


def record(
    event: str,
    *,
    agent_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    ok: bool = True,
    code: str | None = None,
    detail: dict[str, Any] | None = None,
    ts: datetime | str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """追加一条审计事件，返回落盘的记录（含 ``path`` / ``line_no`` 便于断言）。

    **append + 每次一行**：``open(..., "a")`` → ``write(line + "\\n")`` → ``flush()``。
    显式 ``newline="\\n"`` 保证 Linux/Windows 都写 LF（Git Data API 交付不走属性归一化）。
    """
    target = Path(path) if path is not None else resolve_audit_path()
    if isinstance(ts, str):
        stamp = ts
    else:
        stamp = utc_now_iso(ts)
    rec: dict[str, Any] = {
        "event": event,
        "timestamp": stamp,
        "agent_id": agent_id or "",
        "provider": provider or "",
        "model": model or "",
        "ok": bool(ok),
        "code": code or "",
    }
    if detail:
        rec["detail"] = detail
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        with open(target, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            line_no = handle.tell()  # 仅用于诊断
    except OSError as exc:
        raise GovernanceError(E_AUDIT_UNWRITABLE, f"审计写入失败: {target}", path=str(target)) from exc
    rec["path"] = str(target)
    rec["bytes_written"] = line_no
    return rec


def record_unauthorized(
    code: str,
    *,
    agent_id: str | None = None,
    provider: str | None = None,
    detail: dict[str, Any] | None = None,
    ts: datetime | str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """记录一次未授权尝试（工单 §2 任务二 场景 C 要求审计里必须出现该事件）。"""
    return record(
        EVENT_UNAUTHORIZED,
        agent_id=agent_id,
        provider=provider,
        ok=False,
        code=code,
        detail=detail,
        ts=ts,
        path=path,
    )
