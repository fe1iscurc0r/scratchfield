"""R51 验收测试：计算型射频前传（波域权重映射 → 可调滤波器组 vs 全基带 FFT）。

覆盖：
  1. 特征维度：全基带 FFT（N/2+1 维）vs 滤波器组（M 维，M≪N）
  2. 分类精度损失 ≤10%（滤波器组 ≥ 基线 −10pp），且两者都 ≥85%（有意义检测器）
  3. 基带计算量降 ≥3×
  4. LinearClassifier 二分类 fit/predict
  5. 合成信号类型 / 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/prototypes/test_rf_fronthaul.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import rf_fronthaul as rf


def test_feature_dims_and_reduction():
    x = rf.synthetic_signal("normal", n=512, seed=0)
    p_fft = rf.fft_features(x)
    p_fb = rf.filter_bank_features(x, m_bands=32)
    assert p_fft.shape == (512 // 2 + 1,)
    assert p_fb.shape == (32,)
    # 滤波器组维度远小于全谱（前传的核心：投影降维）
    assert p_fb.size < p_fft.size


def test_compute_reduction_at_least_3x():
    reduction = rf.compute_reduction(512, 32)
    assert reduction >= 3.0
    # 前传基带 MAC 远小于全基带 FFT MAC
    assert rf.digital_macs_fronthaul(32) < rf.digital_macs_baseline(512)


def test_fronthaul_accuracy_loss_within_10pp():
    """计算型前传分类精度损失 ≤10%（且两者都 ≥85%）。"""
    r = rf.run_comparison(n_per_class=200, n=512, m_bands=32, seed=0, noise=0.2)
    assert r.acc_baseline >= 0.85
    assert r.acc_fronthaul >= 0.85
    assert r.acc_loss <= 0.10, f"精度损失 {r.acc_loss:.3f} 超过 10pp"
    assert r.reduction >= 3.0


def test_linear_classifier_fit_predict():
    X = np.array([[0.0], [1.0], [1.0], [0.0]])
    y = np.array([0, 1, 1, 0])
    clf = rf.LinearClassifier().fit(X, y)
    assert clf.accuracy(X, y) == 1.0
    assert set(clf.predict(X).tolist()) <= {0, 1}


def test_synthetic_signal_types_energy_in_expected_band():
    """正常信号能量在允许带，异常信号能量在禁带（判别特征一致）。"""
    x_n = rf.synthetic_signal("normal", n=512, seed=3, noise=0.0)
    x_a = rf.synthetic_signal("forbidden", n=512, seed=4, noise=0.0)
    p_n, p_a = rf.fft_features(x_n), rf.fft_features(x_a)
    lo_a, hi_a = 26, 92        # ALLOWED_BAND 对应 bin
    lo_f, hi_f = 154, 230      # FORBIDDEN_BAND 对应 bin
    assert p_n[lo_a:hi_a].sum() > p_n[lo_f:hi_f].sum()
    assert p_a[lo_f:hi_f].sum() > p_a[lo_a:hi_a].sum()


def test_synthetic_signal_rejects_bad_kind():
    with pytest.raises(ValueError):
        rf.synthetic_signal("bogus", seed=0)
