"""工具链 · LoRA-GA² 梯度对齐（R92）

授粉自 2608.19800（LoRA-GA²）：用全量微调梯度（多步平均，GA²=梯度对齐）的 SVD
初始化 LoRA 的 A/B 因子，让低秩更新一开始就沿梯度主方向——比随机初始化收敛更快、
初始损失更低。

原型（纯 numpy）：gradient_alignment 多步梯度平均 + SVD 分解出 A/B；
alignment_score 度量 ΔW 与真梯度的对齐度（余弦相似）；对比随机 init 与 GA init。
"""
from __future__ import annotations

import numpy as np

__all__ = ["gradient_alignment", "alignment_score", "init_lora_dw"]


def gradient_alignment(grads: list[np.ndarray], rank: int) -> tuple[np.ndarray, np.ndarray]:
    """多步梯度平均 → SVD → LoRA 因子 (A, B)，使 B·A ≈ 梯度的 rank 低秩近似。

    梯度 G 形状 (out, in)；A = sqrt(Σ)·V^T (rank×in)，B = U·sqrt(Σ) (out×rank)。
    """
    G = np.mean(np.stack(grads), axis=0)
    U, s, Vt = np.linalg.svd(G, full_matrices=False)
    U = U[:, :rank]
    s = s[:rank]
    Vt = Vt[:rank]
    A = np.sqrt(s)[:, None] * Vt                  # (rank, in)
    B = U * np.sqrt(s)[None, :]                   # (out, rank)
    return A, B


def init_lora_dw(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """LoRA 增量 ΔW = B·A。"""
    return B @ A


def alignment_score(dW: np.ndarray, G: np.ndarray) -> float:
    """ΔW 与真梯度的余弦相似度（越接近 1 越对齐）。"""
    a = np.asarray(dW).ravel()
    b = np.asarray(G).ravel()
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)
