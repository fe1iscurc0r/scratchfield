"""HW-02 MUSIC DOA 测试：单源/双源/低信噪比/阵元数影响。

验收（工单「射频大脑 HW-02」）：
- 单源高 SNR：误差 < 0.5°（M=8, K=200, SNR=20dB，多角度遍历）
- 双源分离：两源估计均 < 1°（±20°, M=8, K=500, SNR=20dB）
- 低 SNR（0dB）：仍可测向，误差 < 3°（M=8, K=500）
- 阵元数影响：M=16 显著优于 M=4（10 种子均值，SNR=10dB）
- MUSIC 超分辨：10° 间隔（低于瑞利限 ~14°）仍可分辨
- MDL 信号源数估计正确（1/2/3 源）
- 数学 sanity：导向矢量落在信号子空间、谱峰在真方向
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.doa import (
    estimate_doa,
    estimate_n_sources_mdl,
    sample_covariance,
    synthesize_snapshots,
    ula_steering_vector,
)


# --------------------------------------------------------------------------- #
# 单源
# --------------------------------------------------------------------------- #
def test_single_source_accuracy():
    """单源高 SNR：多个真方向误差 < 0.5°。"""
    for doa_true in (-40.0, 0.0, 30.0, 60.0):
        x = synthesize_snapshots([doa_true], n_snapshot=200, snr_db=20.0, seed=42)
        est = estimate_doa(x, n_sources=1)
        err = abs(float(est.doas_deg[0]) - doa_true)
        print(f"θ={doa_true:+.0f}° → est={float(est.doas_deg[0]):+.3f}° err={err:.3f}°")
        assert err < 0.5, f"θ={doa_true}° err={err:.3f}° 超容差"


def test_spectrum_peak_at_true_doa():
    """空间谱最大峰应落在真方向（sanity）。"""
    doa_true = -25.0
    x = synthesize_snapshots([doa_true], n_snapshot=200, snr_db=20.0, seed=42)
    est = estimate_doa(x, n_sources=1)
    peak_grid = float(est.grid_deg[np.argmax(est.spectrum)])
    assert abs(peak_grid - doa_true) < 1.0


# --------------------------------------------------------------------------- #
# 双源
# --------------------------------------------------------------------------- #
def test_two_sources_separated():
    """双源 ±20°：两源估计均 < 1°。"""
    true = np.array([-20.0, 20.0])
    x = synthesize_snapshots(true, n_snapshot=500, snr_db=20.0, seed=7)
    est = estimate_doa(x, n_sources=2)
    assert len(est.doas_deg) == 2, f"峰数不足: {est.doas_deg}"
    err = np.abs(np.sort(est.doas_deg) - np.sort(true))
    print(f"true={true} est={np.sort(est.doas_deg)} err={err}")
    assert np.all(err < 1.0)


def test_music_super_resolution_below_rayleigh():
    """超分辨：10° 间隔 < M=8 ULA 瑞利限(~14°)，仍可分辨两源。"""
    true = np.array([-5.0, 5.0])
    x = synthesize_snapshots(true, n_snapshot=1000, snr_db=25.0, seed=9)
    est = estimate_doa(x, n_sources=2)
    assert len(est.doas_deg) == 2, f"10° 间隔未分辨: {est.doas_deg}"
    err = np.abs(np.sort(est.doas_deg) - np.sort(true))
    print(f"true={true} est={np.sort(est.doas_deg)} err={err}")
    assert np.all(err < 2.0)


# --------------------------------------------------------------------------- #
# 低信噪比
# --------------------------------------------------------------------------- #
def test_low_snr_single_source():
    """SNR=0dB：单源仍可测向，误差 < 3°。"""
    x = synthesize_snapshots([30.0], n_snapshot=500, snr_db=0.0, seed=123)
    est = estimate_doa(x, n_sources=1)
    err = abs(float(est.doas_deg[0]) - 30.0)
    print(f"SNR=0dB err={err:.3f}°")
    assert err < 3.0


# --------------------------------------------------------------------------- #
# 阵元数影响
# --------------------------------------------------------------------------- #
def test_more_elements_reduce_error():
    """阵元数越多误差越小：err(M=4) > err(M=8) > err(M=16)，10 种子均值。"""
    errs = {}
    for m_elem in (4, 8, 16):
        per_seed = []
        for seed in range(10):
            x = synthesize_snapshots([30.0], n_elements=m_elem, n_snapshot=300, snr_db=10.0, seed=seed)
            est = estimate_doa(x, n_sources=1)
            per_seed.append(abs(float(est.doas_deg[0]) - 30.0))
        errs[m_elem] = float(np.mean(per_seed))
        print(f"M={m_elem}: 10 种子均值误差 {errs[m_elem]:.3f}°")
    assert errs[4] > errs[8] > errs[16], f"阵元数趋势异常: {errs}"
    assert errs[16] < 1.0, f"M=16 误差应 < 1°: {errs[16]:.3f}°"


# --------------------------------------------------------------------------- #
# MDL 源数估计
# --------------------------------------------------------------------------- #
def test_mdl_source_count():
    """MDL 源数估计：1/2/3 源均正确。"""
    for n_src, seed in ((1, 1), (2, 2), (3, 3)):
        doas = np.linspace(-30.0, 30.0, n_src)  # 均匀间隔 30°
        x = synthesize_snapshots(doas, n_snapshot=400, snr_db=15.0, seed=seed)
        est = estimate_n_sources_mdl(x)
        print(f"n_src={n_src} doas={doas} → MDL={est}")
        assert est == n_src


# --------------------------------------------------------------------------- #
# 数学 sanity
# --------------------------------------------------------------------------- #
def test_noise_subspace_orthogonal_to_steering():
    """真方向导向矢量应几乎落在信号子空间（与噪声子空间正交）。"""
    doa_true = 30.0
    x = synthesize_snapshots([doa_true], n_snapshot=200, snr_db=20.0, seed=42)
    eigvals, eigvecs = np.linalg.eigh(sample_covariance(x))
    noise_subspace = eigvecs[:, :7]  # M-1 个最小特征向量
    a = ula_steering_vector([doa_true], 8).ravel()
    proj_norm2 = float(np.sum(np.abs(noise_subspace.conj().T @ a) ** 2))
    print(f"||U_n^H a(θ_true)||² = {proj_norm2:.2e}")
    assert proj_norm2 < 1e-3


def test_invalid_n_sources_raises():
    """D >= M 非法输入应报错（fail-fast）。"""
    x = synthesize_snapshots([10.0], n_elements=8, n_snapshot=100, snr_db=20.0, seed=42)
    with pytest.raises(ValueError):
        estimate_doa(x, n_sources=8)


if __name__ == "__main__":
    test_single_source_accuracy()
    test_spectrum_peak_at_true_doa()
    test_two_sources_separated()
    test_music_super_resolution_below_rayleigh()
    test_low_snr_single_source()
    test_more_elements_reduce_error()
    test_mdl_source_count()
    test_noise_subspace_orthogonal_to_steering()
    test_invalid_n_sources_raises()
    print("\nHW-02 MUSIC DOA 测试全部通过")
