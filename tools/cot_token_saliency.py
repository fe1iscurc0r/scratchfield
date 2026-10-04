"""工具链 · CoT token 显著性压缩（K687）

授粉自 2608.31066v1（Every Token Leaves a Ripple）：CoT 推理轨迹里每个 token 对
最终答案的贡献不同，用模型内部 token 显著性（saliency）把长推理轨迹压缩——只保留
高显著性 token，砍掉冗余推理步骤，降低推理 token 成本。

原型（纯 numpy）：token_saliency（显著性评分）+ compress（按预算保留高显著 token）
+ saliency_retention（压缩后显著性质保留率）。

验收口径：压缩 ≥50% token 时显著性质保留率 ≥90%（高价值 token 不被误删）。
"""
from __future__ import annotations

import numpy as np

__all__ = ["token_saliency", "compress", "saliency_retention"]


def token_saliency(embeds: np.ndarray, answer_vec: np.ndarray) -> np.ndarray:
    """token 显著性：每个 token 嵌入与「答案方向」的余弦相似度（越大越关键）。

    真实实现用注意力/梯度内部信号；此处用「对答案向量的投影」作可复现代理。
    """
    e = np.asarray(embeds, dtype=float)
    a = np.asarray(answer_vec, dtype=float)
    denom = np.linalg.norm(e, axis=1) * (np.linalg.norm(a) + 1e-12) + 1e-12
    return e @ a / denom


def compress(saliency: np.ndarray, budget: int) -> np.ndarray:
    """按显著性保留 top-budget 个 token 下标（返回保留下标，升序）。"""
    s = np.asarray(saliency, dtype=float)
    k = min(int(budget), s.size)
    idx = np.argsort(-s)[:k]
    return np.sort(idx)


def saliency_retention(saliency: np.ndarray, kept_idx: np.ndarray) -> float:
    """压缩后显著性保留率 = 保留 token 的显著性质量和 / 全量显著性质量和。"""
    s = np.asarray(saliency, dtype=float)
    total = float(s.sum())
    if total <= 0.0:
        return 1.0
    return float(s[kept_idx].sum() / total)
