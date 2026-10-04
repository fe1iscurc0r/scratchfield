"""R05 验收测试：Score-based 轻量频谱检测原型。

覆盖：
  1. 得分模型：统计量非负有限
  2. 检测统计量：强信号 T(x) 显著大于纯噪声
  3. 阈值标定：纯噪声虚警率 ≈ 目标 Pfa
  4. 高 SNR 检测率：多调制在高 SNR 下检测率 ≈ 1
  5. 跨调制泛化：同一噪声训练模型免重训练检测 BPSK/FSK/OOK

运行：python -m pytest mcpserver/rf_brain/prototypes/test_score_detector.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import score_detector as sd


@pytest.fixture(scope="module")
def model():
    return sd.train_score_model(n=32, n_train=1024, seed=0)


def _n(model):
    return model[0].shape[0]


def _sigma(model):
    return model[1]


def test_trained_model_statistic_finite(model):
    x = _sigma(model) * np.random.default_rng(0).standard_normal(_n(model))
    t = sd.score_statistic(x, model)
    assert np.isfinite(t) and t >= 0.0


def test_signal_statistic_larger_than_noise(model):
    rng = np.random.default_rng(42)
    n, sigma = _n(model), _sigma(model)
    noise_stats = [sd.score_statistic(sigma * rng.standard_normal(n), model)
                   for _ in range(200)]
    # 强信号（SNR≈10dB）：能量 = 10·σ²
    s = sd.synthesize_modulations(n, "BPSK", rng=rng) * np.sqrt(10.0) * sigma
    t_sig = sd.score_statistic(s + sigma * rng.standard_normal(n), model)
    assert t_sig > np.quantile(noise_stats, 0.9)


def test_calibrate_threshold_pfa(model):
    pfa = 0.05
    thr = sd.calibrate_threshold(model, pfa=pfa, n_cal=2000, seed=1)
    rng = np.random.default_rng(9)
    n, sigma = _n(model), _sigma(model)
    false_alarms = sum(
        sd.score_statistic(sigma * rng.standard_normal(n), model) > thr
        for _ in range(2000)
    )
    rate = false_alarms / 2000
    assert 0.02 <= rate <= 0.09  # 允许标定噪声，但应接近 5%


def test_detection_rate_high_snr(model):
    for mod in ("BPSK", "QPSK", "FSK", "OOK"):
        pd = sd.detection_rate(model, mod, snr_db=10.0, n_test=300, seed=2)
        assert pd >= 0.95, f"{mod} 高 SNR 检测率过低: {pd}"


def test_cross_modulation_no_retrain(model):
    pd_bpsk = sd.detection_rate(model, "BPSK", snr_db=6.0, n_test=300, seed=3)
    pd_fsk = sd.detection_rate(model, "FSK", snr_db=6.0, n_test=300, seed=4)
    assert pd_bpsk >= 0.8 and pd_fsk >= 0.8
