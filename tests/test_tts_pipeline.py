"""TTS 增量句子积累器验收硬线（handcrafted 蒸馏批 W100-02）。"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lumo.tts_pipeline import IncrementalSentenceAccumulator  # noqa: E402


def test_streaming_split_matches_human():
    """流式喂入分句文本，输出与人工分句一致。"""
    acc = IncrementalSentenceAccumulator()
    out: list[str] = []
    text = "你好。这是第一句！第二句呢？"
    for i in range(0, len(text), 3):
        acc.append(text[i:i + 3])
        out.extend(acc.take_completed_sentences())
    out.extend(acc.flush())
    # 人工分句（末段「第二句呢？」flush 时吐出）
    assert len(out) == 3
    assert out[0].startswith("你好")
    assert out[1].startswith("这是第一句")
    assert out[2].startswith("第二句呢")


def test_no_punct_chunk_zero_cost():
    """无标点 chunk 零开销：take_completed_sentences 直接返回空（预检路径）。"""
    acc = IncrementalSentenceAccumulator()
    acc.append("这是一段没有句末标点的流式文本块")
    assert acc.take_completed_sentences() == []
    # 缓冲原样保留（未做分句破坏）
    assert "没有句末标点" in acc.pending


def test_last_partial_sentence_kept():
    """最后半句保留：只吐完整句，半截留缓冲等补全。"""
    acc = IncrementalSentenceAccumulator()
    acc.append("第一句完整。第二句还没说")
    out = acc.take_completed_sentences()
    assert len(out) == 1 and "第一句" in out[0]
    assert "第二句还没说" in acc.pending  # 半截保留


def test_partial_then_completion():
    """半句后续补全后成句。"""
    acc = IncrementalSentenceAccumulator()
    acc.append("第一句。第二")
    assert acc.take_completed_sentences() == ["第一句。"] or "第一句" in acc.take_completed_sentences()[0]
    acc.append("句补全。")
    out = acc.take_completed_sentences()
    assert any("第二句补全" in s for s in out)


def test_flush_returns_remainder():
    """flush 取剩余尾巴（无标点也给）。"""
    acc = IncrementalSentenceAccumulator()
    acc.append("没标点的尾巴")
    assert acc.take_completed_sentences() == []
    out = acc.flush()
    assert out and "没标点的尾巴" in out[0]
    assert acc.pending == ""


def test_english_punct_supported():
    """英文句末标点同样预检/分句。"""
    acc = IncrementalSentenceAccumulator()
    acc.append("Hello world. Second sentence!")
    out = acc.take_completed_sentences()
    assert any("Hello world" in s for s in out)


def test_reset_clears_buffer():
    acc = IncrementalSentenceAccumulator()
    acc.append("内容")
    acc.reset()
    assert acc.pending == ""
    assert acc.flush() == []


def test_oversized_buffer_truncates_keep_latest():
    """超长缓冲截尾保最新（4096 上限）。"""
    acc = IncrementalSentenceAccumulator(max_buffer=100)
    acc.append("旧" * 500)
    acc.append("新内容。")
    assert acc.pending.endswith("新内容。")
    assert len(acc.pending) <= 100
