# memory/hooks 单元测试 — agentmemory 6-hook 生命周期（F-01）
#
# 覆盖：6 事件按序触发 / env 总开关默认关闭 / 开启后触发 / 同名幂等替换 /
#       单 hook 异常 fail-safe / system_prompt_block 聚合 /
#       on_memory_write → 索引卡联动（install_default_wiring）
# 运行：python -m pytest NEKO/N.E.K.O/memory/test_hooks.py -q
"""Tests for memory.hooks (6-hook lifecycle registry)."""

from __future__ import annotations

import pytest

from memory.hooks import (
    HOOK_EVENTS,
    MemoryHooks,
    get_memory_hooks,
    hooks_enabled,
    install_default_wiring,
)
from memory.index_cards.store import IndexCardStore


@pytest.fixture()
def enabled(monkeypatch):
    """打开总开关（默认关闭，测试显式开启）。"""
    monkeypatch.setenv("NEKO_MEMORY_HOOKS", "1")
    yield
    # monkeypatch 自动还原


@pytest.fixture()
def disabled(monkeypatch):
    monkeypatch.delenv("NEKO_MEMORY_HOOKS", raising=False)
    yield


@pytest.fixture()
def registry():
    r = MemoryHooks()
    yield r
    r.reset()


class TestSixEventsInOrder:
    """验收：6 事件按生命周期序触发。"""

    def test_all_six_events_fire_in_lifecycle_order(self, registry, enabled):
        """一个顺序记录器挂满 6 个事件，按 HOOK_EVENTS 序 emit，触发序一致。"""
        order: list[str] = []
        for ev in HOOK_EVENTS:
            registry.register(
                ev, lambda ev=ev, **_: order.append(ev), name="recorder",
            )
        payloads = {
            "prefetch": {"session_id": "s1", "query": "密度"},
            "sync_turn": {"session_id": "s1", "turn": {"role": "user", "content": "hi"}},
            "on_session_end": {"session_id": "s1", "turns": []},
            "on_pre_compress": {"session_id": "s1", "turns": []},
            "on_memory_write": {"record": {"content": "新事实"}},
            "system_prompt_block": {"session_id": "s1"},
        }
        for ev in HOOK_EVENTS:
            registry.emit(ev, **payloads[ev])
        assert order == list(HOOK_EVENTS)
        assert order == [
            "prefetch", "sync_turn", "on_session_end",
            "on_pre_compress", "on_memory_write", "system_prompt_block",
        ]

    def test_hooks_within_event_fire_in_register_order(self, registry, enabled):
        """同一事件内多 hook 按登记序执行，emit 返回值保序。"""
        registry.register("prefetch", lambda **_: "a", name="a")
        registry.register("prefetch", lambda **_: "b", name="b")
        registry.register("prefetch", lambda **_: "c", name="c")
        assert registry.emit("prefetch", session_id="s", query="q") == ["a", "b", "c"]


class TestEnvSwitch:
    """验收：默认关闭不改变现行为；开关开启才触发。"""

    def test_default_off_emit_short_circuits(self, registry, disabled):
        registry.register("prefetch", lambda **_: pytest.fail("关闭时不得触发"))
        assert registry.emit("prefetch", session_id="s", query="q") == []
        assert hooks_enabled() is False

    def test_switch_on_fires(self, registry, enabled):
        hit: list[int] = []
        registry.register("sync_turn", lambda **_: hit.append(1))
        registry.emit("sync_turn", session_id="s", turn={})
        assert hit == [1]
        assert hooks_enabled() is True

    def test_off_values_do_not_enable(self, registry, monkeypatch):
        for v in ("0", "", "false", "no", "off", "2"):
            monkeypatch.setenv("NEKO_MEMORY_HOOKS", v)
            assert hooks_enabled() is False, f"{v!r} 不应开启"


