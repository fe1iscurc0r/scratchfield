"""PlatformAdapter 抽象基类：connect / send / on_message 契约。"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable

from ..models import InboundMessage, OutboundMessage

OnMessage = Callable[[InboundMessage], Awaitable[None]]


class PlatformAdapter(abc.ABC):
    """平台适配器契约。

    - connect(): 建立长连（WS 等），失败返回 False
    - send(outbound): 出站回复，失败返回 False（降级纪律，不抛）
    - set_on_message(cb) / emit(msg): 入站事件 → 归一化 InboundMessage → 投递消息队列
    - connected: 布尔状态（供 /health 探活）
    """

    name: str = "base"

    def __init__(self) -> None:
        self.connected = False
        self._on_message: OnMessage | None = None

    def set_on_message(self, cb: OnMessage) -> None:
        self._on_message = cb

    async def emit(self, msg: InboundMessage) -> None:
        """把归一化入站消息投递给回调（消息队列）。"""
        if self._on_message:
            await self._on_message(msg)

    @abc.abstractmethod
    async def connect(self) -> bool: ...

    @abc.abstractmethod
    async def send(self, outbound: OutboundMessage) -> bool: ...

    async def close(self) -> None: ...  # 默认空实现
