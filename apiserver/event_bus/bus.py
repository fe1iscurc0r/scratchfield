"""EventBus ABC + InProcessEventBus —— 还原 Cordis EventsService 的五种 dispatch。

参考：vendor/cordis/src/events.ts
- emit       : 同步分发，不等 async（fire-and-forget）
- parallel   : 并发 await 全部 handler，任一 reject 则聚合抛出
- serial     : 顺序 await，直到一个返回 bail 值
- bail       : 同步版 serial
- waterfall  : 洋葱链，handler(event, next)，不调 next() 即 veto

不还原（SPEC 明确不抄）：fiber 树、Context 代理、依赖注入容器。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .disposable import Disposable, DisposableList

logger = logging.getLogger(__name__)

# 标准 Topic handler：收到事件对象
EventHandler = Callable[[Any], Any]
# Waterfall handler：收到 (事件对象, next 函数)，调 next() 继续，不调则 veto
WaterfallHandler = Callable[[Any, Callable[[], Any]], Any]

INTERNAL_PREFIX = "internal/"
INTERNAL_DISPATCH = "internal/dispatch"


def is_bailed(value: Any) -> bool:
    """bail 判定：非 None 且非 False 即停止（对应 Cordis isBailed）。"""
    return value is not None and value is not False


def _topic_key(topic: Any) -> str:
    """归一化 topic：兼容 str / StrEnum / 普通 str-Enum（取 value）。"""
    if isinstance(topic, Enum):
        return str(topic.value)
    return str(topic)


class EventBus(ABC):
    """契约 B：总线接口。"""

    @abstractmethod
    def on(self, topic: str, handler: EventHandler, *, prepend: bool = False) -> Disposable:
        """可逆注册。返回 disposer，调用后该 handler 从总线消失。"""

    @abstractmethod
    def emit(self, topic: str, event: object) -> None:
        """同步分发。所有 handler 无等待并行执行。"""

    @abstractmethod
    async def parallel(self, topic: str, event: object) -> None:
        """并发 await 所有 handler，全部完成后才返回。有任一 reject 则抛。"""

    @abstractmethod
    async def serial(self, topic: str, event: object) -> Any:
        """顺序 await，直到一个返回 bail 值（value is not None and value is not False）。"""

    @abstractmethod
    def bail(self, topic: str, event: object) -> Any:
        """同步 bail。顺序执行 handler，第一个非 None/False 返回值停止。"""

    @abstractmethod
    def waterfall(
        self,
        topic: str,
        event: object,
        final: Optional[Callable[[], Any]] = None,
    ) -> Any:
        """洋葱链。handler(event, next)：调 next() 继续，不调则 veto。"""


class InProcessEventBus(EventBus):
    """单进程内存总线。整个进程共享一个实例（见 __init__.py 的 get_bus）。"""

    def __init__(self) -> None:
        self._hooks: Dict[str, DisposableList[EventHandler]] = {}

    # ---- 注册（契约 A） ----

    def on(self, topic: str, handler: EventHandler, *, prepend: bool = False) -> Disposable:
        topic = _topic_key(topic)
        hooks = self._hooks.get(topic)
        if hooks is None:
            hooks = self._hooks[topic] = DisposableList()

        remove = hooks.unshift(handler) if prepend else hooks.push(handler)
        disposed = False

        def dispose() -> None:
            # 契约 A：同一资源调用两次 disposer，第二次是 no-op
            nonlocal disposed
            if disposed:
                return
            disposed = True
            remove()
            if not len(hooks):
                self._hooks.pop(topic, None)

        return dispose

    def once(self, topic: str, handler: EventHandler, *, prepend: bool = False) -> Disposable:
        """触发一次后自动卸载（还原 Cordis once）。"""
        dispose: Disposable = lambda: None  # 先占位，下方闭包替换

        def wrapper(event: Any) -> Any:
            dispose()
            return handler(event)

        dispose = self.on(topic, wrapper, prepend=prepend)
        return dispose

    # ---- 分发 ----

    def _dispatch(self, topic: str, mode: str, event: object) -> List[EventHandler]:
        """解析本轮 handler 快照，并对非 internal 事件发 internal/dispatch 预通知。"""
        topic = _topic_key(topic)
        if not topic.startswith(INTERNAL_PREFIX):
            self._notify_dispatch(topic, mode, event)
        hooks = self._hooks.get(topic)
        return hooks.snapshot() if hooks is not None else []

    def _notify_dispatch(self, topic: str, mode: str, event: object) -> None:
        hooks = self._hooks.get(INTERNAL_DISPATCH)
        if hooks is None:
            return
        payload = {"topic": topic, "mode": mode, "args": [event]}
        for cb in hooks.snapshot():
            cb(payload)

    @staticmethod
    def _fire_and_forget(result: Any) -> None:
        """emit 下 handler 返回 awaitable 时：有运行中的 loop 则调度，否则关闭并告警。"""
        if not inspect.isawaitable(result):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if inspect.iscoroutine(result):
                result.close()
            logger.warning("emit: handler 返回了 awaitable，但当前无事件循环，已丢弃")
            return
        task = loop.create_task(result)  # type: ignore[arg-type]
        task.add_done_callback(
            lambda t: t.exception() and logger.error("emit: 异步 handler 异常", exc_info=t.exception())
        )

    # ---- 五种 dispatch ----

    def emit(self, topic: str, event: object) -> None:
        for cb in self._dispatch(topic, "emit", event):
            self._fire_and_forget(cb(event))

    async def parallel(self, topic: str, event: object) -> None:
        async def run(cb: EventHandler) -> Any:
            result = cb(event)
            if inspect.isawaitable(result):
                return await result
            return result

        # allSettled 语义：全部落定后再聚合抛出（对应 Cordis AggregateError）
        results = await asyncio.gather(
            *(run(cb) for cb in self._dispatch(topic, "parallel", event)),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise ExceptionGroup(f"parallel({topic}) 有 {len(errors)} 个 handler 失败", errors)

    async def serial(self, topic: str, event: object) -> Any:
        for cb in self._dispatch(topic, "serial", event):
            result = cb(event)
            if inspect.isawaitable(result):
                result = await result
            if is_bailed(result):
                return result
        return None

    def bail(self, topic: str, event: object) -> Any:
        for cb in self._dispatch(topic, "bail", event):
            result = cb(event)
            if is_bailed(result):
                return result
        return None

    def waterfall(
        self,
        topic: str,
        event: object,
        final: Optional[Callable[[], Any]] = None,
    ) -> Any:
        cbs = self._dispatch(topic, "waterfall", event)
        inner: Callable[[], Any] = final if final is not None else (lambda: None)

        def _next() -> Any:
            if cbs:
                cb = cbs.pop(0)
                return cb(event, _next)
            return inner()

        return _next()
