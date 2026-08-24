# memory/enrichment 单元测试 — caura 式索引卡增强管线（F-02）
#
# 覆盖：无 LLM 规则降级必通（索引卡仍生成）/ LLM 失败降级 /
#       LLM 路径 mock 字段完整 / on_memory_write 钩子联动 / 空记录安全
# 运行：python -m pytest NEKO/N.E.K.O/memory/test_enrichment.py -q
"""Tests for memory.enrichment (card enrichment pipeline + rule fallback)."""

from __future__ import annotations

import pytest

from memory.enrichment import (
    ENRICHMENT_FIELDS,
    EnrichmentPipeline,
    RuleBasedEnrichmentService,
    install_on_write_enrichment,
    rule_enrich,
)
from memory.hooks import MemoryHooks
from memory.index_cards.enrich import MEMORY_TYPES
from memory.index_cards.store import IndexCardStore


TURNS = [
    {"role": "user", "content": "记住我喜欢深色主题，晚上写码眼睛舒服"},
    {"role": "assistant", "content": "好的，已记住你的深色主题偏好"},
]

LLM_FIELDS = {
    "title": "深色主题偏好",
    "summary": "用户偏好深色主题，夜间写码护眼。",
    "keywords": ["深色主题", "偏好", "写码"],
    "memory_type": "preference",
    "tags": ["ui", "preference"],
    "weight": 0.8,
}


class FakeLLMService:
    """可控 mock：mode = ok / none / raise。"""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls = 0

    async def enrich(self, turns):
        self.calls += 1
        if self.mode == "none":
            return None
        if self.mode == "raise":
            raise RuntimeError("LLM 网络炸了")
        return dict(LLM_FIELDS)


@pytest.fixture()
def store(tmp_path):
    s = IndexCardStore(tmp_path / "cards.db")
    yield s
    s.close()


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("NEKO_MEMORY_HOOKS", "1")
    yield


def _card(store, session_id="adhoc"):
    cards = store.cards_for_session(session_id)
    assert cards, "索引卡应已生成"
    return cards[0]


def assert_fields_complete(card: dict) -> None:
    """六字段完整且合法（验收口径）。"""
    assert card["memory_type"] in MEMORY_TYPES
    assert 0.0 <= card["weight"] <= 1.0
    assert isinstance(card["summary"], str) and card["summary"]
    assert isinstance(card["keywords"], list)
    assert isinstance(card["tags"], list)
    assert card["topic"], "title 落在 topic 列"


class TestRuleFallbackAlwaysSucceeds:
    """验收：无 LLM 配置时索引卡仍生成（规则降级路径必通）。"""

    def test_no_llm_config_card_still_generated(self, store):
        """llm_service=None → 纯规则降级，卡片字段完整。"""
        p = EnrichmentPipeline(llm_service=None)
        card_id = p.enrich_and_store({"session_id": "s1", "turns": TURNS}, store)
        assert isinstance(card_id, int)
        card = _card(store, "s1")
        assert_fields_complete(card)
        assert card["memory_type"] == "preference", "规则应命中偏好模式"
        assert card["enriched_at"], "增强字段写回时间戳"
        assert p.stats["rule_fallbacks"] == 1 and p.stats["llm_hits"] == 0

    def test_llm_returns_none_degrades_to_rule(self, store):
        p = EnrichmentPipeline(llm_service=FakeLLMService("none"))
        card_id = p.enrich_and_store({"session_id": "s2", "turns": TURNS}, store)
        assert isinstance(card_id, int)
        assert_fields_complete(_card(store, "s2"))
        assert p.stats["rule_fallbacks"] == 1

    def test_llm_raises_degrades_to_rule(self, store):
        """LLM 服务抛异常 → 管线捕获 → 规则降级，卡片仍生成。"""
        p = EnrichmentPipeline(llm_service=FakeLLMService("raise"))
        card_id = p.enrich_and_store({"session_id": "s3", "turns": TURNS}, store)
        assert isinstance(card_id, int)
        assert_fields_complete(_card(store, "s3"))

    def test_single_content_record_no_llm(self, store):
        """单条 content（无 turns）形态：规则降级也建卡。"""
        p = EnrichmentPipeline()
        card_id = p.enrich_and_store({"content": "项目排期定在下周三上线"}, store)
        assert isinstance(card_id, int)
        card = _card(store)
        assert card["memory_type"] in ("project", "event")

    def test_empty_record_returns_none(self, store):
        p = EnrichmentPipeline()
        assert p.enrich_and_store({}, store) is None
        assert p.enrich_and_store({"content": "   "}, store) is None
        assert store.cards_for_session("adhoc") == []


