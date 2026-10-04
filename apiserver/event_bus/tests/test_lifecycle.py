"""生命周期：DisposableList 语义 + emit/parallel/serial/bail dispatch。"""
import asyncio

import pytest

from apiserver.event_bus import DisposableList, InProcessEventBus, Topics

# ---- DisposableList ----

def test_clear_returns_reverse_order():
    dl = DisposableList()
    dl.push("a")
    dl.push("b")
    dl.push("c")
    assert dl.clear() == ["c", "b", "a"]  # 逆序清理
    assert len(dl) == 0


def test_delete_by_value_o1():
    dl = DisposableList()
    dl.push("a")
    dl.push("b")
    assert dl.delete("a") is True
    assert dl.delete("a") is False  # 已删除，幂等
    assert list(dl) == ["b"]


def test_push_disposer_idempotent():
    dl = DisposableList()
    d = dl.push("x")
    d()
    d()  # 第二次 no-op，不抛
    assert len(dl) == 0


def test_unshift_order():
    dl = DisposableList()
    dl.push("tail")
    dl.unshift("head")
    assert list(dl) == ["head", "tail"]


# ---- emit / once ----

def test_emit_multiple_handlers_and_snapshot():
    bus = InProcessEventBus()
    calls = []

    def add_during_dispatch(_):
        calls.append("first")
        bus.on("t", lambda _: calls.append("late"))  # 本轮不应触发

    bus.on("t", add_during_dispatch)
    bus.emit("t", None)
    assert calls == ["first"]
    bus.emit("t", None)
    assert calls == ["first", "first", "late"]


def test_once():
    bus = InProcessEventBus()
    count = 0

    def handler(_):
        nonlocal count
        count += 1

    bus.once("t", handler)
    bus.emit("t", None)
    bus.emit("t", None)
    assert count == 1


# ---- bail / serial ----

def test_bail_stops_on_first_value():
    bus = InProcessEventBus()
    calls = []
    bus.on("q", lambda _: calls.append(1) or None)
    bus.on("q", lambda _: calls.append(2) or "stop")
    bus.on("q", lambda _: calls.append(3) or None)
    assert bus.bail("q", None) == "stop"
    assert calls == [1, 2]


def test_bail_false_and_none_do_not_stop():
    bus = InProcessEventBus()
    bus.on("q", lambda _: False)
    bus.on("q", lambda _: None)
    bus.on("q", lambda _: 0)  # 0 is not None/False → bail
    assert bus.bail("q", None) == 0


def test_bail_no_match_returns_none():
    bus = InProcessEventBus()
    bus.on("q", lambda _: None)
    assert bus.bail("q", None) is None


def test_serial_awaits_in_order_until_bail():
    bus = InProcessEventBus()
    order = []

    async def h1(_):
        await asyncio.sleep(0)
        order.append("h1")
        return None

    async def h2(_):
        order.append("h2")
        return "bail-value"

    async def h3(_):
        order.append("h3")

    bus.on("s", h1)
    bus.on("s", h2)
    bus.on("s", h3)

    result = asyncio.run(bus.serial("s", None))
    assert result == "bail-value"
    assert order == ["h1", "h2"]  # h3 未执行


# ---- parallel ----

def test_parallel_runs_all_and_waits():
    bus = InProcessEventBus()
    done = []

    async def slow(_):
        await asyncio.sleep(0.01)
        done.append("slow")

    async def fast(_):
        done.append("fast")

    bus.on("p", slow)
    bus.on("p", fast)
    asyncio.run(bus.parallel("p", None))
    assert sorted(done) == ["fast", "slow"]  # 全部完成才返回


def test_parallel_aggregates_errors():
    bus = InProcessEventBus()

    async def boom(_):
        raise ValueError("x")

    async def ok(_):
        return None

    bus.on("p", boom)
    bus.on("p", ok)
    with pytest.raises(ExceptionGroup) as exc_info:
        asyncio.run(bus.parallel("p", None))
    assert len(exc_info.value.exceptions) == 1


# ---- internal/dispatch 预通知 ----

def test_internal_dispatch_notification():
    bus = InProcessEventBus()
    seen = []
    bus.on(Topics.INTERNAL_DISPATCH, lambda p: seen.append(p))
    bus.emit("lumo.user.input.received", {"x": 1})
    assert seen == [{"topic": "lumo.user.input.received", "mode": "emit", "args": [{"x": 1}]}]


def test_internal_events_do_not_recurse():
    bus = InProcessEventBus()
    seen = []
    bus.on(Topics.INTERNAL_DISPATCH, lambda p: seen.append(p))
    # 直接 emit internal/dispatch 会正常投递给它的监听者（1 次），
    # 但不会再触发"关于这次分发的预通知"（否则无限递归）
    bus.emit("internal/dispatch", "raw")
    assert seen == ["raw"]
