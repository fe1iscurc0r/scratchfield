"""射频大脑 · 协议感知特征缓存（R63）

授粉自 round3 digest-g1a PASK（2608.28276，Parser-Aware KV Persistence）：
LLM 结构化输出的 KV 缓存长期忽视「parser 状态的结构语义」，PASK 按任务错误
敏感度设置保护下界、把残余容量分配给高价值状态，0.33 KV 预算下 BFCL 领先
17.39pp、吞吐 2.2×。核心思想 = **把「结构感知」引入缓存决策**。

跨领域落地（ESP32/rf_brain 频谱特征缓存）：
  - 不同频段/协议特征对后续解调的重要性差异巨大：导频/前导码/同步字是关键
    （决定能否锁定、解调、校验），噪声/底噪特征低价值。
  - 协议感知缓存按「解调重要性」分级保留关键信道状态，丢弃低价值噪声特征，
    实现嵌入式 SDR 的内存-精度权衡。

原型（纯 numpy，无新依赖）：
  - demod_importance   频谱 + 协议关键 bin 先验 → 逐 bin 解调重要性
  - ProtocolAwareCache 按重要性排序保留 top-K（缓存容量约束）
  - run_cache_tradeoff  缓存减量 → 关键特征保留率曲线（对比朴素 FIFO/随机）

验收口径：缓存减量 ≥50%（容量 ≤ 总特征一半）时，关键特征保留率 ≥90%。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "demod_importance",
    "ProtocolAwareCache",
    "naive_eviction",
    "run_cache_tradeoff",
    "CacheTradeoffResult",
]


def demod_importance(
    power: np.ndarray,
    *,
    protocol_bins: np.ndarray | None = None,
    noise_floor: float | None = None,
) -> np.ndarray:
    """逐 bin 解调重要性：谱峰显著度（SNR 口径）+ 协议关键 bin 先验加权。

    导频/前导码/同步字所在的 bin 即使不是最强峰，也因「协议先验」获得高重要性——
    这正是 PASK「结构感知」的落点：重要性不是只看能量，还看协议语义。
    """
    p = np.asarray(power, dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("power 必须为非空一维谱")
    floor = float(np.median(p)) if noise_floor is None else float(noise_floor)
    if floor <= 0.0:
        floor = 1e-12
    # 谱峰显著度（相对噪声底，dB 口径映射到 [0,1]）
    snr_db = 10.0 * np.log10(p / floor + 1e-12)
    importance = np.clip(snr_db / 30.0, 0.0, 1.0)          # 归一化显著度
    if protocol_bins is not None:
        pb = np.asarray(protocol_bins, dtype=int)
        importance[pb] = np.maximum(importance[pb], 0.9)   # 协议关键 bin 保底高重要性
    return importance


@dataclass
class CacheTradeoffResult:
    """缓存减量-精度权衡结果。"""
    capacities: list[int]
    aware_retention: list[float]   # 协议感知缓存的保留率曲线
    naive_retention: list[float]   # 朴素缓存（随机淘汰）保留率曲线


class ProtocolAwareCache:
    """按重要性排序保留 top-K 的协议感知特征缓存。"""

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("capacity 不能为负")
        self.capacity = int(capacity)
        self.indices: np.ndarray = np.zeros(0, dtype=int)

    def store(self, importance: np.ndarray) -> np.ndarray:
        """按重要性降序保留前 capacity 个特征下标（返回缓存下标）。"""
        imp = np.asarray(importance, dtype=float)
        k = min(self.capacity, imp.size)
        self.indices = np.argsort(-imp)[:k]
        return self.indices

    def retention(self, critical_mask: np.ndarray) -> float:
        """关键特征（critical_mask=True）被缓存保留下来的比例。"""
        crit = np.asarray(critical_mask, dtype=bool)
        if crit.sum() == 0:
            return 1.0
        return float(np.intersect1d(np.flatnonzero(crit), self.indices).size / crit.sum())


def naive_eviction(n_features: int, capacity: int, seed: int = 0) -> np.ndarray:
    """朴素缓存：随机保留 capacity 个特征（无结构感知，作为对照基线）。"""
    rng = np.random.default_rng(seed)
    return rng.choice(n_features, size=min(capacity, n_features), replace=False)


def run_cache_tradeoff(
    power: np.ndarray,
    protocol_bins: np.ndarray,
    *,
    capacities: list[int] | None = None,
    seed: int = 0,
) -> CacheTradeoffResult:
    """缓存减量 → 关键特征保留率曲线（协议感知 vs 朴素随机）。"""
    p = np.asarray(power, dtype=float)
    n = p.size
    if capacities is None:
        capacities = [int(n * f) for f in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)]
    imp = demod_importance(p, protocol_bins=protocol_bins)
    crit = np.zeros(n, dtype=bool)
    crit[np.asarray(protocol_bins, dtype=int)] = True
    crit_idx = np.flatnonzero(crit)

    aware, naive = [], []
    for cap in capacities:
        kept = ProtocolAwareCache(cap).store(imp)
        aware.append(float(np.intersect1d(crit_idx, kept).size / crit_idx.size))
        kept = naive_eviction(n, cap, seed=seed)
        naive.append(float(np.intersect1d(crit_idx, kept).size / crit_idx.size))
    return CacheTradeoffResult(capacities=list(capacities),
                               aware_retention=aware, naive_retention=naive)
