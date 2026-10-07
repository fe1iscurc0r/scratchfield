"""工单202 任务四接线验收：agent 状态 → EMOTION_REQUESTED 总线桥。

覆盖：主题→状态映射（含失败判定）/ 未知主题不猜 / 默认关（不注入）/
开启后真实总线端到端（emit → on 收到）/ 无角色名 fail closed /
emotion ⊆ NEKO 标准集 / 状态表与壳层 JS 版同构（6 状态、motion 两两不同）。
"""
from __future__ import annotations

from apiserver.event_bus import InProcessEventBus, Topics
from apiserver.event_bus.agent_expression import (
    EVENT_TO_STATE,
    NEKO_STANDARD_EMOTIONS,
    STATE_EXPRESSION,
    AgentExpressionBridge,
    reduce_state,
    to_emotion_request,
)


def test_topic_to_state_mapping():
    assert reduce_state(Topics.USER_INPUT_RECEIVED) == "thinking"
    assert reduce_state(Topics.TOOL_PRE_EXECUTE) == "working"
    assert reduce_state(Topics.TOOL_GUARD) == "working"
    assert reduce_state(Topics.TTS_START) == "thinking"
    assert reduce_state(Topics.DECISION_COMPLETED) == "celebrate"


def test_tool_post_execute_success_vs_failure():
    assert reduce_state(Topics.TOOL_POST_EXECUTE, {"status": "ok"}) == "thinking"
    assert reduce_state(Topics.TOOL_POST_EXECUTE, {"status": "error"}) == "error"
    assert reduce_state(Topics.TOOL_POST_EXECUTE, {"ok": False}) == "error"
    assert reduce_state(Topics.TOOL_POST_EXECUTE, {"error": "boom"}) == "error"
    assert reduce_state(Topics.TOOL_POST_EXECUTE) == "thinking"


def test_unknown_topic_never_guesses():
    assert reduce_state("lumo.nonexistent.topic") is None
    assert reduce_state("") is None
    assert reduce_state(None) is None


def test_state_expression_contract():
    """emotion ⊆ NEKO 标准集；6 状态 motion 两两不同；4 种以上情绪。"""
    assert len(STATE_EXPRESSION) == 6
    emotions, motions = set(), set()
    for state, entry in STATE_EXPRESSION.items():
        assert entry["emotion"] in NEKO_STANDARD_EMOTIONS, state
        assert entry["motion"] and entry["label"], state
        emotions.add(entry["emotion"])
        motions.add(entry["motion"])
    assert len(emotions) >= 4, f"不同情绪须 ≥4，实际 {sorted(emotions)}"
    assert len(motions) == 6


def test_to_emotion_request_fail_closed():
    req = to_emotion_request("celebrate", "陆墨")
    assert req == {"lanlan_name": "陆墨", "emotion": "happy", "state": "celebrate"}
    assert to_emotion_request("celebrate", "") is None
    assert to_emotion_request("celebrate", None) is None
    assert to_emotion_request("no_such_state", "陆墨") is None


def test_bridge_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LUMO_AGENT_EXPRESSION", raising=False)
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.EMOTION_REQUESTED, lambda e: received.append(e))
    bridge = AgentExpressionBridge(bus.emit, character_provider=lambda: "陆墨")
    assert bridge.enabled is False
    assert bridge.on_event(Topics.USER_INPUT_RECEIVED) is None
    assert received == []
    assert bridge.stats() == {"enabled": False, "injected": 0, "skipped": 1}


def test_bridge_enabled_end_to_end_on_real_bus():
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.EMOTION_REQUESTED, lambda e: received.append(e))
    bridge = AgentExpressionBridge(bus.emit, character_provider=lambda: "陆墨",
                                   enabled=True)

    req = bridge.on_event(Topics.DECISION_COMPLETED)
    assert req["emotion"] == "happy"
    assert len(received) == 1
    event = received[0]
    assert event["emotion"] == "happy"
    assert event["character"] == "陆墨"
    assert event["state"] == "celebrate"
    assert event["source"] == "agent_expression"

    bridge.on_event(Topics.TOOL_POST_EXECUTE, {"status": "error"})
    assert received[-1]["emotion"] == "sad"

    assert bridge.stats() == {"enabled": True, "injected": 2, "skipped": 0}


def test_bridge_without_character_skips(monkeypatch):
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.EMOTION_REQUESTED, lambda e: received.append(e))
    bridge = AgentExpressionBridge(bus.emit, character_provider=lambda: None, enabled=True)
    assert bridge.on_event(Topics.USER_INPUT_RECEIVED) is None
    assert received == []
    assert bridge.stats()["skipped"] == 1


def test_character_provider_exception_is_safe():
    def boom() -> str:
        raise RuntimeError("no character yet")

    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.EMOTION_REQUESTED, lambda e: received.append(e))
    bridge = AgentExpressionBridge(bus.emit, character_provider=boom, enabled=True)
    assert bridge.on_event(Topics.USER_INPUT_RECEIVED) is None
    assert received == []


def test_unknown_topic_does_not_emit():
    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.EMOTION_REQUESTED, lambda e: received.append(e))
    bridge = AgentExpressionBridge(bus.emit, character_provider=lambda: "陆墨", enabled=True)
    assert bridge.on_event("lumo.totally.unknown") is None
    assert received == []
    assert bridge.injected == 0


def test_event_to_state_table_only_declares_real_sources():
    """表里只应有有真实来源的主题（wait/idle 侧无来源，不得杜撰）。"""
    assert STATE_EXPRESSION["wait"]["motion"] == "wait"      # 表里有状态
    assert "lumo.tool.pre-execute" in EVENT_TO_STATE           # 有真实来源的才进表
    values = set(EVENT_TO_STATE.values())
    assert values <= {"thinking", "working", "celebrate"}
