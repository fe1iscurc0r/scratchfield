"""链路可靠度动态聚类：按阈值把邻居链路分高/中/低三档，映射编码冗余率。

每轮 re-cluster（无状态，直接对当前可靠度表重算），链路质量变化后分组随之迁移。
冗余率映射（可配）：
  - high → 0.0（强链路零冗余，不浪费带宽）
  - mid  → 0.3
  - low  → 0.6（弱链路高冗余抗丢包）
"""
from __future__ import annotations

HIGH = "high"
MID = "mid"
LOW = "low"

DEFAULT_HIGH_THRESHOLD = 0.8
DEFAULT_LOW_THRESHOLD = 0.5

DEFAULT_REDUNDANCY_FACTOR = {HIGH: 0.0, MID: 0.3, LOW: 0.6}


class ReliabilityClusterer:
    """阈值三档聚类器（高/中/低），阈值与冗余率可配。"""

    def __init__(self, high_threshold: float = DEFAULT_HIGH_THRESHOLD,
                 low_threshold: float = DEFAULT_LOW_THRESHOLD,
                 redundancy_factor: dict[str, float] | None = None) -> None:
        if not (0.0 <= low_threshold <= high_threshold <= 1.0):
            raise ValueError("阈值须满足 0 <= low <= high <= 1")
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.redundancy_factor = redundancy_factor or dict(DEFAULT_REDUNDANCY_FACTOR)

    def classify(self, reliability: float) -> str:
        """单条链路可靠度 → 档位（high/mid/low）。"""
        if reliability >= self.high_threshold:
            return HIGH
        if reliability >= self.low_threshold:
            return MID
        return LOW

    def cluster(self, reliabilities: dict[str, float]) -> dict[str, str]:
        """整表重分组：{peer: reliability} → {peer: class}；空表返回空 dict。"""
        return {peer: self.classify(r) for peer, r in reliabilities.items()}

    def redundancy_for(self, peer_class: str) -> float:
        """档位 → 编码冗余率。未知档位按 low 处理（保守冗余）。"""
        return self.redundancy_factor.get(peer_class, self.redundancy_factor.get(LOW, 0.6))


__all__ = [
    "HIGH",
    "MID",
    "LOW",
    "DEFAULT_HIGH_THRESHOLD",
    "DEFAULT_LOW_THRESHOLD",
    "DEFAULT_REDUNDANCY_FACTOR",
    "ReliabilityClusterer",
]
