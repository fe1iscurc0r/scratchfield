"""R80/R81 验收测试：复域因子分析 + Gauss-Hermite 熵。"""
from __future__ import annotations

import numpy as np

from . import complex_factor_analysis as cfa
from . import gauss_hermite_entropy as ghe


def test_complex_factor_recovery():
    rng = np.random.default_rng(0)
    A = rng.standard_normal((16, 2)) + 1j * rng.standard_normal((16, 2))
    B = rng.standard_normal((24, 2)) + 1j * rng.standard_normal((24, 2))
    X = A @ B.conj().T + 1e-3 * (rng.standard_normal((16, 24)) + 1j * rng.standard_normal((16, 24)))
    assert cfa.factor_recovery_error(X, 2) < 0.05          # 秩 2 因子几乎完全恢复


def test_complex_reconstruct_roundtrip():
    rng = np.random.default_rng(0)
    X = rng.standard_normal((8, 8)) + 1j * rng.standard_normal((8, 8))
    A, B, S = cfa.complex_factor_analysis(X, 4)
    assert np.allclose(cfa.reconstruct(A, B, S), X)        # A·B^H + S == X


def test_gauss_hermite_entropy_matches_mc():
    means = np.array([0.0, 3.0])
    stds = np.array([1.0, 1.5])
    weights = np.array([0.5, 0.5])
    h_gh = ghe.gmm_entropy_gh(means, stds, weights, n=32)
    h_mc = ghe.gmm_entropy_mc(means, stds, weights, n_samples=100000, seed=0)
    assert abs(h_gh - h_mc) < 0.1                          # 求积 ≈ MC（0.1 nat 容差）


def test_single_gaussian_entropy_known():
    # 单高斯微分熵 = 0.5·log(2πeσ²)
    sig = 2.0
    h_gh = ghe.gmm_entropy_gh(np.array([0.0]), np.array([sig]), np.array([1.0]), n=32)
    h_true = 0.5 * np.log(2.0 * np.pi * np.e * sig ** 2)
    assert abs(h_gh - h_true) < 0.05
