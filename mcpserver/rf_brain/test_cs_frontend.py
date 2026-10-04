"""PF022 授粉落地验收测试：采样端内嵌压缩（CS-SAR 压缩感知前端模拟）。

覆盖：
  1. 测量矩阵：±1 极性、形状正确、非法参数报错
  2. 压缩-恢复闭环：k-稀疏信号 NcT=4 时 NCC ≥ 0.95（论文指标）
  3. 不同压缩比：NcT=8/4/2 恢复质量单调不降
  4. 带噪测量：轻微噪声下恢复仍可用
  5. OMP 支撑集正确性 / 收敛
  6. 容错：空信号、长度不匹配、非法稀疏度
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.cs_frontend import (
    compress,
    measurement_matrix,
    ncc,
    omp_recover,
    sparse_pulse_signal,
)


class TestMeasurement:
    def test_shape_and_pm1(self):
        a = measurement_matrix(64, 16, seed=0)
        assert a.shape == (16, 64)
        assert np.all(np.isin(a, [-1.0, 1.0]))

    def test_deterministic(self):
        a1 = measurement_matrix(64, 16, seed=3)
        a2 = measurement_matrix(64, 16, seed=3)
        assert np.array_equal(a1, a2)

    def test_invalid_dims(self):
        with pytest.raises(ValueError):
            measurement_matrix(16, 32)  # m > n
        with pytest.raises(ValueError):
            measurement_matrix(16, 0)


class TestCompression:
    def test_compress_length(self):
        n = 128
        x = sparse_pulse_signal(n, 4, seed=0)
        a = measurement_matrix(n, 32, seed=1)
        y = compress(x, a)
        assert y.shape == (32,)

    def test_mismatch_raises(self):
        x = np.zeros(64)
        a = measurement_matrix(128, 32, seed=1)
        with pytest.raises(ValueError):
            compress(x, a)

    def test_zero_signal_compresses(self):
        x = np.zeros(256)
        a = measurement_matrix(256, 64, seed=1)
        assert np.allclose(compress(x, a), 0.0)


class TestRecovery:
    """压缩-恢复闭环（论文核心指标：NcT=4 保 NCC ≥ 0.95）。"""

    @pytest.mark.parametrize("nct", [8, 4, 2])
    def test_ncc_high(self, nct):
        n = 256
        k = 6
        x = sparse_pulse_signal(n, k, seed=0)
        m = max(n // nct, k * 2)
        a = measurement_matrix(n, m, seed=1)
        y = compress(x, a)
        x_hat = omp_recover(y, a, k=k)
        assert ncc(x, x_hat) >= 0.95, f"NcT={nct} NCC 未达标"

    def test_omp_support_size(self):
        n = 128
        k = 5
        x = sparse_pulse_signal(n, k, seed=2)
        a = measurement_matrix(n, 32, seed=1)
        y = compress(x, a)
        x_hat = omp_recover(y, a, k=k)
        assert np.count_nonzero(x_hat) <= k

    def test_noisy_measurement_still_usable(self):
        n = 256
        k = 6
        x = sparse_pulse_signal(n, k, seed=0)
        a = measurement_matrix(n, 64, seed=1)
        rng = np.random.default_rng(5)
        y = compress(x, a) + rng.standard_normal(64) * 0.05
        x_hat = omp_recover(y, a, k=k)
        assert ncc(x, x_hat) >= 0.9, "带噪恢复质量应仍可用"

    def test_recovery_perfect_with_full_rank(self):
        n = 64
        k = 3
        x = sparse_pulse_signal(n, k, seed=0)
        a = measurement_matrix(n, n, seed=1)  # 无压缩，M=N
        y = compress(x, a)
        x_hat = omp_recover(y, a, k=k)
        assert np.allclose(x_hat, x)


class TestNCC:
    def test_identical(self):
        x = np.random.default_rng(0).standard_normal(50)
        assert ncc(x, x) == pytest.approx(1.0)

    def test_orthogonal(self):
        x = np.array([1.0, 0.0])
        y = np.array([0.0, 1.0])
        assert ncc(x, y) == pytest.approx(0.0)

    def test_zero_inputs(self):
        assert ncc(np.zeros(5), np.zeros(5)) == 0.0
        assert ncc(np.zeros(5), np.ones(5)) == 0.0


def test_sparse_signal_valid():
    x = sparse_pulse_signal(100, 7, seed=0)
    assert x.shape == (100,)
    assert np.count_nonzero(x) == 7
    with pytest.raises(ValueError):
        sparse_pulse_signal(100, 0)
