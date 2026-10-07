# [local-patch] 陆墨融合 M3.1 — NEKO → 陆墨反向事件发射器
# 本文件由陆墨融合项目新增，不属于 NEKO 上游源码。
# 详见 .upstream-sha 的 local-patch 记录。
"""NEKO → scratchpad 反向事件发射器（outbox sender）。

职责：
  1) 收集 NEKO 侧 6 类感官事件（user_input / asr_result / tts_start /
     tts_end / user_action / error），异步 POST 到 scratchpad 的
     /api/lumo/event 端点。
  2) 单例 + 单 sender task 串行发送，避免并发写 HTTP。
  3) scratchpad 不可达时静默降级（best-effort），绝不影响 NEKO 主链路。

设计依据（沈遥 M3 反向通道方案）：
  - push 模式，与正向 /api/lumo/speak 对称
  - 事件契约对齐 apiserver/routes/lumo_event.py（event_id + ISO8601 带
    时区时间戳 + discriminated union 六类事件）

铁律遵守：
  - 铁律5（降级优先）：发送失败仅记 debug 日志 + 静默退避，不抛错、不阻塞
  - 铁律7（鉴权）：Bearer $LUMO_PROXY_TOKEN
  - 铁律3（不改上游）：本模块为新增文件；接入点以 import + 一行 emit 挂到
    turn/tts 管线，改动行标 [local-patch]
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ============ 配置 ============

_DEFAULT_EVENT_URL = "http://127.0.0.1:8000/api/lumo/event"  # scratchpad apiserver
_QUEUE_MAXSIZE = 1000          # 沈遥 R3 防 OOM（按计数，M3.1 后续可改按字节）
_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 60.0
_SILENT_AFTER_FAILURES = 5     # 连续失败 N 次后进入静默期，避免刷连接


def _resolve_token() -> str:
    """读取 LUMO_PROXY_TOKEN（优先环境变量，兜底 ConfigManager）。"""
    token = os.environ.get("LUMO_PROXY_TOKEN", "").strip()
    if token:
        return token
    try:
        from utils.config_manager.core_config import ConfigManager
        return str(ConfigManager().get_config("assistApiKeyLumo", "") or "").strip()
    except Exception:
        return ""


def _resolve_url() -> str:
    return os.environ.get("LUMO_EVENT_URL", _DEFAULT_EVENT_URL).strip()


def _new_event_id() -> str:
    # UUIDv7（lumo_event 幂等去重约定）；运行时无 uuid7（<3.13）时 fallback uuid4
    _uuid7 = getattr(uuid, "uuid7", None)
    if _uuid7 is not None:
        return str(_uuid7())
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LumoEventSender:
    """NEKO → 陆墨 反向事件发射器（单例，懒启动 sender task）。

    emit* 方法均为同步（内部 put_nowait），因此同步接入点（如
    ``_enqueue_tts_text_chunk``）与异步接入点（如 ``handle_input_transcript``）
    都能直接调用，无需 await。
    """

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue(
            maxsize=_QUEUE_MAXSIZE
        )
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._backoff = _BACKOFF_INITIAL
        self._consecutive_failures = 0
        self._silent_until = 0.0

    # ---------- 生命周期 ----------

    def _ensure_started(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="lumo-event-sender")

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            await self._send(event)
            self._queue.task_done()

    async def _send(self, event: dict[str, Any]) -> None:
        token = _resolve_token()
        if not token:
            # 未配置共享密钥：静默丢弃（fail-safe，不暴露配置状态）
            logger.debug(
                "[lumo_event_sender] no LUMO_PROXY_TOKEN, drop type=%s",
                event.get("event_type"),
            )
            return

        now = time.monotonic()
        if now < self._silent_until:
            logger.debug(
                "[lumo_event_sender] silent period, drop type=%s",
                event.get("event_type"),
            )
            return

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=3.0, trust_env=False)

        try:
            r = await self._client.post(
                _resolve_url(),
                json=event,
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code < 500:
                # 2xx/4xx 视为链路可达（4xx 由 scratchpad 侧裁决），重置退避
                self._consecutive_failures = 0
                self._backoff = _BACKOFF_INITIAL
            else:
                self._on_failure(event)
        except httpx.HTTPError:
            self._on_failure(event)

    def _on_failure(self, event: dict[str, Any]) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= _SILENT_AFTER_FAILURES:
            self._silent_until = time.monotonic() + self._backoff
            logger.debug(
                "[lumo_event_sender] silent %.1fs (type=%s)",
                self._backoff,
                event.get("event_type"),
            )
            self._backoff = min(self._backoff * 2, _BACKOFF_MAX)
            self._consecutive_failures = 0

    # ---------- 发射 API ----------

    def _emit(
        self,
        event_type: str,
        *,
        session_id: str,
        character: str,
        **fields: Any,
    ) -> None:
        event: dict[str, Any] = {
            "event_id": _new_event_id(),
            "event_type": event_type,
            "timestamp": _now_iso(),
            "neko_session": session_id,
            "character": character,
        }
        event.update(fields)
        try:
            self._queue.put_nowait(event)
            self._ensure_started()
        except asyncio.QueueFull:
            logger.warning(
                "[lumo_event_sender] queue full, drop type=%s", event_type
            )

    def user_input(self, *, session_id, character, text, source="keyboard") -> None:
        self._emit(
            "user_input",
            session_id=session_id,
            character=character,
            text=text,
            source=source,
        )

    def asr_result(
        self, *, session_id, character, text, confidence=1.0, duration_ms=0
    ) -> None:
        self._emit(
            "asr_result",
            session_id=session_id,
            character=character,
            text=text,
            confidence=confidence,
            duration_ms=duration_ms,
        )

    def tts_start(
        self, *, session_id, character, utterance_id, text_len
    ) -> None:
        self._emit(
            "tts_start",
            session_id=session_id,
            character=character,
            utterance_id=utterance_id,
            text_len=text_len,
        )

    def tts_end(
        self, *, session_id, character, utterance_id, interrupted=False
    ) -> None:
        self._emit(
            "tts_end",
            session_id=session_id,
            character=character,
            utterance_id=utterance_id,
            interrupted=interrupted,
        )

    def user_action(self, *, session_id, character, action, detail=None) -> None:
        fields: dict[str, Any] = {"action": action}
        if detail is not None:
            fields["detail"] = detail
        self._emit(
            "user_action",
            session_id=session_id,
            character=character,
            **fields,
        )

    def error(
        self, *, session_id, character, error_type, message, severity="error"
    ) -> None:
        self._emit(
            "error",
            session_id=session_id,
            character=character,
            error_type=error_type,
            message=message,
            severity=severity,
        )


_singleton: Optional[LumoEventSender] = None


def get_sender() -> LumoEventSender:
    global _singleton
    if _singleton is None:
        _singleton = LumoEventSender()
    return _singleton
