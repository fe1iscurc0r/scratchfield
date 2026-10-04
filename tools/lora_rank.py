"""工具链 · LoRA 秩选择（R83）

授粉自 2608.26052（How Much Rank Does LoRA Need? Rank-Error Bounds）：把 LoRA
秩选择从「经验试错」变成「有界的」——低秩近似的误差由被丢弃的奇异值谱决定，
据奇异值谱选满足目标误差的最小秩。

原型（纯 numpy）：rank_error_bound 给 r 秩近似的相对误差，select_rank 选最小秩。
"""
from __future__ import annotations

import numpy as np

__all__ = ["rank_error_bound", "select_rank", "low_rank_approx"]


def rank_error_bound(dW: np.ndarray, r: int) -> float:
    """r 秩近似的相对 Frobenius 误差 = Σ_{k>r} σ_k² / Σ σ_k²（被丢弃能量占比）。"""
    w = np.asarray(dW, dtype=float)
    s = np.linalg.svd(w, compute_uv=False)
    total = float(np.sum(s ** 2))
    if total <= 0.0:
        return 0.0
    dropped = float(np.sum(s[r:] ** 2))
    return dropped / total


def low_rank_approx(dW: np.ndarray, r: int) -> np.ndarray:
    """r 秩截断近似（保留前 r 个奇异值）。"""
    w = np.asarray(dW, dtype=float)
    U, s, Vt = np.linalg.svd(w, full_matrices=False)
    s = s.copy()
    s[r:] = 0.0
    return (U * s) @ Vt


def select_rank(dW: np.ndarray, target_error: float) -> int:
    """选满足「相对误差 ≤ target_error」的最小秩（有界秩选择，替代经验试错）。"""
    w = np.asarray(dW, dtype=float)
    s = np.linalg.svd(w, compute_uv=False)
    total = float(np.sum(s ** 2))
    if total <= 0.0:
        return 0
    energy = np.cumsum(s ** 2) / total          # 前 r 个奇异值累计能量占比
    for r in range(1, w.shape[0] + 1):
        if 1.0 - energy[r - 1] <= target_error:
            return r
    return w.shape[0]
