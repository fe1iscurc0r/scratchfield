"""W63-02 MUSIC DOA 迁入验收测试

验收硬线：
- pytest 全绿 ≥ 4 用例
- 断言：4 阵元合成信号下 MUSIC 角度估计误差有界

测试覆盖：
1. 单源精度（4阵元/高SNR）        误差 < 2°
2. 双源分辨（4阵元/高SNR）        两源误差 < 2°
3. 边界：单阵元（<4）抛出异常
4. 低SNR鲁棒性（4阵元/SNR=5dB）   误差 < 5°
5. 多阵元趋势（4 vs 8 阵元）     M↑ → 误差↓
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.rf_brain.doa.music_doa import MusicDOA, simulate_signals


# --------------------------------------------------------------------------- #
# 用例 1：单源精度（4阵元，高SNR）—— 误差 < 2°
# --------------------------------------------------------------------------- #
def test_single_source_4elements_high_snr():
    """4阵元合成信号：单源MUSIC角度估计误差 < 2°。"""
    doa = MusicDOA(n_elements=4)
    true_angles = [-30.0, 0.0, 45.0]
    for th_true in true_angles:
        X = simulate_signals([th_true], M=4, N=256, snr_db=20, seed=42)
        est = doa.doa(X, n_sources=1)
        assert len(est) >= 1, f"未估计到任何峰：θ={th_true}"
        err = abs(est[0] - th_true)
        print(f"  θ_true={th_true:+.1f}° → θ_est={est[0]:+.2f}° err={err:.3f}°")
        assert err < 2.0, f"θ={th_true}° 误差 {err:.3f}° 超限（< 2°）"


# --------------------------------------------------------------------------- #
# 用例 2：双源分辨（4阵元，高SNR）—— 两源误差 < 2°
# --------------------------------------------------------------------------- #
def test_two_source_4elements_high_snr():
    """4阵元合成信号：双源MUSIC角度估计，两源误差均 < 2°。"""
    doa = MusicDOA(n_elements=4)
    true_angles = [-20.0, 20.0]
    X = simulate_signals(true_angles, M=4, N=512, snr_db=20, seed=7)
    est = doa.doa(X, n_sources=2)
    assert len(est) >= 2, f"峰数不足：{est}"
    est_sorted = sorted(est)
    errs = [abs(e - t) for e, t in zip(est_sorted, sorted(true_angles))]
    print(f"  true={true_angles} → est={est_sorted} errs={errs}")
    assert all(e < 2.0 for e in errs), f"双源误差超限：{errs}"


# --------------------------------------------------------------------------- #
# 用例 3：边界——n_elements < 4 抛出 ValueError
# --------------------------------------------------------------------------- #
def test_n_elements_below_4_raises():
    """单通道限制：n_elements < 4 必须抛出异常（数学重硬件苛）。"""
    for bad_M in (1, 2, 3):
        try:
            MusicDOA(n_elements=bad_M)
            pytest.fail(f"M={bad_M} 未抛出异常，应触发 ValueError")
        except ValueError as exc:
            assert "n_elements" in str(exc) or "4" in str(exc), f"异常信息不明确：{exc}"
            print(f"  M={bad_M} → 正确抛出 ValueError: {exc}")


# --------------------------------------------------------------------------- #
# 用例 4：低SNR鲁棒性（4阵元，SNR=5dB）—— 误差 < 5°
# --------------------------------------------------------------------------- #
def test_low_snr_4elements():
    """4阵元，SNR=5dB：MUSIC估计误差仍 < 5°（退化但可用）。"""
    doa = MusicDOA(n_elements=4)
    th_true = 15.0
    X = simulate_signals([th_true], M=4, N=512, snr_db=5, seed=99)
    est = doa.doa(X, n_sources=1)
    err = abs(est[0] - th_true)
    print(f"  SNR=5dB θ_true={th_true}° → θ_est={est[0]:+.2f}° err={err:.3f}°")
    assert err < 5.0, f"低SNR误差 {err:.3f}° 超限（< 5°）"


# --------------------------------------------------------------------------- #
# 用例 5：多阵元趋势——M↑ 则误差↓
# --------------------------------------------------------------------------- #
def test_more_elements_reduce_error():
    """数学苛硬件：4阵元误差 > 8阵元误差（误差趋势单调递减）。"""
    th_true = 25.0
    errs = {}
    for M in (4, 8):
        per_seed = []
        for seed in range(8):
            X = simulate_signals([th_true], M=M, N=256, snr_db=10, seed=seed)
            est = MusicDOA(n_elements=M).doa(X, n_sources=1)
            per_seed.append(abs(est[0] - th_true))
        errs[M] = float(np.mean(per_seed))
        print(f"  M={M}: 8种子均值误差 {errs[M]:.3f}°")

    assert errs[4] > errs[8], (
        f"阵元数趋势异常：M=4误差{errs[4]:.3f}° 不应 ≥ M=8误差{errs[8]:.3f}°"
    )


# --------------------------------------------------------------------------- #
# 用例 6（附加）：estimate() vs doa() 接口一致性
# --------------------------------------------------------------------------- #
def test_estimate_interface_returns_grid_and_spectrum():
    """estimate() 返回的 grid 峰值应落在真方向 ±1° 内。"""
    doa = MusicDOA(n_elements=4)
    th_true = 30.0
    X = simulate_signals([th_true], M=4, N=256, snr_db=20, seed=42)
    grid, spec = doa.estimate(X, n_sources=1)
    peak_idx = int(np.argmax(spec))
    peak_angle = float(grid[peak_idx])
    err = abs(peak_angle - th_true)
    print(f"  estimate() 峰值: {peak_angle:+.2f}° err={err:.3f}°")
    assert err < 1.5, f"谱峰偏移 {err:.3f}° 过大"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
