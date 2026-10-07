"""
陆墨事件接收端点 — NEKO → scratchpad 的反向事件通道

职责：
  1) 接收 NEKO 推送的用户侧事件（user_input/asr_result/tts_start/tts_end/user_action/error）
  2) 时效校验 + event_id 去重（防重放）
  3) 审计日志（只记 type+len，不记全文）
  4) 投递到 apiserver 内部事件总线（M3 阶段仅日志，决策回路接入留 M3.1）

鉴权：
  - 复用 lumo_proxy.require_proxy_token（LUMO_PROXY_TOKEN）
  - 沈遥 R5：bytes 比较已统一

数据流：
  NEKO 事件源 → POST /api/lumo/event → 本端点校验+去重 → 审计日志 → EventBus.emit(USER_INPUT_RECEIVED)

设计依据：沈遥反向通道架构方案（push 模式，与正向 /api/lumo/speak 对称）。
"""
import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .lumo_proxy import require_proxy_token

router = APIRouter(prefix="/api/lumo", tags=["lumo-event"])
logger = logging.getLogger(__name__)


# ============ 时效与去重配置 ============

_EVENT_TTL_SECONDS = 300  # ±5min 容差
_DEDUP_WINDOW_SIZE = 4096  # LRU 容量上限
# 模块级 LRU（进程内）：event_id -> 接收时间戳
_dedup_window: "OrderedDict[str, float]" = OrderedDict()
_dedup_lock = asyncio.Lock()


def _purge_expired(now: float) -> None:
    """淘汰过期 event_id（非线程安全，调用方需持 _dedup_lock）。"""
    expired = [
        eid for eid, ts in _dedup_window.items() if now - ts > _EVENT_TTL_SECONDS
    ]
    for eid in expired:
        _dedup_window.pop(eid, None)


async def _check_dedup(event_id: str, now: float) -> bool:
    """返回 True 表示首次见到（可处理），False 表示重复。"""
    async with _dedup_lock:
        _purge_expired(now)
        if event_id in _dedup_window:
            # LRU touch：重复事件也更新位置，避免被过早淘汰
            _dedup_window.move_to_end(event_id)
            return False
        _dedup_window[event_id] = now
        if len(_dedup_window) >= _DEDUP_WINDOW_SIZE:
            _dedup_window.popitem(last=False)  # 淘汰最旧
        return True


def _parse_timestamp(ts: str) -> float | None:
    """解析 ISO8601 带时区时间戳为 epoch 秒。失败返回 None。"""
    try:
        # 兼容带 Z 后缀的 UTC
        clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            # 沈遥 R5 / No.5：naive timestamp 收紧为拒绝（project_memory 约定：
            # NEKO 发送方稳定后必须收紧为 400 拒绝）。返回 None 触发 400。
            return None
        return dt.timestamp()
    except Exception:
        return None


# ============ 事件模型 ============


class EventBase(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=64, description="UUIDv7，幂等去重")
    event_type: str
    timestamp: str = Field(..., max_length=64, description="ISO8601 带时区")
    neko_session: str = Field(..., min_length=1, max_length=128, description="NEKO 侧会话标识")
    character: str = Field(..., min_length=1, max_length=64, description="当前角色名")


class UserInputEvent(EventBase):
    """用户在 NEKO 聊天框输入文本（未经 LLM）。陆墨感知用户意图的最早信号。"""
    event_type: Literal["user_input"] = "user_input"
    text: str = Field(..., min_length=1, max_length=4096)
    source: Literal["keyboard", "voice", "paste"] = "keyboard"


class AsrResultEvent(EventBase):
    """ASR 识别完成。与 user_input 互为冗余路径——voice 来源时 user_input 可能未触发。"""
    event_type: Literal["asr_result"] = "asr_result"
    text: str = Field(..., min_length=1, max_length=4096)
    confidence: float = Field(..., ge=0.0, le=1.0)
    duration_ms: int = Field(..., ge=0)


class TtsStartEvent(EventBase):
    """TTS 播放开始。只传长度不传全文——正向 speak 通道已有全文留痕。"""
    event_type: Literal["tts_start"] = "tts_start"
    utterance_id: str = Field(..., min_length=1, max_length=64)
    text_len: int = Field(..., ge=0, le=4096)


