"""waterfall 专项：洋葱链顺序、veto、final 兜底、prepend。"""
from apiserver.event_bus import InProcessEventBus


def test_all_next_calls_final():
    bus = InProcessEventBus()
    order = []

    def h1(event, next):
        order.append("h1-before")
        result = next()
        order.append("h1-after")
        return result

    def h2(event, next):
        order.append("h2-before")
        result = next()
        order.append("h2-after")
        return result

    bus.on("gate", h1)
    bus.on("gate", h2)
    result = bus.waterfall("gate", {}, final=lambda: "done")

    assert result == "done"
    # 洋葱序：外 → 内 → 内 → 外
    assert order == ["h1-before", "h2-before", "h2-after", "h1-after"]


def test_veto_short_circuits_rest():
    bus = InProcessEventBus()
    calls = []

    bus.on("gate", lambda event, next: calls.append("h1") or next())
    bus.on("gate", lambda event, next: "vetoed")  # 不调 next
    bus.on("gate", lambda event, next: calls.append("h3") or next())

    result = bus.waterfall("gate", {}, final=lambda: "fallback")

    assert result == "vetoed"
    assert calls == ["h1"]  # h3 与 final 均未运行


def test_no_handler_runs_final():
    bus = InProcessEventBus()
    assert bus.waterfall("empty", {}, final=lambda: 42) == 42


def test_no_handler_no_final_returns_none():
    bus = InProcessEventBus()
    assert bus.waterfall("empty", {}) is None


def test_prepend_changes_order():
    bus = InProcessEventBus()
    order = []
    bus.on("gate", lambda event, next: order.append("last") or next())
    bus.on("gate", lambda event, next: order.append("first") or next(), prepend=True)
    bus.waterfall("gate", {}, final=lambda: None)
    assert order == ["first", "last"]


def test_tool_pre_execute_gate_pattern():
    """SPEC 改动点 D：安全门用法 —— 审批通过则放行原调用。"""
    bus = InProcessEventBus()

    def approve(event, next):
        if event["tool"] == "dangerous":
            return {"blocked": True}
        return next()

    bus.on("lumo.tool.pre-execute", approve)

    def original():
        return {"executed": True}

    assert bus.waterfall("lumo.tool.pre-execute", {"tool": "safe"}, final=original) == {"executed": True}
    assert bus.waterfall("lumo.tool.pre-execute", {"tool": "dangerous"}, final=original) == {"blocked": True}
