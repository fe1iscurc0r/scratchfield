"""relation_mixer 测试（K18 验收：吞吐 ≥4× + 质量相当）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from relation_mixer import (
    banded_relation,
    flops_mha,
    flops_relation_mixer,
    mha,
    quality_comparison,
    relation_mixer,
)


def test_throughput_at_least_4x():
    N, d, dk, k = 128, 64, 64, 8
    assert flops_mha(N, d, dk) >= 4.0 * flops_relation_mixer(N, d, k)


def test_banded_relation_row_normalized():
    R = banded_relation(16, k=5)
    assert np.allclose(R.sum(axis=1), 1.0)
    assert np.all(R >= 0.0)


def test_layers_output_shape():
    N, d, dk = 8, 4, 4
    x = np.random.default_rng(0).normal(size=(N, d))
    Wq = Wk = Wv = np.eye(d, dk)
    Wo = np.eye(dk, d)
    R = banded_relation(N, k=3)
    assert mha(x, Wq, Wk, Wv, Wo).shape == (N, d)
    assert relation_mixer(x, R, np.eye(d)).shape == (N, d)


def test_quality_comparable():
    q = quality_comparison(seed=0)
    noise_var = 0.25  # 观测噪声方差；去噪应显著低于此
    assert q["attn"] < noise_var, f"attention 未去噪：MSE {q['attn']:.4f}"
    assert q["rel"] < noise_var, f"relation 未去噪：MSE {q['rel']:.4f}"
    # 质量相当：relation 不得显著劣于 attention（容差）
    assert q["rel"] <= q["attn"] + 0.05, f"relation 显著劣于 attention：{q}"