class TtsEndEvent(EventBase):
    """TTS 播放结束。interrupted=True 表示被打断。"""
    event_type: Literal["tts_end"] = "tts_end"
    utterance_id: str = Field(..., min_length=1, max_length=64)
    interrupted: bool = False


class UserActionEvent(EventBase):
    """用户 UI 操作。高频，可采样。"""
    event_type: Literal["user_action"] = "user_action"
    action: Literal["switch_character", "stop_playback", "pause", "resume", "clear_chat"]
    detail: str | None = Field(None, max_length=256)


class ErrorEvent(EventBase):
    """NEKO 内部错误。不传 stacktrace 全文，只传类型+摘要。供陆墨决策降级。"""
    event_type: Literal["error"] = "error"
    error_type: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=512)
    severity: Literal["warn", "error", "fatal"] = "error"


LumoEvent = Annotated[
    Union[
        UserInputEvent,
        AsrResultEvent,
        TtsStartEvent,
        TtsEndEvent,
        UserActionEvent,
        ErrorEvent,
    ],
    Field(discriminator="event_type"),
]


# ============ 端点 ============


@router.post("/event")
async def receive_event(
    event: LumoEvent,
    _auth: dict = Depends(require_proxy_token),
):
    """接收 NEKO 推送的反向事件。

    处理链：
    1. timestamp 时效校验（±5min，防重放——沈遥 R1）
    2. event_id 去重（LRU 5min，容量 4096——沈遥 R1）
    3. 审计日志（只记 type+len，不记全文——沈遥 R4）
    4. emit 到 EventBus v2（消费者热插拔订阅，本文件不感知具体消费者）

    幂等：重复 event_id 返回 200 + duplicated=True，不抛错。
    """
    now = time.time()

    # 1. 时效校验（防重放）
    ts_epoch = _parse_timestamp(event.timestamp)
    if ts_epoch is None:
        raise HTTPException(status_code=400, detail="invalid timestamp format")
    if abs(now - ts_epoch) > _EVENT_TTL_SECONDS:
        # 铁锚 #6：401 语义不符（ Unauthorized 指鉴权失败），时效问题用 400
        raise HTTPException(status_code=400, detail="event expired or skewed")

    # 2. event_id 去重
    if not await _check_dedup(event.event_id, now):
        logger.debug(
            f"[lumo_event] dup event_id={event.event_id[:8]} type={event.event_type}"
        )
        return {"accepted": True, "event_id": event.event_id, "duplicated": True}

    # 3. 审计日志（不记全文）
    text_len = getattr(event, "text_len", None)
    if text_len is None and hasattr(event, "text"):
        text_len = len(event.text)
    # 沈遥 No.4：character 截断 32 字符 + sanitize 换行，防日志注入
    char_safe = event.character.replace("\n", "\\n").replace("\r", "\\r")[:32]
    # M1 修复：neko_session / event_id 也需 sanitize 换行，防日志注入
    def _sanitize_log_field(s: str, limit: int = 32) -> str:
        return s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")[:limit]
    sid_safe = _sanitize_log_field(event.neko_session, 8)
    eid_safe = _sanitize_log_field(event.event_id, 8)
    # 沈遥 No.8：error 事件额外记录 severity + error_type
    extra = ""
    if event.event_type == "error":
        etype_safe = event.error_type.replace("\n", "\\n").replace("\r", "\\r")
        extra = f" severity={event.severity} error_type={etype_safe}"
    logger.info(
        f"[lumo_event] type={event.event_type} char={char_safe} "
        f"sid={sid_safe} eid={eid_safe} "
        f"text_len={text_len if text_len is not None else '-'}{extra}"
    )

    # 4. 投递到 EventBus v2（热插拔：本文件只 emit，不 import 任何具体消费者）
    #    消费者（lumo_state / lumo_proactive）在 api_server 启动时通过 bus.on()
    #    注册，加新订阅者无需再改本文件（SPEC v2 契约）。
    from apiserver.event_bus import Topics, get_bus
    get_bus().emit(Topics.USER_INPUT_RECEIVED, event)

    return {"accepted": True, "event_id": event.event_id, "duplicated": False}
