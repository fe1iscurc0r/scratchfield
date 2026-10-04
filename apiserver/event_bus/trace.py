"""W120-01：全链路 Trace —— contextvar 上下文 + span 记录 + 落盘 + 查询。

目标：一次用户请求从 Lumo 入口 → 工具调用 → 总线事件 → mcpserver 任务事件，全程带同一 `trace_id`，
可用一个查询端点看完整链路（时间线 / 模块 / 工具 / 耗时 / 错误）。

- 上下文：`contextvars`（asyncio 任务内自动传播；跨进程/跨总线靠显式透传 trace_id）
- span：进出时间 + 耗时 + 父 span + 属性 + 错误摘要；`trace_span()` 上下文管理器与 `@traced` 装饰器
- 落盘：`<user_data>/event_store/traces.jsonl`（复用 W119-02 的 EventStore：后台线程写、缓冲、轮转）
- 查询：`get_trace(trace_id)`（先查当前内存上下文，再回放落盘）；端点 `GET /debug/trace/<id>`
- 与总线联动：W119-02 的信封 `trace_id` 缺省取当前 trace（事件自动挂到链路上）

用途边界：trace 仅作调试/审计观察，不承载业务状态。
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import inspect
import itertools
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

TRACES_FILENAME = "traces.jsonl"
#: span 单调序号（排序用；Windows time.time() 粒度太粗，不能拿来定序）
_SEQ = itertools.count(1)
_MAX_SPANS_PER_TRACE = 500


@dataclass
class Span:
    """一次操作的时间片。

    排序/耗时都**不能靠 `time.time()`**：Windows 上它的粒度约 15.6ms，连续 span 会拿到
    完全相同的时间戳（实测两个嵌套 span start 相同 → 按 start 排序排不出父子顺序）。
    因此：`seq`（单调递增序号）用于排序，`perf_counter`（高精度）用于算耗时，
    `start` 只作墙钟展示。
    """

    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    seq: int = field(default_factory=lambda: next(_SEQ))
    parent_id: str | None = None
    start: float = field(default_factory=time.time)
    end: float | None = None
    duration_ms: float | None = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def finish(self) -> None:
        """结束 span：记录墙钟结束时间与高精度耗时。"""
        self.end = time.time()
        self.duration_ms = round((time.perf_counter() - self._t0) * 1000, 3)

    def to_dict(self, trace_id: str) -> Dict[str, Any]:
        return {
            "trace_id": trace_id,
            "span_id": self.span_id,
            "seq": self.seq,
            "parent_id": self.parent_id,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "error": self.error,
        }


@dataclass
class TraceContext:
    """一条链路：trace_id + 已记录 span。"""

    trace_id: str
    spans: List[Span] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


_current: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "lumo_trace_context", default=None
)
_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("lumo_trace_span_stack", default=())

_store_lock = threading.Lock()
_trace_store: Any = None
#: 已完成链路的内存尾部缓存（便于刚结束的请求立刻可查；落盘查询兜底）
_recent: "Dict[str, Dict[str, Any]]" = {}
_recent_order: List[str] = []
_RECENT_LIMIT = 50


# ---------------------------------------------------------------------------
# 落盘（复用事件存储：后台线程写 + 缓冲 + 轮转）
# ---------------------------------------------------------------------------


def _default_trace_path() -> Path:
    from system.config import get_data_dir

    return Path(get_data_dir()) / "event_store" / TRACES_FILENAME


def get_trace_store() -> Any:
    """trace 落盘用的 EventStore 单例（同目录风格，独立文件 traces.jsonl）。"""
    global _trace_store
    if _trace_store is None:
        with _store_lock:
            if _trace_store is None:
                from .event_store import EventStore

                try:
                    from system.config import get_config

                    cfg = get_config().bus.event_store
                    _trace_store = EventStore(
                        _default_trace_path(),
                        enabled=getattr(cfg, "enabled", True),
                        buffer_lines=getattr(cfg, "buffer_lines", 200),
                        max_bytes=getattr(cfg, "max_bytes", 16 * 1024 * 1024),
                        keep_files=getattr(cfg, "keep_files", 5),
                    )
                except Exception as e:  # noqa: BLE001
                    logger.debug("[trace] 读取配置失败，用默认值: %s", e)
                    _trace_store = EventStore(_default_trace_path())
    return _trace_store


def reset_trace_store_for_tests(store: Any = None) -> None:
    global _trace_store
    with _store_lock:
        if _trace_store is not None and _trace_store is not store:
            _trace_store.close(timeout=1.0)
        _trace_store = store


def flush_traces(timeout: float = 3.0) -> bool:
    store = get_trace_store()
    return bool(store.flush(timeout=timeout)) if store is not None else True


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------


def start_trace(trace_id: str | None = None, **metadata: Any) -> contextvars.Token:
    """开启一条链路（返回 token，配合 end_trace 还原）。"""
    ctx = TraceContext(trace_id=str(trace_id) if trace_id else uuid.uuid4().hex, metadata=dict(metadata))
    token = _current.set(ctx)
    _stack.set(())
    return token


def end_trace(token: contextvars.Token | None = None) -> str | None:
    """结束链路：把内存上下文归档进近期缓存（便于立刻查询）。"""
    ctx = _current.get()
    trace_id = ctx.trace_id if ctx is not None else None
    if ctx is not None:
        _archive(ctx)
    try:
        if token is not None:
            _current.reset(token)
        else:
            _current.set(None)
    except (ValueError, LookupError):
        _current.set(None)
    return trace_id


def current_trace() -> TraceContext | None:
    return _current.get()


def get_or_create_trace_id() -> str:
    """当前链路 id；没有上下文时创建一个（并保留在上下文中，供本次调用内复用）。"""
    ctx = _current.get()
    if ctx is not None:
        return ctx.trace_id
    ctx = TraceContext(trace_id=uuid.uuid4().hex, metadata={"implicit": True})
    _current.set(ctx)
    return ctx.trace_id


def current_trace_id() -> str | None:
    ctx = _current.get()
    return ctx.trace_id if ctx is not None else None


def record_span(span: Span) -> None:
    """记录一个 span（内存 + 落盘）。无上下文时静默跳过。"""
    ctx = _current.get()
    if ctx is None:
        return
    if len(ctx.spans) >= _MAX_SPANS_PER_TRACE:
        return
    ctx.spans.append(span)
    try:
        store = get_trace_store()
        if store is not None and store.enabled:
            store.append(span.to_dict(ctx.trace_id))
    except Exception:  # noqa: BLE001 - trace 落盘不得影响主路径
        logger.debug("[trace] span 落盘失败", exc_info=True)


@contextlib.contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[Span]:
    """with trace_span("tool:exec", tool="exec") as span: ...（异常也会记录并原样抛出）"""
    stack = _stack.get()
    parent_id = stack[-1] if stack else None
    span = Span(name=str(name), parent_id=parent_id, attributes=dict(attributes))
    token = _stack.set(stack + (span.span_id,))
    try:
        yield span
    except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
        span.error = f"{type(exc).__name__}: {exc}"[:200]
        raise
    finally:
        span.finish()
        _stack.reset(token)
        record_span(span)


def traced(name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：同步/异步函数都自动包一层 span。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        span_name = name or getattr(func, "__qualname__", func.__name__)

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with trace_span(span_name):
                    return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name):
                return func(*args, **kwargs)

        return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# 归档与查询
# ---------------------------------------------------------------------------


def _archive(ctx: TraceContext) -> None:
    """把完成的链路放进近期缓存（有界；span 按开始时间排序，父在前子在后）。"""
    if not ctx.spans:
        return
    ordered = sorted(ctx.spans, key=lambda s: s.seq)
    record = {
        "trace_id": ctx.trace_id,
        "started_at": ctx.started_at,
        "metadata": ctx.metadata,
        "span_count": len(ordered),
        "spans": [span.to_dict(ctx.trace_id) for span in ordered],
    }
    with _store_lock:
        _recent[ctx.trace_id] = record
        _recent_order.append(ctx.trace_id)
        while len(_recent_order) > _RECENT_LIMIT:
            oldest = _recent_order.pop(0)
            _recent.pop(oldest, None)


def get_trace(trace_id: str) -> Dict[str, Any] | None:
    """查询链路：先查当前上下文，再查近期缓存，最后回放落盘。"""
    want = str(trace_id or "").strip()
    if not want:
        return None

    ctx = _current.get()
    if ctx is not None and ctx.trace_id == want:
        return {
            "trace_id": want,
            "started_at": ctx.started_at,
            "metadata": ctx.metadata,
            "span_count": len(ctx.spans),
            "spans": [span.to_dict(want) for span in sorted(ctx.spans, key=lambda s: s.seq)],
            "source": "active",
        }

    with _store_lock:
        cached = _recent.get(want)
    if cached is not None:
        return {**cached, "source": "recent"}

    store = get_trace_store()
    if store is None:
        return None
    spans: List[Dict[str, Any]] = []
    try:
        for item in store.replay():
            if not isinstance(item, dict):
                continue
            if str(item.get("trace_id") or "") != want:
                continue
            spans.append(item)
    except Exception:  # noqa: BLE001
        logger.debug("[trace] 回放落盘失败", exc_info=True)
        return None
    if not spans:
        return None
    spans.sort(key=lambda s: s.get("seq") or 0)
    return {
        "trace_id": want,
        "started_at": spans[0].get("start"),
        "metadata": {},
        "span_count": len(spans),
        "spans": spans,
        "source": "store",
    }


def trace_stats() -> Dict[str, Any]:
    with _store_lock:
        return {
            "recent_traces": len(_recent),
            "recent_limit": _RECENT_LIMIT,
            "active_trace_id": current_trace_id(),
        }


def reset_for_tests() -> None:
    """测试用：清上下文与近期缓存（不动落盘文件）。"""
    _current.set(None)
    _stack.set(())
    with _store_lock:
        _recent.clear()
        _recent_order.clear()
