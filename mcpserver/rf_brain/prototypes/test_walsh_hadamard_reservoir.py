"""R66 验收测试：Walsh-Hadamard 储层时序建模（无乘法正交算子）。

覆盖：
  1. fwht：与显式 Hadamard 矩阵乘积一致（±1 正交变换，仅 +/− 运算）
  2. 信道/时序预测：WHT 储层精度 ≥ 基线的 80%（对比 R08 LinearReservoir）
  3. 坏参数拒绝（非 2 的幂长度 / hidden）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_walsh_hadamard_reservoir.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import walsh_hadamard_reservoir as whr
from .spectral_constrained_predictor import LinearReservoir


def _predictable_signal(n: int = 400, seed: int = 0) -> np.ndarray:
    """单正弦 + 小噪声（可预测的时序，用于对比预测精度）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return np.sin(2.0 * np.pi * 0.02 * t) + 0.05 * rng.standard_normal(n)


def _r2(pred: np.ndarray, truth: np.ndarray) -> float:
    p = np.asarray(pred, dtype=float)
    t = np.asarray(truth, dtype=float)
    m = min(p.size, t.size)
    return 1.0 - float(np.mean((p[:m] - t[:m]) ** 2)) / float(np.var(t))


def test_fwht_matches_hadamard_matrix():
    """FWHT 结果与显式 Hadamard 矩阵乘法一致（验证 ±1 正交变换正确性）。"""
    n = 8
    rng = np.random.default_rng(0)
    x = rng.standard_normal(n)
    # 显式 Hadamard 矩阵（Sylvester 构造，±1）
    H = np.ones((1, 1))
    while H.shape[0] < n:
        H = np.block([[H, H], [H, -H]])
    assert np.allclose(whr.fwht(x), H @ x)


def test_wht_reservoir_within_80pct_of_baseline():
    """WHT 储层信道预测精度 ≥ 基线的 80%。"""
    signal = _predictable_signal(seed=0)
    train, test = signal[:300], signal[300:]
    init = test[:20]

    base = LinearReservoir(hidden=32, spectral_radius=0.9, seed=0)
    base.train(train)
    base_pred = base.rollout(init, len(test) - 20)[1:]

    wh = whr.WalshHadamardReservoir(hidden=64, input_scale=0.2, seed=0)
    wh.train(train)
    wh_pred = wh.rollout(init, len(test) - 20)[1:]

    acc_base = max(0.0, _r2(base_pred, test[20:]))
    acc_wh = max(0.0, _r2(wh_pred, test[20:]))
    assert acc_wh >= 0.8 * acc_base, f"WHT 精度 {acc_wh:.3f} 未达基线 {acc_base:.3f} 的 80%"


def test_rejects_bad_params():
    with pytest.raises(ValueError):
        whr.fwht(np.zeros(6))  # 非 2 的幂
    with pytest.raises(ValueError):
        whr.WalshHadamardReservoir(hidden=48)  # 非 2 的幂
