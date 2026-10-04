"""射频大脑 · 差集 Weyl 信道容量（R122）

授粉自 2608.20726v1（Difference-Set Weyl Channels: Exact Capacity）：差集
Weyl（Heisenberg-Weyl）信道由有限个时频移位算子 {X^a Z^b}_{(a,b)∈S} 张成，
当移位集 S 是差集时信道算子有精确可解的容量。原型构造 Weyl 信道矩阵、算奇异值、
用水注法（water-filling）算容量。

原型（纯 numpy）：weyl_operators / weyl_channel_matrix / channel_capacity。
"""
from __future__ import annotations

import numpy as np

__all__ = ["weyl_operators", "weyl_channel_matrix", "channel_capacity"]


def weyl_operators(d: int) -> tuple[np.ndarray, np.ndarray]:
    """Heisenberg-Weyl 算子：X（循环移位）、Z（相位）。d×d 复矩阵。"""
    X = np.zeros((d, d), dtype=complex)
    for i in range(d):
        X[(i + 1) % d, i] = 1.0
    Z = np.diag(np.exp(2j * np.pi * np.arange(d) / d))
    return X, Z


def weyl_channel_matrix(d: int, shift_set: list[tuple[int, int]]) -> np.ndarray:
    """Weyl 信道矩阵 = Σ_{(a,b)∈S} X^a Z^b（移位集 S 张成的信道算子）。

    直接按 (X^a Z^b)[r,c] = 1[r=(c+a)%d]·ω^{b·c} 构造（避免 matrix_power 的特征分解，
    数值更稳），向量化逐项累加。
    """
    omega = np.exp(2j * np.pi / d)
    H = np.zeros((d, d), dtype=complex)
    r = np.arange(d)
    for a, b in shift_set:
        a, b = a % d, b % d
        c = (r - a) % d                                  # 每行唯一非零列
        H[r, c] += omega ** (b * c)
    return H


def channel_capacity(H: np.ndarray, snr: float) -> float:
    """MIMO 信道容量（水注法）：C = Σ log2(1 + p_i·λ_i·SNR)，p_i 为注水功率。

    无 CSI 发送（等功率）时退化为 Σ log2(1 + λ_i·SNR/d)，此处用奇异值谱水注。
    """
    Hc = np.asarray(H, dtype=complex)
    s = np.linalg.svd(Hc, compute_uv=False)
    lam = s ** 2                                     # 特征值（增益）
    lam = lam[lam > 1e-12]
    if lam.size == 0:
        return 0.0
    # 水注：找到水位 ν 使 Σ max(0, ν - 1/(SNR·λ)) = 1
    inv = 1.0 / (snr * lam)
    lo, hi = 0.0, float(inv.max()) + 1.0
    for _ in range(200):
        nu = 0.5 * (lo + hi)
        if np.sum(np.maximum(nu - inv, 0.0)) > 1.0:
            hi = nu
        else:
            lo = nu
    nu = 0.5 * (lo + hi)
    p = np.maximum(nu - inv, 0.0)
    return float(np.sum(np.log2(1.0 + snr * p * lam)))