class TestLLMPathMocked:
    """验收：LLM 路径 mock 断言字段完整（卡片字段来自 LLM 输出）。"""

    def test_llm_fields_written_to_card(self, store):
        p = EnrichmentPipeline(llm_service=FakeLLMService("ok"))
        card_id = p.enrich_and_store({"session_id": "s9", "turns": TURNS}, store)
        assert isinstance(card_id, int)
        card = _card(store, "s9")
        # 六字段完整 + 取值来自 LLM mock
        assert card["topic"] == LLM_FIELDS["title"]
        assert card["summary"] == LLM_FIELDS["summary"]
        assert card["keywords"] == LLM_FIELDS["keywords"]
        assert card["memory_type"] == LLM_FIELDS["memory_type"]
        assert card["tags"] == LLM_FIELDS["tags"]
        assert abs(card["weight"] - LLM_FIELDS["weight"]) < 1e-9
        assert p.stats["llm_hits"] == 1 and p.stats["rule_fallbacks"] == 0

    def test_llm_partial_output_backfilled(self, store):
        """LLM 输出缺 title/weight 非法 → _ensure_complete 兜底补齐，不炸。"""

        class Partial:
            async def enrich(self, turns):
                return {"summary": "只有摘要", "keywords": ["k1"], "weight": "abc"}

        p = EnrichmentPipeline(llm_service=Partial())
        card_id = p.enrich_and_store({"session_id": "s10", "turns": TURNS}, store)
        assert isinstance(card_id, int)
        card = _card(store, "s10")
        assert card["topic"], "title 兜底"
        assert card["memory_type"] in MEMORY_TYPES
        assert 0.0 <= card["weight"] <= 1.0


class TestRuleEnrichUnits:
    def test_rule_enrich_type_patterns(self):
        cases = [
            ("我喜欢深色主题", "preference"),
            ("方案定了，决定采用 PostgreSQL", "decision"),
            ("今天参加了季度评审", "event"),
        ]
        for text, expected in cases:
            fields = rule_enrich([{"role": "user", "content": text}])
            assert fields["memory_type"] == expected, text
            assert set(ENRICHMENT_FIELDS) <= set(fields)

    def test_rule_enrich_weight_bounds(self):
        fields = rule_enrich([{"role": "user", "content": "嗯"}])
        assert 0.0 <= fields["weight"] <= 1.0

    def test_rule_service_is_enrichment_service(self):
        p = EnrichmentPipeline(llm_service=RuleBasedEnrichmentService())
        assert isinstance(p.enrich(TURNS), dict)


class TestHookIntegration:
    """F-02 接入 F-01：on_memory_write 触发增强管线建卡。"""

    def test_on_memory_write_builds_enriched_card(self, store, enabled):
        hooks = MemoryHooks()
        name = install_on_write_enrichment(hooks, store=store, llm_service=None)
        assert name == "on_memory_write/enrichment_pipeline"
        results = hooks.emit("on_memory_write", record={
            "session_id": "hook-s1", "turns": TURNS,
        })
        assert len(results) == 1 and isinstance(results[0], int)
        card = _card(store, "hook-s1")
        assert_fields_complete(card)

    def test_install_idempotent(self, store, enabled):
        """重复 install 不叠加：一次 emit 一张卡。"""
        hooks = MemoryHooks()
        install_on_write_enrichment(hooks, store=store)
        install_on_write_enrichment(hooks, store=store)
        results = hooks.emit("on_memory_write", record={"content": "幂等"})
        assert len(results) == 1
        assert len(store.cards_for_session("adhoc")) == 1

    def test_respects_global_switch(self, store, monkeypatch):
        """总开关关闭（默认）→ 钩子装了也不触发，现行为不变。"""
        monkeypatch.delenv("NEKO_MEMORY_HOOKS", raising=False)
        hooks = MemoryHooks()
        install_on_write_enrichment(hooks, store=store)
        assert hooks.emit("on_memory_write", record={"content": "x"}) == []
        assert store.cards_for_session("adhoc") == []

    def test_with_llm_via_hook(self, store, enabled):
        """钩子路径带 LLM 服务：字段来自 LLM mock。"""
        hooks = MemoryHooks()
        install_on_write_enrichment(
            hooks, store=store, llm_service=FakeLLMService("ok"))
        hooks.emit("on_memory_write", record={"session_id": "hook-s2", "turns": TURNS})
        card = _card(store, "hook-s2")
        assert card["memory_type"] == "preference"
        assert card["topic"] == LLM_FIELDS["title"]
