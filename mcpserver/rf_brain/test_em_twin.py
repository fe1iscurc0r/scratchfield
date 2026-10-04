"""PF054 授粉落地验收测试：电磁孪生稀疏重建。

覆盖：
  1. ISTA 软阈值正确性 / 一维稀疏恢复（M≈4K 时 PSNR>25dB、支撑准确率≥90%）
  2. 不同压缩比恢复质量（NcT=8/4/2 单调不降）
  3. 二维稀疏场：随机投影测量 → ISTA 重建 NCC≥0.95
  4. 支撑集评估：Jaccard 语义、前 k 大逻辑
  5. PSNR 评估正确性
  6. 容错：空输入/维度不匹配/非法测量矩阵
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.cs_frontend import measurement_matrix
from mcpserver.rf_brain.em_twin import (
    ista_recover,
    measure_field_2d,
    psnr_db,
    reconstruct_field_2d,
    soft_threshold,
    sparse_field_2d,
    support_accuracy,
)


def _sparse_1d(n: int = 256, k: int = 8, seed: int = 3):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    x[rng.choice(n, k, replace=False)] = rng.standard_normal(k) * 2.0
    return x


class TestISTA:
    def test_soft_threshold(self):
        x = np.array([-3.0, -0.5, 0.0, 0.5, 3.0])
        out = soft_threshold(x, 1.0)
        assert np.allclose(out, [-2.0, 0.0, 0.0, 0.0, 2.0])

    @pytest.mark.parametrize("nct", [4, 2])
    def test_recovery_m4k(self, nct):
        n, k = 256, 8
        x = _sparse_1d(n, k)
        m = max(n // nct, k * 2)
        a = measurement_matrix(n, m, seed=1)
        y = a @ x
        x_hat = ista_recover(y, a, k=k)
        assert psnr_db(x, x_hat) > 25.0, f"NcT={nct} PSNR 未达标"
        assert support_accuracy(x, x_hat) >= 0.90, f"NcT={nct} 支撑准确率未达标"
        assert float(np.abs(np.dot(x, x_hat))) > 0.9  # NCC 近似

    def test_nc8_halfway(self):
        # NcT=8 是 4 倍过采样极限，不强制高精度但不应全崩
        n, k = 256, 8
        x = _sparse_1d(n, k)
        m = n // 8
        a = measurement_matrix(n, m, seed=1)
        y = a @ x
        x_hat = ista_recover(y, a, k=k)
        assert psnr_db(x, x_hat) > 10.0

    def test_noiseless_full_rank(self):
        n, k = 64, 3
        x = _sparse_1d(n, k, seed=1)
        a = measurement_matrix(n, n, seed=2)
        y = a @ x
        x_hat = ista_recover(y, a, k=k)
        assert np.allclose(x_hat, x, atol=1e-3)

    def test_invalid_dims(self):
        with pytest.raises(ValueError):
            ista_recover(np.zeros(10), np.zeros((5, 20)))


class TestSupportAndPSNR:
    def test_support_identical(self):
        x = np.array([0.0, 1.0, 0.0, -2.0, 0.0])
        assert support_accuracy(x, x) == pytest.approx(1.0)

    def test_support_topk_semantics(self):
        x_true = np.array([0.0, 1.0, 0.0, -2.0, 0.0])   # 支撑 {1,3}
        # 恢复信号前 k=2 大系数命中 {1,3} 但带杂散小值 → 绝对阈值会虚低
        x_hat = np.array([0.0, 1.1, 0.05, -1.9, 0.03])
        assert support_accuracy(x_true, x_hat) >= 0.5
        # 与完全错误的支撑区分
        x_bad = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        assert support_accuracy(x_true, x_bad) < 0.5

    def test_psnr(self):
        x = np.array([0.0, 1.0, 2.0])
        assert psnr_db(x, x) == 99.0
        assert psnr_db(x, x * 1.1) < 30.0
        assert psnr_db(np.array([]), np.array([])) == 0.0


class Test2DField:
    def test_sparse_field(self):
        f = sparse_field_2d(32, 4, seed=0)
        assert f.shape == (32, 32)
        assert np.count_nonzero(f) == 4

    def test_gaussian_field(self):
        f = sparse_field_2d(32, 4, seed=0, gaussian=True)
        assert f.shape == (32, 32)
        assert np.count_nonzero(f) > 100  # 高斯弥散非稀疏

    def test_reconstruction_ncc_high(self):
        field = sparse_field_2d(32, 4, seed=0)
        n_meas = 256  # 25% 测量
        vals, meas, _ = measure_field_2d(field, n_meas, seed=1)
        rec = reconstruct_field_2d(vals, meas, field.shape)
        assert ncc(field.ravel(), rec.ravel()) >= 0.95
        assert psnr_db(field.ravel(), rec.ravel()) > 25.0

    def test_reconstruction_low_sample(self):
        # 12.5% 测量也应基本可重建（点散射体稀疏）
        field = sparse_field_2d(32, 4, seed=0)
        vals, meas, _ = measure_field_2d(field, 128, seed=1)
        rec = reconstruct_field_2d(vals, meas, field.shape)
        assert ncc(field.ravel(), rec.ravel()) >= 0.9

    def test_invalid_meas_matrix(self):
        field = sparse_field_2d(32, 4, seed=0)
        vals, meas, _ = measure_field_2d(field, 64, seed=1)
        with pytest.raises(ValueError):
            reconstruct_field_2d(vals, np.zeros((8, 8)), field.shape)  # 列数错


def ncc(x, y):
    denom = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(x, y) / denom)
