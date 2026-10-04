"""射频大脑 · Gauss-Hermite 高斯混合熵（R81）

授粉自 2608.21467v1（Gauss-Hermite Quadrature for Gaussian-Mixture Entropy）：
高斯混合熵无闭式，用 Gauss-Hermite 求积近似——比 Monte Carlo 更稳（确定性节点）。
信号/状态不确定性常用 GMM 建模，熵用于信息量/不确定度估计。

原型（纯 numpy）：gauss_hermite_nodes_weights + gmm_entropy_gh（求积近似）
+ gmm_entropy_mc（Monte Carlo 对照）。
"""
from __future__ import annotations

import numpy as np

__all__ = ["gauss_hermite_nodes_weights", "gmm_entropy_gh", "gmm_entropy_mc"]


def gauss_hermite_nodes_weights(n: int) -> tuple[np.ndarray, np.ndarray]:
    """n 点 Gauss-Hermite 节点与权重（物理学家形式）。"""
    x, w = np.polynomial.hermite.hermgauss(n)
    return x, w


def gmm_entropy_gh(means: np.ndarray, stds: np.ndarray, weights: np.ndarray, n: int = 32) -> float:
    """Gauss-Hermite 求积近似 GMM 微分熵 H = -Σ π_i ∫ N(x;μ_i,σ_i) log p(x) dx。

    对每个分量在自身 (μ_i, σ_i) 下用 GH 节点采样，log p 用 logsumexp 计算。
    """
    means = np.asarray(means, dtype=float)
    stds = np.asarray(stds, dtype=float)
    weights = np.asarray(weights, dtype=float)
    x, w = gauss_hermite_nodes_weights(n)
    H = 0.0
    for mu, sig, pi in zip(means, stds, weights):
        pts = mu + np.sqrt(2.0) * sig * x                    # 变换到该分量坐标
        logp = np.log(np.sum(weights[:, None] * _norm_pdf(pts[None, :], means[:, None], stds[:, None]), axis=0))
        H -= pi * float(np.sum(w * logp) / np.sqrt(np.pi))
    return H


def _norm_pdf(x: np.ndarray, mu: np.ndarray, sig: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * ((x - mu) / sig) ** 2) / (sig * np.sqrt(2.0 * np.pi))


def gmm_entropy_mc(means: np.ndarray, stds: np.ndarray, weights: np.ndarray,
                   n_samples: int = 100000, seed: int = 0) -> float:
    """Monte Carlo 对照：从 GMM 采样 → 平均 -log p(x)。"""
    rng = np.random.default_rng(seed)
    k = len(weights)
    comp = rng.choice(k, size=n_samples, p=weights / weights.sum())
    samples = rng.standard_normal(n_samples) * stds[comp] + means[comp]
    logp = np.log(np.sum(weights[:, None] * _norm_pdf(samples[None, :], means[:, None], stds[:, None]), axis=0))
    return float(-np.mean(logp))
