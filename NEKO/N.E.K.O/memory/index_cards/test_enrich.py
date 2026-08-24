# index_cards/enrich 单元测试 — LLM 索引卡增强（授粉自 caura enrichment）
#
# 覆盖：JSON 宽容解析 / 字段校验规范化 / LLM 失败降级启发式 /
#       enrich_card 写回 / llm_summarizer 回调注入 / memory_type 枚举
# 运行：python3 -m pytest NEKO/N.E.K.O/memory/index_cards/test_enrich.py -q
"""Tests for index_cards.enrich (LLM card enrichment + degradation)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from memory.index_cards.enrich import (
    MEMORY_TYPES,
    _format_turns,
    _parse_json_response,
    _validate,
    enrich_card,
    llm_enrich,
    llm_summarizer,
)
from memory.index_cards.store import IndexCardStore


SAMPLE_TURNS = [
    {"role": "user", "content": "帮我看看这个材料的密度"},
    {"role": "assistant", "content": "这个材料的密度是 1.2 g/cm³"},
    {"role": "user", "content": "那它的热稳定性呢"},
    {"role": "assistant", "content": "热分解温度约 200°C，适合做水凝胶基底"},
]


@pytest.fixture()
def store(tmp_path):
    s = IndexCardStore(tmp_path / "cards.db")
    yield s
    s.close()


# ---------------------------------------------------------------- 工具函数
class TestFormatTurns:
    def test_basic(self) -> None:
        out = _format_turns(SAMPLE_TURNS)
        assert "[user]" in out
        assert "[assistant]" in out
        assert "密度" in out

    def test_empty_content_skipped(self) -> None:
        out = _format_turns([{"role": "user", "content": ""}, {"role": "user", "content": "hi"}])
        assert "hi" in out
        assert out.count("[user]") == 1

    def test_truncation(self) -> None:
        long_turns = [{"role": "user", "content": "x" * 5000}]
        out = _format_turns(long_turns, max_chars=100)
        assert len(out) <= 100 + 20  # 带 role 前缀


class TestParseJson:
    def test_plain_json(self) -> None:
        d = _parse_json_response('{"title": "t", "summary": "s"}')
        assert d == {"title": "t", "summary": "s"}

    def test_code_fence(self) -> None:
        d = _parse_json_response('```json\n{"title": "t"}\n```')
        assert d == {"title": "t"}

    def test_truncated_tail_recovered(self) -> None:
        raw = '{"title": "t", "summary": "s"} 截断的尾巴'
        d = _parse_json_response(raw)
        assert d is not None
        assert d["title"] == "t"

    def test_garbage_returns_none(self) -> None:
        assert _parse_json_response("not json at all") is None


class TestValidate:
    def test_defaults(self) -> None:
        v = _validate({})
        assert v["memory_type"] == "fact"
        assert v["keywords"] == []
        assert v["tags"] == []
        assert 0.0 <= v["weight"] <= 1.0

    def test_keywords_normalized(self) -> None:
        v = _validate({"keywords": [" 水凝胶 ", "密度", 42, ""]})
        assert v["keywords"] == ["水凝胶", "密度", "42"]
        assert len(v["keywords"]) <= 6

    def test_memory_type_enum(self) -> None:
        assert _validate({"memory_type": "preference"})["memory_type"] == "preference"
        assert _validate({"memory_type": "not-a-type"})["memory_type"] == "fact"

    def test_weight_clamped(self) -> None:
        assert _validate({"weight": 99})["weight"] == 1.0
        assert _validate({"weight": -5})["weight"] == 0.0
        assert _validate({"weight": "abc"})["weight"] == 0.5

    def test_memory_types_enum_defined(self) -> None:
        assert "fact" in MEMORY_TYPES
        assert "preference" in MEMORY_TYPES
        assert "decision" in MEMORY_TYPES


# ---------------------------------------------------------------- llm_enrich
class TestLlmEnrich:
    async def test_returns_none_without_config(self) -> None:
        assert await llm_enrich(SAMPLE_TURNS, config_manager=None) is None

    async def test_success(self) -> None:
        cm = AsyncMock()
        cm.aget_model_api_config.return_value = {
            "model": "m", "base_url": "http://x", "api_key": "k",
        }
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {
            "content": '{"title": "材料密度", "summary": "密度1.2，热分解200°C", '
                       '"keywords": ["密度", "水凝胶"], "memory_type": "fact", '
                       '"tags": ["材料"], "weight": 0.8}'
        })()
        with patch("memory.index_cards.enrich.create_chat_llm_async", return_value=llm):
            out = await llm_enrich(SAMPLE_TURNS, cm)
        assert out is not None
        assert out["memory_type"] == "fact"
        assert out["weight"] == 0.8
        assert "密度" in out["keywords"]
        llm.aclose.assert_awaited_once()

    async def test_llm_error_returns_none(self) -> None:
        cm = AsyncMock()
        cm.aget_model_api_config.return_value = {
            "model": "m", "base_url": "http://x", "api_key": "k",
        }
        with patch(
            "memory.index_cards.enrich.create_chat_llm_async",
            side_effect=RuntimeError("boom"),
        ):
            assert await llm_enrich(SAMPLE_TURNS, cm) is None

    async def test_unconfigured_tier_returns_none(self) -> None:
        cm = AsyncMock()
        cm.aget_model_api_config.return_value = {"model": "", "base_url": "", "api_key": ""}
        assert await llm_enrich(SAMPLE_TURNS, cm) is None

    async def test_invalid_json_returns_none(self) -> None:
        cm = AsyncMock()
        cm.aget_model_api_config.return_value = {
            "model": "m", "base_url": "http://x", "api_key": "k",
        }
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {"content": "不是 JSON"})()
        with patch("memory.index_cards.enrich.create_chat_llm_async", return_value=llm):
            assert await llm_enrich(SAMPLE_TURNS, cm) is None


# ---------------------------------------------------------------- enrich_card
class TestEnrichCard:
    async def test_write_back(self, store) -> None:
        card_id = store.build_card("s1", SAMPLE_TURNS)
        cm = AsyncMock()
        cm.aget_model_api_config.return_value = {
            "model": "m", "base_url": "http://x", "api_key": "k",
        }
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {
            "content": '{"title": "t", "summary": "s", "keywords": ["k1"], '
                       '"memory_type": "decision", "tags": ["t1", "t2"], "weight": 0.9}'
        })()
        with patch("memory.index_cards.enrich.create_chat_llm_async", return_value=llm):
            ok = await enrich_card(card_id, SAMPLE_TURNS, store, cm)
        assert ok is True
        cards = store.cards_for_session("s1")
        assert cards[0]["memory_type"] == "decision"
        assert cards[0]["tags"] == ["t1", "t2"]
        assert cards[0]["weight"] == 0.9
        assert cards[0]["enriched_at"] is not None

    async def test_llm_failure_keeps_heuristic(self, store) -> None:
        card_id = store.build_card("s1", SAMPLE_TURNS)
        with patch(
            "memory.index_cards.enrich.create_chat_llm_async",
            side_effect=RuntimeError("boom"),
        ):
            ok = await enrich_card(card_id, SAMPLE_TURNS, store, AsyncMock())
        assert ok is False
        cards = store.cards_for_session("s1")
        assert cards[0]["memory_type"] == "fact"  # 保持默认
        assert cards[0]["weight"] == 0.5

    async def test_build_card_with_summarizer(self, store) -> None:
        def fake_summarizer(turns):
            return ("LLM 摘要", ["kw1", "kw2"])

        card_id = store.build_card("s2", SAMPLE_TURNS, summarizer=fake_summarizer)
        cards = store.cards_for_session("s2")
        assert cards[0]["summary"] == "LLM 摘要"
        assert cards[0]["keywords"] == ["kw1", "kw2"]


# ---------------------------------------------------------------- llm_summarizer
class TestLlmSummarizer:
    def test_fallback_to_heuristic_when_llm_fails(self, store) -> None:
        # config_manager 为 None → llm_enrich 直接返回 None → 回退启发式
        summarizer = llm_summarizer(config_manager=None)
        summary, keywords = summarizer(SAMPLE_TURNS)
        assert summary  # 启发式也有输出
        assert keywords  # 关键词非空
        # 与纯启发式一致
        from memory.index_cards.store import heuristic_summary

        h_summary, h_kw = heuristic_summary(SAMPLE_TURNS)
        assert summary == h_summary
