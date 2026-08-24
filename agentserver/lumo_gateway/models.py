"""lumo_gateway 消息与会话映射数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InboundMessage:
    """归一化入站消息：平台原始事件 → 统一结构（平台无关）。"""

    platform: str  # 平台标识，如 "qq"
    msg_id: str  # 平台消息 ID（去重键）
    user_id: str  # 发送者 ID（私聊场景即对话对端 openid）
    group_id: str | None = None  # 群聊 ID，私聊为 None
    content: str = ""  # 文本内容
    raw: dict[str, Any] = field(default_factory=dict)  # 平台原始事件（排查用）


@dataclass(slots=True)
class OutboundMessage:
    """归一化出站消息：陆墨回复 → 平台出站结构。"""

    platform: str  # 目标平台
    user_id: str  # 回复目标（私聊 openid）
    content: str  # 回复文本（单段 ≤ 2000 字）
    msg_id: str = ""  # 关联入站消息 id（透传给平台做上下文引用）
    group_id: str | None = None  # 群聊回复目标


@dataclass(slots=True)
class SessionMap:
    """会话映射记录：路由键 ↔ 陆墨 session_id。"""

    route_key: str  # {platform}:{user_id}
    session_id: str  # 合法陆墨 session_id（^[a-zA-Z0-9_-]{1,64}$）
    created_at: str  # ISO-8601 UTC
    updated_at: str  # ISO-8601 UTC
