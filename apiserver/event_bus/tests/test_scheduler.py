"""W120-02 验收：调度任务总线化（tick 发号 / 循环 / proactive 等价迁移 / 兜底开关）。

对应工单验收：
- bus 上能收到 lumo.scheduler.tick（间隔与计数正确）
- proactive 在 tick 下触发/不触发与旧逻辑一致（仅 5m 档；判定仍由既有 check() 决定）
- 原定时器保留可切回（config.bus.scheduler.use_bus）
"""
from __future__ import annotations

import asyncio
import time

from apiserver.event_bus import InProcessEventBus, Topics
from apiserver.event_bus.scheduler import (
    Scheduler,
    parse_interval,
    register_scheduler_subscriber,
)


def test_parse_interval_units_and_errors():
    assert parse_interval("30s") == 30
    assert parse_interval("5m") == 300
    assert parse_interval("2h") == 7200
    assert parse_interval("0.5m") == 30
    for bad in ("", "5", "m5", "5d"):
        try:
            parse_interval(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} 应抛 ValueError")


def test_emit_tick_payload_and_monotonic_counter():
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.SCHEDULER_TICK, lambda e: received.append(e))

    scheduler = Scheduler(bus, ticks=["5m"])
    first = scheduler.emit_tick("5m")
    second = scheduler.emit_tick("5m")

    assert first["interval"] == "5m" and first["tick_n"] == 1
    assert second["tick_n"] == 2 and second["triggered_at"]
    assert scheduler.tick_count("5m") == 2 and scheduler.tick_count() == 2
    assert len(received) == 2


def test_scheduler_loop_emits_per_interval():
    """真实循环：0.15s 档位跑 ~0.5s 应发出 ≥2 次且计数递增。"""
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.SCHEDULER_TICK, lambda e: received.append(e))

    async def scenario() -> None:
        scheduler = Scheduler(bus, ticks=["0.15s"])
        scheduler.start()
        try:
            await asyncio.sleep(0.5)
        finally:
            scheduler.stop()
        assert scheduler.tick_count("0.15s") >= 2

    asyncio.run(scenario())
    assert len(received) >= 2
    assert [e["tick_n"] for e in received] == sorted(e["tick_n"] for e in received)


def test_register_scheduler_subscriber_receives_and_unsubscribes():
    bus = InProcessEventBus()
    seen: list[str] = []
    dispose = register_scheduler_subscriber(bus, lambda e: seen.append(e["interval"]))

    scheduler = Scheduler(bus)
    scheduler.emit_tick("1h")
    assert seen == ["1h"]
    dispose()
    scheduler.emit_tick("1h")
    assert seen == ["1h"]  # 退订后不再收到


def test_proactive_on_scheduler_tick_matches_old_behaviour(monkeypatch):
    """proactive 的 tick 处理器：只吃 5m 档；对已知会话逐个 check(sid, snap, "科研提醒")。"""
    from apiserver.routes import lumo_state
    from apiserver.routes.lumo_proactive import ProactiveDecider

    calls: list[tuple] = []

    class FakeStore:
        def get_snapshot(self, sid: str) -> str:
            return f"snap-{sid}"

    monkeypatch.setattr(lumo_state, "get_state_store", lambda: FakeStore())

    decider = ProactiveDecider()
    decider._states = {"s1": {}, "s2": {}}  # 两个已知会话（与旧定时器遍历范围一致）

    async def fake_check(sid: str, snapshot: str, topic: str):
        calls.append((sid, snapshot, topic))
        return None

    monkeypatch.setattr(decider, "check", fake_check, raising=False)

    # 非 5m 档：不触发
    asyncio.run(decider.on_scheduler_tick({"interval": "1h", "tick_n": 1}))
    assert calls == []

    # 5m 档：与 _periodic_check 等价（逐会话、topic=科研提醒、快照来自 state store）
    asyncio.run(decider.on_scheduler_tick({"interval": "5m", "tick_n": 1}))
    assert calls == [("s1", "snap-s1", "科研提醒"), ("s2", "snap-s2", "科研提醒")]


def test_use_bus_switch_defaults_true():
    """兜底开关默认走总线（false 时才切回原定时器）。"""
    import sys

    sys.path.insert(0, ".")
    from system.config import get_config

    assert get_config().bus.scheduler.use_bus is True
    assert "5m" in get_config().bus.scheduler.ticks
