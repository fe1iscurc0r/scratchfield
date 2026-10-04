"""TTS 增量句子积累器（handcrafted 蒸馏批 W100-02 原创实现）。

设计参考：handcrafted-persona-engine 的 IncrementalSentenceAccumulator（无 LICENSE，
仅蒸馏不融合）——按蒸馏文档 docs/handcrafted-tts-engine-distill-2026-09-10.md 第 2 节
的设计思想从零编写。

三个关键优化（蒸馏要点）：
    1. 标点预检：缓冲无句末标点直接返回空，省 ~90% 块的开销。
    2. 分句后保留最后一段：只吐前 N-1 句，防半截句子切出。
    3. 归一化/分句走接口（可插拔），默认正则中文分句 + 简体统一（无重依赖）。
"""
from __future__ import annotations

import re

# 句末标点（预检 + 分句共用）：中英文
_SENT_END_RE = re.compile(r"[。！？；：…!?;:]")
# 分句：在句末标点后切（含右引号/括号吞并）
_SPLIT_RE = re.compile(r"([^。！？；：…!?;:]*[。！？；：…!?;:]+[」』”’）)]*)")

_DEFAULT_MAX_BUFFER = 4096


def normalize_text(text: str) -> str:
    """默认归一化：去多余空白（无重依赖；可插拔替换）。"""
    return re.sub(r"\s+", " ", text).strip()


def segment_sentences(text: str) -> list[str]:
    """默认分句：正则句末标点切分（可插拔替换）。"""
    parts = [m.group(0).strip() for m in _SPLIT_RE.finditer(text)]
    remainder = _SPLIT_RE.sub("", text).strip()
    if remainder:
        parts.append(remainder)
    return [p for p in parts if p]


class IncrementalSentenceAccumulator:
    """流式文本 → 完整句子（标点预检 + 末段保留）。"""

    def __init__(
        self,
        normalizer=normalize_text,
        segmenter=segment_sentences,
        max_buffer: int = _DEFAULT_MAX_BUFFER,
    ) -> None:
        self._normalizer = normalizer
        self._segmenter = segmenter
        self._max_buffer = max_buffer
        self._buf = ""

    def append(self, chunk: str) -> None:
        """流式塞入缓冲；超长时截尾保最新。"""
        self._buf = (self._buf + chunk)[-self._max_buffer:]

    def take_completed_sentences(self) -> list[str]:
        """返回完整句子列表（无句末标点则空，零归一化/分句开销）。"""
        if not _SENT_END_RE.search(self._buf):
            return []
        sentences = self._segmenter(self._normalizer(self._buf))
        if not sentences:
            return []
        last = sentences[-1]
        # 末段带句末标点 → 全部为完整句，直接吐空缓冲
        if _SENT_END_RE.search(last):
            self._buf = ""
            return sentences
        if len(sentences) <= 1:
            return []
        # 末段保留：可能是半截句子，留给后续 chunk 补全
        self._buf = last
        return sentences[:-1]

    def flush(self) -> list[str]:
        """流结束：取剩余尾巴（有内容就吐，无论是否完整句）。"""
        if not self._buf.strip():
            self._buf = ""
            return []
        out = self._segmenter(self._normalizer(self._buf))
        self._buf = ""
        return [s for s in out if s]

    def reset(self) -> None:
        self._buf = ""

    @property
    def pending(self) -> str:
        return self._buf