class TestIdempotentAndFailSafe:
    def test_same_name_register_replaces_not_duplicates(self, registry, enabled):
        """同名重复 register = 替换：一次 emit 只触发一次。"""
        registry.register("prefetch", lambda **_: "old", name="dup")
        registry.register("prefetch", lambda **_: "new", name="dup")
        assert registry.emit("prefetch", session_id="s", query="q") == ["new"]
        assert registry.list_hooks("prefetch") == {"prefetch": ["dup"]}

    def test_hook_exception_does_not_infect_others(self, registry, enabled):
        """单个 hook 抛异常：跳过它，其余照常，emit 不抛。"""
        def boom(**_):
            raise RuntimeError("hook 崩了")
        registry.register("on_session_end", boom, name="bad")
        registry.register("on_session_end", lambda **_: "ok", name="good")
        results = registry.emit("on_session_end", session_id="s", turns=[])
        assert results == ["ok"]  # 崩的吞掉（fail-safe）

    def test_unregister(self, registry, enabled):
        registry.register("prefetch", lambda **_: 1, name="x")
        assert registry.unregister("prefetch", "x") is True
        assert registry.unregister("prefetch", "x") is False
        assert registry.emit("prefetch", session_id="s", query="q") == []

    def test_unknown_event_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.register("nope", lambda **_: None)
        with pytest.raises(ValueError):
            registry.emit("nope")


class TestSystemPromptBlock:
    def test_aggregates_text_blocks_in_order(self, registry, enabled):
        registry.register("system_prompt_block",
                          lambda session_id, **_: f"[卡] {session_id} 摘要", name="cards")
        registry.register("system_prompt_block",
                          lambda session_id, **_: None, name="silent")  # None 跳过
        registry.register("system_prompt_block",
                          lambda session_id, **_: 123, name="nonstr")   # 非 str 跳过
        registry.register("system_prompt_block",
                          lambda session_id, **_: "   ", name="blank")  # 空白跳过
        registry.register("system_prompt_block",
                          lambda session_id, **_: "[图] 关联提示", name="graph")
        text = registry.emit_system_prompt_block("s9")
        assert text == "[卡] s9 摘要\n[图] 关联提示"

    def test_empty_when_no_hooks(self, registry, enabled):
        assert registry.emit_system_prompt_block("s") == ""


class TestOnMemoryWriteIndexCardWiring:
    """验收：接入写路径（on_memory_write → 索引卡联动）。"""

    def test_turns_record_builds_card(self, registry, enabled, tmp_path):
        store = IndexCardStore(tmp_path / "cards.db")
        try:
            install_default_wiring(registry, card_store=store)
            results = registry.emit("on_memory_write", record={
                "session_id": "sess-42",
                "turns": [
                    {"role": "user", "content": "这个材料密度多少"},
                    {"role": "assistant", "content": "密度 1.2 g/cm³"},
                ],
            })
            assert len(results) == 1 and isinstance(results[0], int)
            cards = store.cards_for_session("sess-42")
            assert len(cards) == 1
            assert cards[0]["keywords"], "启发式建卡应有关键词"
        finally:
            store.close()

    def test_single_content_record_builds_card(self, registry, enabled, tmp_path):
        """单条事实（只有 content，无 turns）也联动建卡。"""
        store = IndexCardStore(tmp_path / "cards.db")
        try:
            install_default_wiring(registry, card_store=store)
            results = registry.emit("on_memory_write", record={"content": "用户偏好深色主题"})
            assert isinstance(results[0], int)
            cards = store.cards_for_session("adhoc")
            assert len(cards) == 1
        finally:
            store.close()

    def test_empty_record_returns_none_no_card(self, registry, enabled, tmp_path):
        store = IndexCardStore(tmp_path / "cards.db")
        try:
            install_default_wiring(registry, card_store=store)
            results = registry.emit("on_memory_write", record={})
            assert results == [None]
            assert store.cards_for_session("adhoc") == []
        finally:
            store.close()

    def test_wiring_idempotent_no_double_fire(self, registry, enabled, tmp_path):
        """重复 install_default_wiring 不叠加：一次 emit 只建一张卡。"""
        store = IndexCardStore(tmp_path / "cards.db")
        try:
            install_default_wiring(registry, card_store=store)
            install_default_wiring(registry, card_store=store)
            results = registry.emit("on_memory_write", record={"content": "幂等接线"})
            assert len(results) == 1
            assert len(store.cards_for_session("adhoc")) == 1
        finally:
            store.close()

    def test_wiring_respects_global_switch(self, registry, disabled, tmp_path):
        """总开关关闭时（默认态），联动装了也不触发——现行为零变化。"""
        store = IndexCardStore(tmp_path / "cards.db")
        try:
            install_default_wiring(registry, card_store=store)
            assert registry.emit("on_memory_write", record={"content": "x"}) == []
            assert store.cards_for_session("adhoc") == []
        finally:
            store.close()


class TestGlobalSingleton:
    def test_get_memory_hooks_singleton(self):
        a = get_memory_hooks()
        b = get_memory_hooks()
        assert a is b
        a.reset()
