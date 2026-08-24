"""Lumo EventBus v2 —— 热插拔事件总线。

用法：
    from apiserver.event_bus import get_bus, Topics

    bus = get_bus()                      # 进程级单例
    d = bus.on(Topics.USER_INPUT_RECEIVED, handler)
    bus.emit(Topics.USER_INPUT_RECEIVED, event)
    d()                                  # 卸载，重复调用是 no-op
"""
from .bus import EventBus, EventHandler, InProcessEventBus, WaterfallHandler, is_bailed
from .disposable import Disposable, DisposableList
from .topics import Topics

__all__ = [
    "Disposable",
    "DisposableList",
    "EventBus",
    "EventHandler",
    "InProcessEventBus",
    "Topics",
    "WaterfallHandler",
    "get_bus",
    "is_bailed",
]

_bus: InProcessEventBus | None = None


def get_bus() -> InProcessEventBus:
    """总线单例：整个进程只有一条总线，所有组件共享。"""
    global _bus
    if _bus is None:
        _bus = InProcessEventBus()
    return _bus
