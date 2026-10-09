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
from .event_store import EventStore, build_envelope, get_event_store
from .topics import Topics
import threading

__all__ = [
    "Disposable",
    "DisposableList",
    "EventBus",
    "EventHandler",
    "EventStore",
    "InProcessEventBus",
    "Topics",
    "WaterfallHandler",
    "build_envelope",
    "get_bus",
    "get_event_store",
    "is_bailed",
]

_bus: InProcessEventBus | None = None


_bus_lock = threading.Lock()


def get_bus() -> InProcessEventBus:
    """总线单例：整个进程只有一条总线，所有组件共享。"""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = InProcessEventBus()
    return _bus
