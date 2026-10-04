"""W69-05 融合 · 视频摘要知识库管线（吸收 BiliSum 的「字幕→分段→摘要→知识库」思路，MIT）

把视频字幕（含时间戳）转成「分段摘要 + 时间戳锚点」的可检索条目，补 bilibili-video /
youtube-content skill 的摘要短板。摘要函数为 mock（可替换为 LLM），管线本身可跑、可测。

纯 numpy/stdlib，无真视频。
"""
from __future__ import annotations

import numpy as np

__all__ = ["segment_cues", "summarize_segment", "build_knowledge"]


def segment_cues(cues: list[tuple[float, float, str]], max_seg_s: float = 120.0) -> list[list[tuple[float, float, str]]]:
    """按时间窗把字幕 cues 切成不重叠、有序的段（每段时长 ≤ max_seg_s）。"""
    cues = sorted(cues, key=lambda c: c[0])
    segments: list[list[tuple[float, float, str]]] = []
    cur: list[tuple[float, float, str]] = []
    seg_start = None
    for start, end, text in cues:
        if seg_start is None:
            seg_start = start
        if start - seg_start > max_seg_s and cur:
            segments.append(cur)
            cur = []
            seg_start = start
        cur.append((start, end, text))
    if cur:
        segments.append(cur)
    return segments


def summarize_segment(cues: list[tuple[float, float, str]], summarizer=None) -> str:
    """段摘要（mock：拼接首句 + 关键词；summarizer 可替换为真实 LLM 摘要）。"""
    if summarizer is not None:
        return summarizer(cues)
    if not cues:
        return ""
    texts = [t for _, _, t in cues if t.strip()]
    if not texts:
        return ""
    # mock：首句 + 最长句的关键词（前 6 个词）
    head = texts[0][:40]
    words = " ".join(texts).split()
    keywords = " ".join(words[:6]) if words else ""
    return f"{head} … {keywords}"


def build_knowledge(cues: list[tuple[float, float, str]], max_seg_s: float = 120.0) -> list[dict]:
    """字幕 → 知识条目（含时间戳锚点），供检索定位到具体片段。"""
    entries = []
    for seg in segment_cues(cues, max_seg_s):
        entries.append({
            "start_s": seg[0][0],
            "end_s": seg[-1][1],
            "summary": summarize_segment(seg),
        })
    return entries
