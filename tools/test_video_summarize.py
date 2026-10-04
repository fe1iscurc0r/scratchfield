"""W69-05 融合测试：视频摘要知识库管线。

运行：python -m pytest tools/test_video_summarize.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from video_summarize import build_knowledge, segment_cues, summarize_segment


def _cues(n=12):
    # 12 条字幕，每条 10s，共 120s（按 60s 一段应切成 2 段）
    return [(i * 10.0, i * 10.0 + 9.0, f"字幕第 {i} 段的内容") for i in range(n)]


def test_segment_ordered_non_overlapping():
    cues = _cues()
    segs = segment_cues(cues, max_seg_s=60.0)
    assert len(segs) == 2  # 120s / 60s
    # 段间不重叠、有序
    assert segs[0][-1][1] <= segs[1][0][0]
    assert segs[0][0][0] < segs[1][0][0]


def test_summarize_nonempty():
    assert summarize_segment(_cues(3)) != ""


def test_build_knowledge_carries_timestamps():
    entries = build_knowledge(_cues(12), max_seg_s=60.0)
    assert len(entries) == 2
    for e in entries:
        assert e["start_s"] < e["end_s"]
        assert e["summary"]


def test_empty_cues_handled():
    assert segment_cues([], max_seg_s=60.0) == []
    assert build_knowledge([], max_seg_s=60.0) == []
    assert summarize_segment([]) == ""
