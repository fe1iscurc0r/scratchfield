"""W69-04 融合 · 文档分块 + 元数据过滤（吸收 OpenKB 的 chunking 与 metadata-filter 思路，Apache-2.0）

给本仓 rag/ 补「非代码文档接入」的分块策略（按段落 / 定长重叠）与元数据过滤。
纯 stdlib/numpy。
"""
from __future__ import annotations

import re

import numpy as np

__all__ = ["chunk_by_paragraph", "chunk_with_overlap", "filter_by_metadata"]


def chunk_by_paragraph(text: str) -> list[str]:
    """按空行分段，去掉空段与首尾空白。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p]


def chunk_with_overlap(text: str, chunk_size: int = 100, overlap: int = 20) -> list[str]:
    """定长重叠分块：每块 chunk_size 字符，相邻块重叠 overlap 字符。"""
    text = text.strip()
    if not text:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
        if i + chunk_size >= len(text):
            break
    return chunks


def filter_by_metadata(chunks: list[dict], *, source: str | None = None, tag: str | None = None, after_ts: float | None = None) -> list[dict]:
    """按来源/标签/时间过滤 chunk（每个 chunk 是含 metadata 的 dict）。"""
    out = chunks
    if source is not None:
        out = [c for c in out if c.get("source") == source]
    if tag is not None:
        out = [c for c in out if tag in (c.get("tags") or [])]
    if after_ts is not None:
        out = [c for c in out if (c.get("ts") or 0.0) >= after_ts]
    return out
