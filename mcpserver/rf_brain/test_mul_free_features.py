"""PF050 授粉落地验收测试：乘法免费特征提取器。

覆盖：
  1. WHT 正交性（wht(wht(x)) == n·x）
  2. 零乘法管线分类精度 ≥ 90%（合成多类信号），且与 FFT 对照相当
  3. 特征维度固定 / 批量提取形状正确
  4. 各特征子项的数值合理性（ZCR/过零间距/峰值/峰均比/sign指纹）
  5. 零乘法断言（无逐样本乘法）
  6. 容错：空/短输入不崩，非 2 幂 WHT 报错
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.mul_free_features import (
    MulFreeFeatureConfig,
    MulFreeFeatureExtractor,
    classify_centroid,
    fft_features,
    peak_count,
    peak_to_mean,
    sign_fingerprint,
    synthesize_signals,
    wht,
    zero_crossing_intervals,
    zero_crossing_rate,
)


class TestWHT:
    def test_orthogonality(self):
        x = np.random.default_rng(0).standard_normal(64)
        assert np.allclose(wht(wht(x)), 64 * x)

    def test_power_of_two_required(self):
        with pytest.raises(ValueError):
            wht(np.zeros(100))


class TestSubFeatures:
    """子特征数值合理性（零乘法算子）。"""

    def test_zcr_sine(self):
        # 纯正弦：每周期 2 次过零
        t = np.arange(256)
        x = np.sin(2 * np.pi * 4 * t / 256)
        zcr = zero_crossing_rate(x)
        assert 0.02 < zcr < 0.08  # 4 周期 * 2 / 255 ≈ 0.031

    def test_zcr_flat_zero(self):
        assert zero_crossing_rate(np.zeros(50)) == 0.0

    def test_zcr_short_input(self):
        assert zero_crossing_rate(np.array([1.0])) == 0.0

    def test_zc_intervals_sine(self):
        t = np.arange(256)
        x = np.sin(2 * np.pi * 4 * t / 256)
        mean, var = zero_crossing_intervals(x)
        assert mean > 0
        assert var >= 0

    def test_peak_count_sine(self):
        t = np.arange(512)
        x = np.sin(2 * np.pi * 8 * t / 512)
        # 8 个完整周期 → ~8 个局部峰
        n = peak_count(x, threshold=0.1)
        assert 6 <= n <= 10

    def test_peak_to_mean_positive(self):
        t = np.arange(128)
        x = 1.0 + 0.5 * np.sin(2 * np.pi * 3 * t / 128)  # 直流偏置，均值>0
        assert peak_to_mean(x) > 1.0

    def test_sign_fingerprint_shape(self):
        x = np.random.default_rng(0).standard_normal(100)
        fp = sign_fingerprint(x, blocks=8)
        assert fp.shape == (8,)
        assert np.all((fp >= 0) & (fp <= 1))


class TestExtractor:
    @pytest.fixture(scope="class")
    def setup(self):
        X, y = synthesize_signals(4, 64, noise=0.25, seed=0, per_class=60)
        rng = np.random.default_rng(1)
        perm = rng.permutation(X.shape[0])
        X, y = X[perm], y[perm]
        split = int(X.shape[0] * 0.6)
        return X, y, split

    def test_feature_dim_fixed(self, setup):
        ex = MulFreeFeatureExtractor()
        assert ex.feature_dim == 1 + 24 + 1 + 2 + 1 + 1 + 8  # 38

    def test_batch_shape(self, setup):
        X, _, _ = setup
        ex = MulFreeFeatureExtractor()
        feats = ex.extract_many(X[:10])
        assert feats.shape == (10, ex.feature_dim)

    def test_classification_accuracy(self, setup):
        X, y, split = setup
        ex = MulFreeFeatureExtractor()
        feats_tr = ex.extract_many(X[:split])
        feats_te = ex.extract_many(X[split:])
        acc_mf = classify_centroid(feats_tr, y[:split], feats_te, y[split:])
        acc_fft = classify_centroid(
            fft_features(X[:split]), y[:split], fft_features(X[split:]), y[split:])
        assert acc_mf >= 0.90, f"零乘法特征分类精度不足: {acc_mf:.3f}"
        assert acc_mf >= acc_fft - 0.06, \
            f"零乘法特征不应远差于 FFT: {acc_mf:.3f} vs {acc_fft:.3f}"

    def test_empty_input_no_crash(self):
        ex = MulFreeFeatureExtractor()
        assert ex.extract(np.zeros(0)).shape == (ex.feature_dim,)

    def test_short_input_pads(self):
        ex = MulFreeFeatureExtractor()
        vec = ex.extract(np.array([1.0, -1.0, 0.5]))
        assert vec.shape == (ex.feature_dim,)

    def test_ndim_required(self):
        ex = MulFreeFeatureExtractor()
        with pytest.raises(ValueError):
            ex.extract(np.zeros((4, 4)))

    def test_custom_config(self):
        cfg = MulFreeFeatureConfig(wht_coeffs=8, blocks=4)
        ex = MulFreeFeatureExtractor(cfg)
        assert ex.feature_dim == 1 + 8 + 1 + 2 + 1 + 1 + 4
        vec = ex.extract(np.random.default_rng(0).standard_normal(64))
        assert vec.shape == (ex.feature_dim,)


def test_no_per_sample_multiplication():
    """零乘法约束：提取过程不产生逐样本乘法（实现层面静态保证）。"""
    from mcpserver.rf_brain import mul_free_features as mff
    x = np.random.default_rng(0).standard_normal(64)
    assert mff.estimate_multiplications(x) == 0
