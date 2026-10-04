from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from apiserver import naga_auth
from system.config import IS_PACKAGED, VERSION, get_config, get_data_dir

logger = logging.getLogger(__name__)

TELEMETRY_DIR = get_data_dir() / "telemetry"
TELEMETRY_QUEUE_PATH = TELEMETRY_DIR / "events.ndjson"
TELEMETRY_STATE_PATH = TELEMETRY_DIR / "state.json"

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "app_secret",
    "authorization",
    "captcha_answer",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "set_cookie",
    "token",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return lowered in _SENSITIVE_KEYS or any(flag in lowered for flag in _SENSITIVE_KEYS)


def _sanitize_string(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""

    lowered = stripped.lower()
    if lowered.startswith("bearer "):
        return "<redacted>"
    if stripped.startswith("sk-") or stripped.startswith("sess-"):
        return "<redacted>"
    if stripped.count(".") == 2 and len(stripped) > 24:
        return "<redacted>"
    if os.path.isabs(stripped):
        return f"<path:{Path(stripped).name}>"
    if "@" in stripped and " " not in stripped:
        local, _, domain = stripped.partition("@")
        if local and domain:
            return f"<email:{domain}>"
    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urlparse(stripped)
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    compact = " ".join(stripped.split())
    if len(compact) > 400:
        compact = compact[:399] + "…"
    return compact


def _sanitize_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if depth > 6:
        return "<max-depth>"

    if key and _is_sensitive_key(key):
        return "<redacted>"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _sanitize_string(value)

    if isinstance(value, Path):
        return f"<path:{value.name}>"

    if isinstance(value, BaseException):
        raw = str(value)
        return {
            "type": value.__class__.__name__,
            "message": _sanitize_string(raw),
            "hash": _hash_text(raw),
        }

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            safe_key = str(raw_key)[:80]
            sanitized[safe_key] = _sanitize_value(raw_value, key=safe_key, depth=depth + 1)
        return sanitized

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if len(items) > 32:
            items = items[:32] + ["<truncated>"]
        return [_sanitize_value(item, depth=depth + 1) for item in items]

    return _sanitize_string(str(value))


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _rewrite_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


class TelemetryManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._install_id: str | None = None
        self._last_upload_at: str | None = None
        self._last_error: str | None = None
        self._last_upload_count = 0
        self._dropped_events = 0
        self._auth_blocked_token_hash: str | None = None
        self._auth_blocked_reason: str | None = None

    def _is_auth_error(self, detail: str, status_code: int | None = None) -> bool:
        lowered = (detail or "").strip().lower()
        if status_code in {401, 403}:
            return True
        return any(
            marker in lowered
            for marker in (
                "unauthorized",
                "forbidden",
                "invalid token",
                "token expired",
                "expired token",
                "令牌无效",
                "令牌无效或已过期",
                "已过期",
            )
        )

    async def start(self) -> None:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        await self._ensure_state()
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._run_flush_loop(), name="naga-telemetry-flush")

    async def shutdown(self) -> None:
        task = self._flush_task
        self._flush_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            await self.flush_once(force=True)
        except Exception as exc:
            logger.debug("[Telemetry] shutdown flush failed: %s", exc)

    async def _ensure_state(self) -> None:
        def _load_or_create() -> str:
            TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
            if TELEMETRY_STATE_PATH.exists():
                try:
                    state = json.loads(TELEMETRY_STATE_PATH.read_text(encoding="utf-8"))
                    install_id = str(state.get("install_id") or "").strip()
                    if install_id:
                        return install_id
                except Exception:
                    pass
            install_id = uuid.uuid4().hex
            TELEMETRY_STATE_PATH.write_text(
                json.dumps(
                    {
                        "install_id": install_id,
                        "created_at": _utc_now_iso(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return install_id

        self._install_id = await asyncio.to_thread(_load_or_create)

    async def track(
        self,
        event: str,
        props: dict[str, Any] | None = None,
        *,
        source: str = "apiserver",
        trace_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        cfg = get_config().telemetry
        if not cfg.enabled:
            return
        if self._install_id is None:
            await self._ensure_state()

        payload = {
            "event_id": uuid.uuid4().hex,
            "event": event.strip()[:120] or "unknown_event",
            "ts": _utc_now_iso(),
            "source": source,
            "trace_id": trace_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "install_id": self._install_id,
            "app_version": VERSION,
            "platform": sys.platform,
            "packaged": IS_PACKAGED,
            "props": _sanitize_value(props or {}),
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"

        async with self._lock:
            await asyncio.to_thread(_append_line, TELEMETRY_QUEUE_PATH, line)
            await self._trim_queue_locked(max_events=cfg.max_queue_events, max_bytes=cfg.max_queue_bytes)

    async def _trim_queue_locked(self, *, max_events: int, max_bytes: int) -> None:
        try:
            stat = await asyncio.to_thread(TELEMETRY_QUEUE_PATH.stat)
        except FileNotFoundError:
            return

        lines = await asyncio.to_thread(_read_lines, TELEMETRY_QUEUE_PATH)
        if stat.st_size <= max_bytes and len(lines) <= max_events:
            return
        kept_lines = lines[-max_events:]
        while kept_lines and len("\n".join(kept_lines).encode("utf-8")) > max_bytes:
            kept_lines = kept_lines[1:]
        dropped = max(0, len(lines) - len(kept_lines))
        self._dropped_events += dropped
        await asyncio.to_thread(_rewrite_lines, TELEMETRY_QUEUE_PATH, kept_lines)

    def _resolve_upload_url(self) -> str:
        cfg = get_config()
        upload_url = cfg.telemetry.upload_url.strip()
        if upload_url:
            return upload_url
        return ""

    async def flush_once(self, *, force: bool = False) -> dict[str, Any]:
        cfg = get_config().telemetry
        if not cfg.enabled:
            return {"status": "disabled"}
        if not cfg.upload_enabled and not force:
            return {"status": "upload_disabled"}

        async with self._lock:
            lines = await asyncio.to_thread(_read_lines, TELEMETRY_QUEUE_PATH)
            if not lines:
                return {"status": "empty"}

            batch_lines = lines[: cfg.batch_size]
            remainder = lines[cfg.batch_size :]

        events: list[dict[str, Any]] = []
        for line in batch_lines:
            try:
                events.append(json.loads(line))
            except Exception:
                continue

        if not events:
            async with self._lock:
                await asyncio.to_thread(_rewrite_lines, TELEMETRY_QUEUE_PATH, remainder)
            return {"status": "empty_batch"}

        body = {
            "client": {
                "install_id": self._install_id,
                "app_version": VERSION,
                "platform": sys.platform,
                "packaged": IS_PACKAGED,
            },
            "sent_at": _utc_now_iso(),
            "events": events,
        }
        # W119-01：每次 flush 附带一份总线统计摘要（不逐事件打点，防噪）
        try:
            from apiserver.event_bus import get_bus

            snap = get_bus().snapshot()
            body["bus"] = {
                "uptime_s": snap.get("uptime_s"),
                "dispatch_total": snap.get("dispatch_total"),
                "error_total": snap.get("error_total"),
                "waterfall_veto_total": snap.get("waterfall_veto_total"),
                "mode_counts": snap.get("mode_counts"),
                "top_topics": list((snap.get("topics") or {}).keys())[:10],
            }
        except Exception as e:  # noqa: BLE001 - 遥测不得因总线不可用而失败
            logger.debug("[telemetry] 总线快照读取失败，跳过 bus 摘要: %s", e)
        headers = {"Content-Type": "application/json"}
        token = naga_auth.get_access_token()
        token_hash = _hash_text(token) if token else None
        if token_hash and self._auth_blocked_token_hash == token_hash and not force:
            self._last_error = self._auth_blocked_reason or "telemetry auth blocked"
            return {
                "status": "auth_blocked",
                "error": self._last_error,
                "count": len(events),
            }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif not force:
            self._last_error = "telemetry skipped: no access token"
            return {"status": "no_auth", "count": len(events)}

        upload_url = self._resolve_upload_url()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(cfg.upload_timeout_seconds),
                trust_env=False,
            ) as client:
                response = await client.post(upload_url, json=body, headers=headers)
            response_json: dict[str, Any] | None = None
            try:
                response_json = response.json()
            except Exception:
                response_json = None

            if response.status_code >= 400:
                detail = (
                    (response_json or {}).get("error")
                    or (response_json or {}).get("detail")
                    or response.text.strip()
                    or f"HTTP {response.status_code}"
                )
                if self._is_auth_error(detail, response.status_code):
                    self._auth_blocked_token_hash = token_hash
                    self._auth_blocked_reason = detail
                raise RuntimeError(detail)
            if isinstance(response_json, dict) and response_json.get("ok") is False:
                detail = str(response_json.get("error") or response_json.get("message") or "telemetry rejected")
                if self._is_auth_error(detail):
                    self._auth_blocked_token_hash = token_hash
                    self._auth_blocked_reason = detail
                raise RuntimeError(detail)

            async with self._lock:
                await asyncio.to_thread(_rewrite_lines, TELEMETRY_QUEUE_PATH, remainder)

            self._auth_blocked_token_hash = None
            self._auth_blocked_reason = None
            self._last_error = None
            self._last_upload_at = _utc_now_iso()
            self._last_upload_count = len(events)
            return {
                "status": "uploaded",
                "count": len(events),
                "remaining": len(remainder),
            }
        except Exception as exc:
            self._last_error = str(exc)
            if self._is_auth_error(str(exc)):
                self._auth_blocked_token_hash = token_hash
                self._auth_blocked_reason = str(exc)
                logger.debug("[Telemetry] upload paused until token refresh: %s", exc)
            else:
                logger.debug("[Telemetry] upload failed: %s", exc)
            return {"status": "error", "error": str(exc), "count": len(events)}

    async def _run_flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(max(5, int(get_config().telemetry.flush_interval_seconds)))
                await self.flush_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Telemetry] flush loop stopped: %s", exc)

    async def get_status(self) -> dict[str, Any]:
        if self._install_id is None:
            await self._ensure_state()
        async with self._lock:
            lines = await asyncio.to_thread(_read_lines, TELEMETRY_QUEUE_PATH)
        cfg = get_config().telemetry
        return {
            "enabled": cfg.enabled,
            "upload_enabled": cfg.upload_enabled,
            "upload_url": self._resolve_upload_url(),
            "install_id": self._install_id,
            "queued_events": len(lines),
            "last_upload_at": self._last_upload_at,
            "last_upload_count": self._last_upload_count,
            "last_error": self._last_error,
            "dropped_events": self._dropped_events,
            "auth_blocked": bool(self._auth_blocked_token_hash),
            "auth_blocked_reason": self._auth_blocked_reason,
        }


_telemetry_manager: TelemetryManager | None = None


def get_telemetry_manager() -> TelemetryManager:
    global _telemetry_manager
    if _telemetry_manager is None:
        _telemetry_manager = TelemetryManager()
    return _telemetry_manager


def emit_telemetry(
    event: str,
    props: dict[str, Any] | None = None,
    *,
    source: str = "apiserver",
    trace_id: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        get_telemetry_manager().track(
            event,
            props,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            agent_id=agent_id,
        )
    )


# ---------------------------------------------------------------------------
# W120-04：关键指标计数器（内存、O(1)、不阻塞主路径）
# ---------------------------------------------------------------------------


def _sanitize_metric_text(text: str, *, limit: int = 200) -> str:
    """指标输出脱敏 + 截断：复用 apiserver.metric_sanitize（含按值特征的 token 掩码）。

    单独成模块的原因：本文件原有的 _sanitize_string 只按**键名**脱敏，反查/参数里裸奔的
    token 值会漏出指标输出（实测 sk-xxx 原样出现）。
    """
    from apiserver.metric_sanitize import sanitize_metric_text

    return sanitize_metric_text(str(text or ""), limit=limit)


class MetricsCounters:
    """极简指标登记：请求量/工具调用/延迟与失败率 + 最近错误 TopN（脱敏）。

    只存内存（重启清零，README 注明）；每次登记是 O(1) 的整数/浮点累加，不写盘、不阻塞。
    """

    def __init__(self, *, error_window: int = 20) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._latency_sum_ms: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._errors: deque[dict[str, Any]] = deque(maxlen=max(1, int(error_window)))
        self._started_at = time.time()

    # ---- 登记 ----

    def record_request(self, *, path: str, method: str, status: int, duration_ms: float, error: str = "") -> None:
        label = f"{method} {path}"
        with self._lock:
            self._counters["request_total"] += 1
            self._counters[f"request_status_{int(status) // 100}xx"] += 1
            self._latency_sum_ms["request"] += float(duration_ms)
            self._latency_count["request"] += 1
            if status >= 400 and error:
                self._errors.append(
                    {
                        "kind": "http",
                        "path": _sanitize_metric_text(str(path)),
                        "status": int(status),
                        "error": _sanitize_metric_text(str(error)),
                        "ts": time.time(),
                    }
                )

    def record_tool(self, *, tool: str, ok: bool, duration_ms: float, error: str = "") -> None:
        name = str(tool or "unknown")[:80]
        with self._lock:
            self._counters["tool_total"] += 1
            self._counters["tool_ok" if ok else "tool_failed"] += 1
            self._latency_sum_ms["tool"] += float(duration_ms)
            self._latency_count["tool"] += 1
            if not ok:
                self._errors.append(
                    {
                        "kind": "tool",
                        "tool": _sanitize_metric_text(name, limit=80),
                        "error": _sanitize_metric_text(str(error)),
                        "ts": time.time(),
                    }
                )

    # ---- 汇总 ----

    @staticmethod
    def _rate(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    def snapshot(self, *, bus: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            latency_sum = dict(self._latency_sum_ms)
            latency_count = dict(self._latency_count)
            errors = list(self._errors)[-10:]
        request_total = counters.get("request_total", 0)
        tool_total = counters.get("tool_total", 0)
        tool_failed = counters.get("tool_failed", 0)
        return {
            "uptime_s": round(time.time() - self._started_at, 1),
            "requests": {
                "total": request_total,
                "status_2xx": counters.get("request_status_2xx", 0),
                "status_4xx": counters.get("request_status_4xx", 0),
                "status_5xx": counters.get("request_status_5xx", 0),
                "avg_latency_ms": round(latency_sum.get("request", 0.0) / latency_count["request"], 2)
                if latency_count.get("request")
                else 0.0,
            },
            "tools": {
                "total": tool_total,
                "ok": counters.get("tool_ok", 0),
                "failed": tool_failed,
                "failure_rate": self._rate(tool_failed, tool_total),
                "avg_latency_ms": round(latency_sum.get("tool", 0.0) / latency_count["tool"], 2)
                if latency_count.get("tool")
                else 0.0,
            },
            "bus": {
                "dispatch_total": (bus or {}).get("dispatch_total", 0),
                "error_total": (bus or {}).get("error_total", 0),
                "waterfall_veto_total": (bus or {}).get("waterfall_veto_total", 0),
                "mode_counts": (bus or {}).get("mode_counts", {}),
                "top_topics": list(((bus or {}).get("topics") or {}).keys())[:10],
            },
            "recent_errors": [_sanitize_value(e) for e in errors],
            "note": "计数只存内存（重启清零）；字段已脱敏，错误摘要截断 200 字符",
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latency_sum_ms.clear()
            self._latency_count.clear()
            self._errors.clear()
            self._started_at = time.time()


METRICS = MetricsCounters()


def record_request_metric(*, path: str, method: str, status: int, duration_ms: float, error: str = "") -> None:
    """供 HTTP 中间件调用（O(1)、不抛）。"""
    try:
        METRICS.record_request(path=path, method=method, status=status, duration_ms=duration_ms, error=error)
    except Exception:  # noqa: BLE001 - 指标登记不得影响请求
        logger.debug("[telemetry] 请求指标登记失败", exc_info=True)


def record_tool_metric(*, tool: str, ok: bool, duration_ms: float, error: str = "") -> None:
    """供工具回路调用（O(1)、不抛）。"""
    try:
        METRICS.record_tool(tool=tool, ok=ok, duration_ms=duration_ms, error=error)
    except Exception:  # noqa: BLE001
        logger.debug("[telemetry] 工具指标登记失败", exc_info=True)
