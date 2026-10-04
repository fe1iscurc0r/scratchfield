"""采集函数：EI / UCB / 随机，在候选点中选择下一个实验点。

约定：目标一律"越大越好"（多目标已在 loop 中标量化）。EI/UCB 均为最大化口径。
"""
from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import numpy as np


def _norm_pdf(z: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * z**2) / np.sqrt(2.0 * np.pi)


def _norm_cdf(z: np.ndarray) -> np.ndarray:
    # numpy 2.x 主命名空间无 np.erf，改用 math.erf 逐元素实现标准正态 CDF。
    erf = np.vectorize(lambda x: math.erf(x / math.sqrt(2.0)))
    return 0.5 * (1.0 + erf(np.asarray(z, dtype=float)))


def expected_improvement(
    mu: np.ndarray, sigma: np.ndarray, y_best: float, xi: float = 0.01
) -> np.ndarray:
    """期望改善（Expected Improvement），最大化口径。

    参数:
        mu, sigma: 代理模型在候选点的预测均值与不确定性。
        y_best: 当前已观测最优目标值。
        xi: 探索-利用平衡项（≥0 鼓励更多探索）。
    """
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        imp = mu - y_best - xi
        z = np.where(sigma > 0, imp / sigma, 0.0)
        ei = np.where(sigma > 0, imp * _norm_cdf(z) + sigma * _norm_pdf(z), 0.0)
    return np.where(ei > 0, ei, 0.0)


def upper_confidence_bound(
    mu: np.ndarray, sigma: np.ndarray, kappa: float = 1.96
) -> np.ndarray:
    """上置信界（Upper Confidence Bound），最大化口径。kappa 越大越偏向探索。"""
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    return mu + kappa * sigma


def random_score(n: int, rng: np.random.Generator | None = None) -> np.ndarray:
    """随机打分（无模型时的冷启动/随机基线）。"""
    rng = rng or np.random.default_rng(0)
    return rng.uniform(size=n)


def recommend(
    surrogate,
    candidates_X: np.ndarray,
    strategy: str = "ei",
    y_best: float | None = None,
    xi: float = 0.01,
    kappa: float = 1.96,
    rng: np.random.Generator | None = None,
    failed_points: np.ndarray | None = None,
    failure_penalty: float = 0.0,
) -> Tuple[int, np.ndarray]:
    """在候选点上打分并返回最优候选的下标与分数向量。

    参数:
        surrogate: 已拟合代理模型（含 predict_with_uncertainty）。
        candidates_X: (n, dim) 候选点编码向量。
        strategy: "ei" | "ucb" | "random"。
        y_best: 当前最优目标（EI 需要；未给则用预测均值上界近似）。
        xi, kappa: EI / UCB 超参。
        rng: 随机源。
        failed_points: (m, dim) 失败实验点，用于给失败邻域加惩罚（映射 1）。
        failure_penalty: 失败邻域惩罚强度（≥0；0 表示不惩罚）。

    返回:
        (best_idx, scores)：最优候选下标 + 每个候选的采集分数。
    """
    rng = rng or np.random.default_rng(0)
    candidates_X = np.asarray(candidates_X, dtype=float)
    n = len(candidates_X)
    if strategy == "random":
        scores = random_score(n, rng)
    else:
        mu, sigma = surrogate.predict_with_uncertainty(candidates_X)
        if strategy == "ei":
            if y_best is None:
                y_best = float(mu.max())
            scores = expected_improvement(mu, sigma, y_best, xi)
        elif strategy == "ucb":
            scores = upper_confidence_bound(mu, sigma, kappa)
        else:
            raise ValueError(f"未知采集策略: {strategy!r}（可选 ei / ucb / random）")

    # 失败实验纳入：给失败点邻域叠加惩罚，压低其采集分数（映射 1）。
    if failure_penalty > 0 and failed_points is not None and len(failed_points) > 0:
        failed = np.asarray(failed_points, dtype=float)
        for fp in failed:
            dist = np.sqrt(((candidates_X - fp) ** 2).sum(axis=1))
            scores = scores - failure_penalty * np.exp(-dist)

    best_idx = int(np.argmax(scores))
    return best_idx, scores
