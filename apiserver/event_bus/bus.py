"""EventBus ABC + InProcessEventBus —— 还原 Cordis EventsService 的五种 dispatch。

参考：vendor/cordis/src/events.ts
- emit       : 同步分发，不等 async（fire-and-forget）
- parallel   : 并发 await 全部 handler，任一 reject 则聚合抛出
- serial     : 顺序 await，直到一个返回 bail 值
- bail       : 同步版 serial
- waterfall  : 洋葱链，handler(event, next)，不调 next() 即 veto

不还原（SPEC 明确不抄）：fiber 树、Context 代理、依赖注入容器。

W119-01 可观测层（本卷新增，默认零开销）：
- 统计：每 topic dispatch 次数 / 各 mode 计数 / handler 抛错计数 / waterfall veto 计数
- 环形缓冲：最近 N 条事件（topic/mode/timestamp/error 摘要），默认 200
- 可选 hook：`set_hooks(on_dispatch=..., on_error=...)`，不设置则完全不调用
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

from .disposable import Disposable, DisposableList

logger = logging.getLogger(__name__)

# 标准 Topic handler：收到事件对象
EventHandler = Callable[[Any], Any]
# Waterfall handler：收到 (事件对象, next 函数)，调 next() 继续，不调则 veto
WaterfallHandler = Callable[[Any, Callable[[], Any]], Any]

INTERNAL_PREFIX = "internal/"
INTERNAL_DISPATCH = "internal/dispatch"

# W119-01：环形缓冲默认容量（最近事件保留条数）
DEFAULT_RING_SIZE = 200


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
        final: Callable[[], Any] | None = None,
    ) -> Any:
        """洋葱链。handler(event, next)：调 next() 继续，不调则 veto。"""


class InProcessEventBus(EventBus):
    """单进程内存总线。整个进程共享一个实例（见 __init__.py 的 get_bus）。"""

    def __init__(self, *, ring_size: int = DEFAULT_RING_SIZE) -> None:
        self._hooks: Dict[str, DisposableList[EventHandler]] = {}
        # ---- W119-01 可观测层状态 ----
        self._stats_lock = threading.Lock()
        self._started_at = time.time()
        self._dispatch_total = 0
        self._mode_counts: Dict[str, int] = {}
        self._topic_counts: Dict[str, int] = {}
        self._topic_errors: Dict[str, int] = {}
        self._error_total = 0
        self._veto_total = 0
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=max(1, int(ring_size)))
        self._on_dispatch: Callable[[Dict[str, Any]], None] | None = None
        self._on_error: Callable[[Dict[str, Any]], None] | None = None

    # ---- W119-01：可观测接口 ----

    def set_hooks(
        self,
        on_dispatch: Callable[[Dict[str, Any]], None] | None = None,
        on_error: Callable[[Dict[str, Any]], None] | None = None,
    ) -> None:
        """注册可选 hook（默认不设置=零额外调用）。

        on_dispatch(entry)：每次 dispatch 被调用，entry 与环形缓冲条目同构。
        on_error(entry)：每次 handler 抛错被调用（entry 含 error 摘要）。
        hook 自身抛错不影响分发主路径。
        """
        self._on_dispatch = on_dispatch
        self._on_error = on_error

    def _record_dispatch(self, topic: str, mode: str) -> None:
        entry = {"topic": topic, "mode": mode, "timestamp": time.time(), "error": None}
        with self._stats_lock:
            self._dispatch_total += 1
            self._mode_counts[mode] = self._mode_counts.get(mode, 0) + 1
            self._topic_counts[topic] = self._topic_counts.get(topic, 0) + 1
            self._recent.append(entry)
            hook = self._on_dispatch
        if hook is not None:
            try:
                hook(dict(entry))
            except Exception:  # noqa: BLE001 - hook 不得影响分发
                logger.warning("bus on_dispatch hook 抛错", exc_info=True)

    def _record_error(self, topic: str, mode: str, exc: BaseException) -> None:
        summary = f"{type(exc).__name__}: {exc}"[:200]
        entry = {"topic": topic, "mode": mode, "timestamp": time.time(), "error": summary}
        with self._stats_lock:
            self._error_total += 1
            self._topic_errors[topic] = self._topic_errors.get(topic, 0) + 1
            self._recent.append(entry)
            hook = self._on_error
        if hook is not None:
            try:
                hook(dict(entry))
            except Exception:  # noqa: BLE001
                logger.warning("bus on_error hook 抛错", exc_info=True)

    def _record_veto(self) -> None:
        with self._stats_lock:
            self._veto_total += 1

    def snapshot(self) -> Dict[str, Any]:
        """统计快照（JSON 可序列化）：总量 / 各 mode / 各 topic / 错误 / veto。"""
        with self._stats_lock:
            topics = {
                name: {"dispatches": count, "errors": self._topic_errors.get(name, 0)}
                for name, count in sorted(self._topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            }
            return {
                "started_at": self._started_at,
                "uptime_s": round(time.time() - self._started_at, 1),
                "dispatch_total": self._dispatch_total,
                "mode_counts": dict(self._mode_counts),
                "error_total": self._error_total,
                "waterfall_veto_total": self._veto_total,
                "topics": topics,
                "registered_topics": len(self._hooks),
                "ring_size": len(self._recent),
                "ring_capacity": self._recent.maxlen,
            }

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """最近事件（新→旧），最多 limit 条；limit<=0 时按默认 50。"""
        take = max(1, int(limit or 50))
        with self._stats_lock:
            items = list(self._recent)
        return list(reversed(items[-take:]))

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
        """解析本轮 handler 快照，并对非 internal 事件发 internal/dispatch 预通知。

        W119-01：非 internal topic 的每次分发都计入统计与环形缓冲（internal/* 是分发
        预通知自身，计入会双重计数）。
        W119-02：同一次分发同时写入事件日志（append-only JSONL，入队即返回，不阻塞）。
        """
        topic = _topic_key(topic)
        if not topic.startswith(INTERNAL_PREFIX):
            self._notify_dispatch(topic, mode, event)
            self._record_dispatch(topic, mode)
            self._persist_event(topic, mode, event)
        hooks = self._hooks.get(topic)
        return hooks.snapshot() if hooks is not None else []

    def _persist_event(self, topic: str, mode: str, event: object) -> None:
        """W119-02：事件入队落盘；W124-04：先过 surface 的原子验证（非法事件拒收）。

        surface 提供 schema 校验 + 顺序号断档检测；不可用/异常时退回直接落盘（行为不变）。
        """
        try:
            from .event_store import build_envelope, get_event_store

            store = get_event_store()
            if not store.enabled:
                return
            envelope = build_envelope(topic, mode, event, source=getattr(self, "_source", "lumo"))
            try:
                from .surface import get_surface_store

                if get_surface_store().ingest(envelope):
                    return  # 已由 surface 入盘（含验证）
            except Exception:  # noqa: BLE001 - surface 不可用时退回原路径
                logger.debug("surface ingest 失败，退回直接落盘", exc_info=True)
            store.append(envelope)
        except Exception:  # noqa: BLE001 - 持久化不得影响主路径
            logger.debug("event_store append 失败", exc_info=True)

    def _notify_dispatch(self, topic: str, mode: str, event: object) -> None:
        hooks = self._hooks.get(INTERNAL_DISPATCH)
        if hooks is None:
            return
        payload = {"topic": topic, "mode": mode, "args": [event]}
        for cb in hooks.snapshot():
            cb(payload)

    def _fire_and_forget(self, result: Any, topic: str = "") -> None:
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

        def _on_done(task: "asyncio.Task[Any]") -> None:
            exc = task.exception()
            if exc is None:
                return
            self._record_error(topic or "<unknown>", "emit", exc)
            logger.error("emit: 异步 handler 异常", exc_info=exc)

        task = loop.create_task(result)  # type: ignore[arg-type]
        task.add_done_callback(_on_done)

    # ---- 五种 dispatch ----

    def emit(self, topic: str, event: object) -> None:
        topic_key = _topic_key(topic)
        for cb in self._dispatch(topic_key, "emit", event):
            try:
                result = cb(event)
            except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出，行为不变
                self._record_error(topic_key, "emit", exc)
                raise
            self._fire_and_forget(result, topic_key)

    async def parallel(self, topic: str, event: object) -> None:
        topic_key = _topic_key(topic)

        async def run(cb: EventHandler) -> Any:
            result = cb(event)
            if inspect.isawaitable(result):
                return await result
            return result

        # allSettled 语义：全部落定后再聚合抛出（对应 Cordis AggregateError）
        results = await asyncio.gather(
            *(run(cb) for cb in self._dispatch(topic_key, "parallel", event)),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            for exc in errors:
                self._record_error(topic_key, "parallel", exc)
            raise ExceptionGroup(f"parallel({topic}) 有 {len(errors)} 个 handler 失败", errors)

    async def serial(self, topic: str, event: object) -> Any:
        topic_key = _topic_key(topic)
        for cb in self._dispatch(topic_key, "serial", event):
            try:
                result = cb(event)
                if inspect.isawaitable(result):
                    result = await result
            except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
                self._record_error(topic_key, "serial", exc)
                raise
            if is_bailed(result):
                return result
        return None

    def bail(self, topic: str, event: object) -> Any:
        topic_key = _topic_key(topic)
        for cb in self._dispatch(topic_key, "bail", event):
            try:
                result = cb(event)
            except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
                self._record_error(topic_key, "bail", exc)
                raise
            if is_bailed(result):
                return result
        return None

    def waterfall(
        self,
        topic: str,
        event: object,
        final: Callable[[], Any] | None = None,
    ) -> Any:
        topic_key = _topic_key(topic)
        cbs = self._dispatch(topic_key, "waterfall", event)
        inner: Callable[[], Any] = final if final is not None else (lambda: None)

        def _next() -> Any:
            if cbs:
                cb = cbs.pop(0)
                called_next = False

                def _next_inner() -> Any:
                    nonlocal called_next
                    called_next = True
                    return _next()

                try:
                    return cb(event, _next_inner)
                except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
                    self._record_error(topic_key, "waterfall", exc)
                    raise
                finally:
                    # W119-01：handler 未调 next() = veto（洋葱链被拦断），单独计数
                    if not called_next:
                        self._record_veto()
            return inner()

        return _next()
