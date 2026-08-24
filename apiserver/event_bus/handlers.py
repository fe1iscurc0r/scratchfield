"""消费者订阅逻辑（热插拔侧）。

核心约束：lumo_event.py 只负责 emit，**不 import 任何消费者**。
消费者在这里（或各自模块内）主动订阅总线，返回 disposer 即可卸载。

所有函数都通过参数注入依赖，本模块同样不 import 具体消费者实现，
保持「加订阅者不改核心」的契约。
"""
from __future__ import annotations

from typing import Any, Protocol

from .bus import EventBus
from .disposable import Disposable
from .topics import Topics


class StateStoreLike(Protocol):
    def on_user_input(self, event: Any) -> Any: ...


class ProactiveLike(Protocol):
    def on_user_input(self, event: Any) -> Any: ...


class MemoryLike(Protocol):
    def on_memory_created(self, event: Any) -> Any: ...


def register_state_consumer(bus: EventBus, store: StateStoreLike) -> Disposable:
    """lumo_state：订阅 USER_INPUT_RECEIVED，更新状态快照。"""
    return bus.on(Topics.USER_INPUT_RECEIVED, lambda event: store.on_user_input(event))


def register_proactive_consumer(bus: EventBus, proactive: ProactiveLike) -> Disposable:
    """lumo_proactive：订阅 USER_INPUT_RECEIVED，触发五门决策。

    注：proactive 自身的定时器逻辑独立保留，不经过总线。
    """
    return bus.on(Topics.USER_INPUT_RECEIVED, lambda event: proactive.on_user_input(event))


def register_summer_memory_consumer(bus: EventBus, memory: MemoryLike) -> Disposable:
    """summer_memory：订阅 MEMORY_CREATED，记忆生命周期。"""
    return bus.on(Topics.MEMORY_CREATED, lambda event: memory.on_memory_created(event))
