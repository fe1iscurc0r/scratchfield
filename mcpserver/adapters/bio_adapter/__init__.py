"""bio_adapter —— 确定性序列比对适配层（Phase A2）。

源码来自上游 `AffineGaps`（Apache 2.0），`align.py` 为 affine_gaps.py 原样复制（零修改）。

核心能力（SPEC 3.2）：
- `needleman_wunsch_gotoh_alignment`：全局比对（affine gap penalty）
- `smith_waterman_gotoh_alignment`：局部比对（affine gap penalty）
- `levenshtein_distance`：编辑距离算法

依赖：numpy（必须）；numba 有则 JIT 加速，无则纯 Python 回退（上游已内置 HAS_NUMBA 探测）。
"""
from __future__ import annotations

from .align import (
    levenshtein_alignment,
    needleman_wunsch_gotoh_alignment,
    needleman_wunsch_gotoh_score,
    smith_waterman_gotoh_alignment,
    smith_waterman_gotoh_score,
)

__all__ = [
    "needleman_wunsch_gotoh_alignment",
    "smith_waterman_gotoh_alignment",
    "levenshtein_alignment",
]