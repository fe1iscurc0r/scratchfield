"""W119-01 验收：总线可观测层（统计 / hook / 环形缓冲 / veto 计数）。

对应工单验收：
- GET /debug/dump/bus 返回统计含 topic 级计数
- handler 抛异常后 on_error hook 收到且快照计数 +1
- 环形缓冲可用（触发 ≥200 事件后仍返回最近 200）
"""
import asyncio

import pytest

from apiserver.event_bus import InProcessEventBus, Topics


def _collect(bus: InProcessEventBus):
    dispatched: list[dict] = []
    errored: list[dict] = []
    bus.set_hooks(dispatched.append, errored.append)
    return dispatched, errored


def test_stats_count_per_topic_and_mode():
    """快照按 topic / mode 计数，total 累加；internal/* 不计入（防双重计数）。"""
    bus = InProcessEventBus()
    bus.on("a", lambda e: None)
    bus.on("a", lambda e: None)
    bus.on("b", lambda e: None)

    bus.emit("a", None)
    bus.emit("a", None)
    bus.emit("b", None)
    asyncio.run(bus.parallel("b", None))
    asyncio.run(bus.serial("a", None))

    snap = bus.snapshot()
    assert snap["dispatch_total"] == 5
    assert snap["mode_counts"] == {"emit": 3, "parallel": 1, "serial": 1}
    assert snap["topics"]["a"]["dispatches"] == 3
    assert snap["topics"]["b"]["dispatches"] == 2
    assert snap["error_total"] == 0
    # internal/dispatch 预通知不计入统计
    assert all(not name.startswith("internal/") for name in snap["topics"])


def test_error_hook_and_counter():
    """handler 抛错：on_error 收到摘要、error_total/ topic_errors +1，异常仍向上抛。"""
    bus = InProcessEventBus()
    dispatched, errored = _collect(bus)

    def boom(_event):
        raise RuntimeError("handler 炸了")

    bus.on("bad", boom)
    with pytest.raises(RuntimeError):
        bus.emit("bad", None)

    assert bus.snapshot()["error_total"] == 1
    assert bus.snapshot()["topics"]["bad"]["errors"] == 1
    assert len(errored) == 1
    assert "RuntimeError" in errored[0]["error"]
    # dispatch 钩子仍然收到（先 dispatch 后抛错）
    assert dispatched and dispatched[-1]["topic"] == "bad"

    # parallel 聚合抛出同样计数
    bus.on("bad2", boom)
    with pytest.raises(ExceptionGroup):
        asyncio.run(bus.parallel("bad2", None))
    assert bus.snapshot()["error_total"] == 2


def test_ring_buffer_keeps_recent_events():
    """环形缓冲：触发 250 次后仍只保留最近 200 条，最近事件最靠前。"""
    bus = InProcessEventBus(ring_size=200)
    bus.on("t", lambda e: None)
    for i in range(250):
        bus.emit("t", {"i": i})

    snap = bus.snapshot()
    assert snap["ring_size"] == 200
    assert snap["ring_capacity"] == 200

    recent = bus.recent_events(5)
    assert len(recent) == 5
    assert recent[0]["timestamp"] >= recent[-1]["timestamp"]
    assert bus.recent_events(500)[0]["topic"] == "t"


def test_waterfall_veto_counted():
    """waterfall 不调 next = veto：计数 +1；调 next 则不计。"""
    bus = InProcessEventBus()
    bus.on(Topics.TOOL_PRE_EXECUTE, lambda event, nxt: None)  # veto
    bus.waterfall(Topics.TOOL_PRE_EXECUTE, {}, final=lambda: "unused")
    assert bus.snapshot()["waterfall_veto_total"] == 1

    bus2 = InProcessEventBus()
    bus2.on(Topics.TOOL_PRE_EXECUTE, lambda event, nxt: nxt())
    assert bus2.waterfall(Topics.TOOL_PRE_EXECUTE, {}, final=lambda: "done") == "done"
    assert bus2.snapshot()["waterfall_veto_total"] == 0


def test_hooks_default_off_and_hook_error_isolated():
    """默认无 hook 时也能统计；hook 自身抛错不影响分发主路径。"""
    bus = InProcessEventBus()
    seen = []
    bus.on("x", lambda e: seen.append(e))

    def bad_hook(_entry):
        raise ValueError("hook 自己炸了")

    bus.set_hooks(on_dispatch=bad_hook)
    bus.emit("x", 1)  # 不因 hook 抛错而失败
    assert seen == [1]
    assert bus.snapshot()["dispatch_total"] == 1
