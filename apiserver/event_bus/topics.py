"""Topics 命名规范（契约 C）—— 整合 caura-memclaw 命名约定。

- 事实：past-participle（已发生）
- 命令：requested / pre-execute（请求干活 / waterfall 门）
- 内部：internal/ 前缀（不触发 internal/dispatch 预通知，防递归）
"""
from __future__ import annotations

from enum import StrEnum


class Topics(StrEnum):
    # ---- 事实（past-participle，已发生） ----
    USER_INPUT_RECEIVED = "lumo.user.input.received"
    ASR_RESULT = "lumo.asr.result"
    TTS_START = "lumo.tts.start"
    TTS_END = "lumo.tts.end"
    MEMORY_CREATED = "lumo.memory.created"
    MEMORY_ARCHIVED = "lumo.memory.archived"
    DECISION_COMPLETED = "lumo.decision.completed"

    # ---- 命令（requested，请求干活） ----
    SPEAK_REQUESTED = "lumo.speak.requested"
    EMOTION_REQUESTED = "lumo.emotion.requested"
    MEMORY_EMBED_REQUESTED = "lumo.memory.embed-requested"
    TOOL_PRE_EXECUTE = "lumo.tool.pre-execute"  # waterfall 门

    # ---- 内部 ----
    INTERNAL_DISPATCH = "internal/dispatch"  # 所有分发的预通知
    #   Payload: {"topic": str, "mode": str, "args": list}

    # ---- 节点心跳（跨节点状态广播） ----
    NODE_HEARTBEAT = "lumo.node.heartbeat"

    # ---- 预留扩展（未来仪器/传感器接入） ----
    RESERVED = "lumo.reserved"
