"""W69-04 融合测试：文档分块 + 元数据过滤。

运行：python -m pytest tools/test_doc_chunker.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from doc_chunker import chunk_by_paragraph, chunk_with_overlap, filter_by_metadata


def test_chunk_by_paragraph():
    text = "第一段。\n\n第二段。\n\n\n第三段。"
    paras = chunk_by_paragraph(text)
    assert paras == ["第一段。", "第二段。", "第三段。"]


def test_chunk_with_overlap_has_overlap():
    text = "x" * 250
    chunks = chunk_with_overlap(text, chunk_size=100, overlap=20)
    # 相邻块重叠：前一块的尾部 == 后一块的头部（overlap 字符）
    assert chunks[0][-20:] == chunks[1][:20]


def test_chunk_with_overlap_covers_all():
    text = "abcdefghij" * 30  # 300 字符
    chunks = chunk_with_overlap(text, chunk_size=100, overlap=20)
    joined = "".join(chunks)
    assert text[:100] in joined  # 首块完整
    assert len(chunks) >= 3  # 300/80 ≈ 4 块


def test_filter_by_metadata():
    chunks = [
        {"text": "a", "source": "wiki", "tags": ["rf"], "ts": 10.0},
        {"text": "b", "source": "paper", "tags": ["materials"], "ts": 20.0},
        {"text": "c", "source": "wiki", "tags": ["sdr"], "ts": 30.0},
    ]
    assert len(filter_by_metadata(chunks, source="wiki")) == 2
    assert len(filter_by_metadata(chunks, tag="rf")) == 1
    assert len(filter_by_metadata(chunks, after_ts=20.0)) == 2
