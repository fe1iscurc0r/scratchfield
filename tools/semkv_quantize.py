"""工具链 · SemKV 语义混合精度 KV 缓存量化（K415）

授粉自 2608.28911（SemKV: Semantic Mixed-Precision KV Cache Quantization）：
KV cache 是大模型推理的内存瓶颈——按「语义重要性」分组，低重要性的 KV 用更低
精度量化，高重要性保高精度，兼顾内存压缩与精度。

原型（纯 numpy）：semantic_importance（注意力式评分）+ mixed_precision_quantize
（分档量化）+ 内存/误差度量。

验收口径：内存压缩 ≥50% 时重建误差低于上界（关键 KV 保高精度）。
"""
from __future__ import annotations

import numpy as np

__all__ = ["semantic_importance", "mixed_precision_quantize", "mem_bytes", "recon_error"]


def semantic_importance(kv: np.ndarray, query: np.ndarray) -> np.ndarray:
    """语义重要性：KV 向量与查询的注意力式得分（softmax 前 logits）。"""
    k = np.asarray(kv, dtype=float)
    q = np.asarray(query, dtype=float)
    return k @ q


def mixed_precision_quantize(kv: np.ndarray, importance: np.ndarray, *,
                             high_bits: int = 32, low_bits: int = 8,
                             top_ratio: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """分档量化：高重要性（top_ratio）保 high_bits，其余压到 low_bits。

    返回 (量化后 kv, 精度标签 1=高精度/0=低精度)。量化为 scale+round 均匀量化。
    """
    k = np.asarray(kv, dtype=float)
    n = k.shape[0]
    idx = np.argsort(-np.asarray(importance, dtype=float))
    n_high = max(1, int(n * top_ratio))
    high = idx[:n_high]
    tags = np.zeros(n, dtype=int)
    tags[high] = 1

    out = np.zeros_like(k)
    for group, bits in ((high, high_bits), (idx[n_high:], low_bits)):
        if group.size == 0:
            continue
        g = k[group]
        mn, mx = g.min(), g.max()
        scale = (mx - mn) / (2 ** bits - 1) if mx > mn else 1.0
        q = np.round((g - mn) / max(scale, 1e-12)) * scale + mn
        out[group] = q
    return out, tags


def mem_bytes(tags: np.ndarray, dim: int, high_bits: int = 32, low_bits: int = 8) -> int:
    """量化后内存（字节）= Σ bit 数 / 8。"""
    return int(np.sum(np.where(tags == 1, high_bits, low_bits)) * dim / 8)


def recon_error(kv: np.ndarray, kv_q: np.ndarray) -> float:
    """量化重建相对误差 = ||kv - kv_q||_F / ||kv||_F。"""
    k = np.asarray(kv, dtype=float)
    q = np.asarray(kv_q, dtype=float)
    denom = np.linalg.norm(k) + 1e-12
    return float(np.linalg.norm(k - q) / denom)
