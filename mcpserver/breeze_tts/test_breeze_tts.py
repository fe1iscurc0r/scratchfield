"""breeze_tts 离线单测（工单 263 任务 D；不真调模型）。"""
from __future__ import annotations

import json
import pathlib

import pytest

from mcpserver.breeze_tts.agent import (
    BreezeTTSAgent,
    EmotionEvent,
    parse_emotion_events,
)

MANIFEST = pathlib.Path(__file__).with_name("agent-manifest.json")


# ---- 情绪标记解析（3 例）----
def test_single_tag_extracted() -> None:
    pure, events = parse_emotion_events("你好[笑]，今天如何？")
    assert pure == "你好，今天如何？"
    assert events == [EmotionEvent(start=2, end=5, tag="笑")]


def test_multiple_tags_ordered() -> None:
    pure, events = parse_emotion_events("[叹气]算了[咳嗽]吧")
    assert pure == "算了吧"
    assert [e.tag for e in events] == ["叹气", "咳嗽"]
    assert events[0].start < events[1].start


def test_unknown_brackets_kept() -> None:
    """未知方括号内容不当情绪，原样保留（防误伤 [注] 这类标注）。"""
    pure, events = parse_emotion_events("见[注]说明")
    assert pure == "见[注]说明"
    assert events == []


# ---- 空文本（1 例）----
def test_empty_text_rejected() -> None:
    agent = BreezeTTSAgent(model_dir="C:/whatever")
    with pytest.raises(ValueError):
        agent.synthesize("")
    with pytest.raises(ValueError):
        agent.synthesize("[笑]")  # 只有情绪标记，剔除后为空


# ---- 权重缺失报错（1 例）----
def test_missing_weights_readable_error(monkeypatch) -> None:
    monkeypatch.delenv("BREEZE_TTS_MODEL_DIR", raising=False)
    agent = BreezeTTSAgent(model_dir=None)
    with pytest.raises(RuntimeError, match="BREEZE_TTS_MODEL_DIR"):
        agent.synthesize("你好")


# ---- manifest 可 json.load（1 例）----
def test_manifest_loadable() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "breeze_tts"
    assert data["license"] == "Apache-2.0"
    assert {t["name"] for t in data["tools"]} == {
        "breeze_synthesize",
        "breeze_list_voices",
        "breeze_health",
    }
