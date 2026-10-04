"""射频大脑 · 复域稀疏可分离因子分析（R80）

授粉自 2608.21551v1（Sparse Separable Factor Analysis in the Complex Domain）：
复值阵列（IQ/阵列信号）可分解为「低秩因子 + 稀疏离群」——科学解释依赖幅度/相位
保留。原型用复 SVD 截断做低秩因子恢复（可分离结构），并叠加稀疏残差。

原型（纯 numpy）：complex_factor_analysis 复 SVD 截断 + 稀疏残差；reconstruct。
"""
from __future__ import annotations

import numpy as np

__all__ = ["complex_factor_analysis", "reconstruct", "factor_recovery_error"]


def complex_factor_analysis(X: np.ndarray, r: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """复矩阵 X → 低秩因子 A·B^H + 稀疏残差 S（复 SVD 截断）。"""
    Xc = np.asarray(X, dtype=complex)
    U, s, Vh = np.linalg.svd(Xc, full_matrices=False)
    A = U[:, :r] * s[:r][None, :]                    # (m, r) 复因子
    B = Vh[:r].conj().T                              # (n, r) 复因子
    low_rank = A @ B.conj().T                        # 低秩部分
    S = Xc - low_rank                                # 稀疏残差（复域）
    return A, B, S


def reconstruct(A: np.ndarray, B: np.ndarray, S: np.ndarray) -> np.ndarray:
    return A @ B.conj().T + S


def factor_recovery_error(X: np.ndarray, r: int) -> float:
    """r 秩因子恢复的相对重构误差 = ||X - A·B^H||_F / ||X||_F（稀疏残差占比）。"""
    Xc = np.asarray(X, dtype=complex)
    A, B, S = complex_factor_analysis(Xc, r)
    return float(np.linalg.norm(S) / np.linalg.norm(Xc))
