"""射频大脑 · 秩特征分布式校准免融合（R69）

授粉自 round3 digest-g3 2608.28214（无标定气体源定位）：用「对传感器缩放/非线性
不变的秩特征」做局部信念估计、再以专家乘积融合，在传感器完全不标定、响应非线性
不一致的情况下实现可靠的分布式源定位——不要求标定、不要求同构硬件，只要求观测
的**相对演化**。

核心机制：
  - 秩特征 = 测量值的**排序**（而非绝对值）。单调（缩放/非线性）变换不改变排序，
    故秩特征对未标定的传感器响应天然不变。
  - 局部信念 = 每个传感器按秩给出一个关于源位置的高斯信念（秩越靠前精度越高）。
  - 专家乘积 = 高斯信念相乘 → 精度加权的质心，即融合定位。

原型（纯 numpy，1D 源定位，可推广到 TDOA/AOA）：
  - synthesize_measurements  传感器 + 未知单调非线性响应 + 噪声
  - mean_fusion              原始值加权质心（被非线性失真）
  - rank_fusion              秩特征 + 专家乘积（对单调非线性不变）
  - localization_error / run_comparison

验收口径：未标定传感器融合定位误差较均值融合降 ≥30%。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "synthesize_measurements",
    "mean_fusion",
    "rank_fusion",
    "localization_error",
    "run_comparison",
]


def synthesize_measurements(
    source_pos: float,
    sensor_pos: np.ndarray,
    *,
    gamma: float = 0.15,
    sigma: float = 0.12,
    noise: float = 0.001,
    seed: int = 0,
) -> np.ndarray:
    """合成未标定传感器测量：y_i = f(A(d_i)) + noise，f(z)=z^γ（共同未知非线性）。

    真实衰减 A(d)=exp(-d²/(2σ²))；传感器共享一个未知的单调压缩/扩张响应 z^γ
    （γ≠1 表示非线性、未标定）。秩（排序）对 γ 不变，原始值则被 γ 失真。
    """
    p = np.asarray(sensor_pos, dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("sensor_pos 必须为非空一维数组")
    d2 = (p - float(source_pos)) ** 2
    A = np.exp(-d2 / (2.0 * sigma ** 2))
    rng = np.random.default_rng(seed)
    return A ** float(gamma) + noise * rng.standard_normal(p.size)


def mean_fusion(sensor_pos: np.ndarray, measurements: np.ndarray) -> float:
    """均值融合：原始测量值加权的质心（对非线性失真敏感）。"""
    y = np.asarray(measurements, dtype=float)
    if y.sum() <= 0.0:
        return float(np.median(sensor_pos))
    return float(np.sum(sensor_pos * y) / np.sum(y))


def rank_fusion(sensor_pos: np.ndarray, measurements: np.ndarray, *, tau: float = 1.5) -> float:
    """秩特征 + 专家乘积融合：按测量值排序，秩指数权重 → 高斯专家乘积质心。

    秩 r_i（1=测量值最高=最近）；局部信念精度 w_i=exp(-(r_i-1)/τ)（最近者精度最高），
    专家乘积 = 精度加权质心。排序对单调（缩放/非线性）变换不变，故免标定。
    """
    y = np.asarray(measurements, dtype=float)
    ranks = np.argsort(np.argsort(-y)) + 1          # 1 = 最高
    w = np.exp(-(ranks - 1) / float(tau))           # 秩 → 专家精度
    return float(np.sum(sensor_pos * w) / np.sum(w))


def localization_error(estimate: float, source_pos: float) -> float:
    return abs(float(estimate) - float(source_pos))


def run_comparison(
    *,
    n_sensors: int = 16,
    gamma: float = 0.15,
    trials: int = 200,
    seed: int = 0,
) -> dict:
    """蒙特卡洛对比：均值融合 vs 秩特征融合的平均定位误差与降幅。"""
    rng = np.random.default_rng(seed)
    source = 0.5
    err_mean, err_rank = [], []
    for _ in range(trials):
        p = np.sort(rng.uniform(0.0, 1.0, n_sensors))
        y = synthesize_measurements(source, p, gamma=gamma, seed=int(rng.integers(1 << 30)))
        err_mean.append(localization_error(mean_fusion(p, y), source))
        err_rank.append(localization_error(rank_fusion(p, y), source))
    em = float(np.mean(err_mean))
    er = float(np.mean(err_rank))
    return {"mean_error": em, "rank_error": er, "reduction": (em - er) / em if em > 0 else 0.0}
