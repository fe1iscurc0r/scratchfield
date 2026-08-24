"""SPEC 第四节：三条验收条件。"""
from apiserver.event_bus import InProcessEventBus, Topics


def test_disposer_once_only():
    bus = InProcessEventBus()
    count = 0

    def handler(_):
        nonlocal count
        count += 1

    d = bus.on("test", handler)
    bus.emit("test", None)  # count=1
    assert count == 1
    d()
    bus.emit("test", None)  # count=1（handler 已卸载）
    assert count == 1
    d()  # 第二次 no-op，不抛
    bus.emit("test", None)  # count=1
    assert count == 1


def test_waterfall_veto():
    bus = InProcessEventBus()
    # WaterfallHandler(event, next) — 不调 next = veto
    bus.on("gate", lambda event, next: None)
    result = bus.waterfall("gate", {}, final=lambda: "fallback")
    assert result is None  # 被 veto，final 未运行


def test_consumer_plug_unplug():
    # lumo_event.py 不 import 任何消费者
    bus = InProcessEventBus()
    events = []
    bus.on(Topics.USER_INPUT_RECEIVED, lambda e: events.append(e))
    # 模拟 lumo_event.emit
    bus.emit(Topics.USER_INPUT_RECEIVED, {"type": "user_input"})
    assert len(events) == 1
    # 再加一个消费者，不改 lumo_event.py
    more = []
    bus.on(Topics.USER_INPUT_RECEIVED, lambda e: more.append(e))
    bus.emit(Topics.USER_INPUT_RECEIVED, {"type": "user_input"})
    assert len(events) == 2
    assert len(more) == 1
