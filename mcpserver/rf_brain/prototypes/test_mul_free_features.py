"""R39 验收测试：乘法免费特征提取原型。

覆盖：
  1. WHT 正交性：wht(wht(x)) = n·x（可逆、无损）
  2. 分类精度：WHT 特征与 FFT 特征精度相当（≥90%）
  3. 零乘法：WHT 周期估算为 0 乘法、仅加减
  4. 长度约束：非 2 的幂长度报错

运行：python -m pytest mcpserver/rf_brain/prototypes/test_mul_free_features.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import mul_free_features as mff


def test_wht_orthogonality():
    x = np.random.default_rng(0).standard_normal(64)
    assert np.allclose(mff.wht(mff.wht(x)), 64 * x)


def test_classification_accuracy():
    n = 64
    X, y = mff.synthesize_signals(3, n, seed=0)
    rng = np.random.default_rng(1)
    perm = rng.permutation(X.shape[0])
    X, y = X[perm], y[perm]
    X_tr, y_tr, X_te, y_te = X[:60], y[:60], X[60:], y[60:]
    acc_wht = mff.classify(mff.wht_features(X_tr), y_tr, mff.wht_features(X_te), y_te)
    acc_fft = mff.classify(mff.fft_features(X_tr), y_tr, mff.fft_features(X_te), y_te)
    assert acc_wht >= 0.9
    assert acc_fft >= 0.9


def test_zero_multiplications():
    c = mff.cycle_estimate(64)
    assert c["wht_multiplies"] == 0
    assert c["wht_adds"] > 0


def test_power_of_two_requirement():
    with pytest.raises(ValueError):
        mff.wht(np.zeros(100))
