"""K687/K415 验收测试：CoT token 显著性压缩 + SemKV 语义混合精度量化。"""
from __future__ import annotations

import numpy as np

from tools.cot_token_saliency import compress, saliency_retention, token_saliency
from tools.semkv_quantize import (
    mem_bytes,
    mixed_precision_quantize,
    recon_error,
    semantic_importance,
)


def test_cot_compression_retention():
    """压缩 ≥50% token 时显著性保留率 ≥90%。"""
    rng = np.random.default_rng(0)
    n, d = 64, 16
    embeds = rng.standard_normal((n, d))
    # 少量「答案 token」沿 answer 方向（高显著性），大量「推理 token」随机（低显著）
    answer = rng.standard_normal(d)
    embeds[:8] = answer + 0.1 * rng.standard_normal((8, d))
    sal = token_saliency(embeds, answer)
    kept = compress(sal, budget=n // 2)          # 50% 预算
    assert kept.size == n // 2
    assert saliency_retention(sal, kept) >= 0.90


def test_cot_compression_keeps_high_saliency():
    rng = np.random.default_rng(1)
    n, d = 32, 8
    embeds = rng.standard_normal((n, d))
    answer = rng.standard_normal(d)
    embeds[:4] = answer + 0.01 * rng.standard_normal((4, d))
    sal = token_saliency(embeds, answer)
    kept = compress(sal, budget=4)
    assert set(kept.tolist()) == {0, 1, 2, 3}   # 高显著 token 全保留


def test_semkv_memory_reduction_and_error():
    """内存压缩 ≥50% 且重建误差有界。"""
    rng = np.random.default_rng(0)
    n, d = 128, 32
    kv = rng.standard_normal((n, d))
    query = rng.standard_normal(d)
    imp = semantic_importance(kv, query)
    kv_q, tags = mixed_precision_quantize(kv, imp, high_bits=32, low_bits=8, top_ratio=0.2)
    # 内存：高精度 20%×32bit + 低精度 80%×8bit，vs 全 32bit
    assert mem_bytes(tags, d) < 0.5 * (n * d * 32 // 8)
    # 高重要性 KV 重建误差小（保高精度）
    high_mask = tags == 1
    assert recon_error(kv[high_mask], kv_q[high_mask]) < 0.01


def test_semkv_importance_scores():
    rng = np.random.default_rng(2)
    kv = rng.standard_normal((16, 8))
    query = rng.standard_normal(8)
    imp = semantic_importance(kv, query)
    assert imp.shape == (16,)
    assert np.isfinite(imp).all()
