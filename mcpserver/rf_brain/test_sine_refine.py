"""工单256 任务A 的测试：正弦频率精修（离线、确定性）。

跑法（仓库根）：
    python -m pytest mcpserver/rf_brain/test_sine_refine.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mcpserver.rf_brain import sine_refine as sr


def test_refined_rmse_strictly_better_than_fft() -> None:
    """★ 硬断言：两音间隔 < 1.5 bin 时，精修后的频率 RMSE **严格小于** FFT 峰值法。"""
    sig, fs = sr.build_demo_signal()
    rep = sr.refine_tones(sig, fs, n_tones=len(sr.DEMO_TRUE_HZ),
                          true_freqs_hz=list(sr.DEMO_TRUE_HZ))
    assert rep.rmse_fft is not None and rep.rmse_refined is not None
    assert rep.rmse_refined < rep.rmse_fft, (
        f"精修 RMSE {rep.rmse_refined:.6f} 未严格小于 FFT 基线 {rep.rmse_fft:.6f}")
    # 同时要求量级上的改善（不是"刚好小一点点"）
    assert rep.rmse_refined < rep.rmse_fft * 0.1


def test_deterministic_bitwise() -> None:
    """同一输入两次调用，结果逐位一致（工单硬要求）。"""
    sig, fs = sr.build_demo_signal()
    a = sr.refine_tones(sig, fs, n_tones=2, true_freqs_hz=list(sr.DEMO_TRUE_HZ)).as_dict()
    b = sr.refine_tones(sig, fs, n_tones=2, true_freqs_hz=list(sr.DEMO_TRUE_HZ)).as_dict()
    assert a == b


def test_signal_generation_deterministic() -> None:
    s1, fs1 = sr.build_demo_signal()
    s2, fs2 = sr.build_demo_signal()
    assert fs1 == fs2
    assert np.array_equal(s1, s2)


def test_seeds_do_not_use_truth() -> None:
    """初值必须来自 FFT：给不给真值，初值/收敛路径都不能变。

    这是工单纪律 1（不许用真值初始化）的可执行版本。
    """
    sig, fs = sr.build_demo_signal()
    without = sr.refine_tones(sig, fs, n_tones=2)
    with_truth = sr.refine_tones(sig, fs, n_tones=2, true_freqs_hz=[100.0, 101.2])
    assert without.seeds_hz == with_truth.seeds_hz
    assert [t.freq_hz for t in without.tones] == [t.freq_hz for t in with_truth.tones]
    assert without.iterations == with_truth.iterations
    # 只有 RMSE 字段该被真值影响
    assert without.rmse_fft is None and with_truth.rmse_fft is not None


def test_convergence_curve_decreasing() -> None:
    """收敛曲线：最后一次的最大频率改动必须显著小于第一次（确实在收敛）。"""
    sig, fs = sr.build_demo_signal()
    rep = sr.refine_tones(sig, fs, n_tones=2)
    assert len(rep.convergence) == rep.iterations
    assert rep.convergence[-1] < rep.convergence[0] * 0.5
    # 迭代次数不得超上限
    assert rep.iterations <= sr.DEFAULT_MAX_ITER


def test_max_iter_respected() -> None:
    sig, fs = sr.build_demo_signal()
    rep = sr.refine_tones(sig, fs, n_tones=2, max_iter=2, freq_tol_hz=0.0)
    assert rep.iterations == 2


def test_loose_tolerance_stops_early() -> None:
    """把容差放到很松，应在第一次迭代后立刻收敛。"""
    sig, fs = sr.build_demo_signal()
    rep = sr.refine_tones(sig, fs, n_tones=2, freq_tol_hz=10.0)
    assert rep.iterations == 1


def test_single_tone_on_bin_bin_recovers_exactly() -> None:
    """单音正好在 bin 上 ⇒ 精修误差应远小于一个 bin。"""
    fs, n = 1000.0, 512
    t = np.arange(n, dtype=float) / fs
    f0 = 10 * fs / n                     # 正好第 10 个 bin
    sig = np.cos(2.0 * math.pi * f0 * t)
    rep = sr.refine_tones(sig, fs, n_tones=1, true_freqs_hz=[f0])
    assert abs(rep.tones[0].freq_hz - f0) < fs / n * 0.05
    assert rep.tones[0].amplitude == pytest.approx(1.0, abs=0.02)


def test_invalid_arguments() -> None:
    sig, fs = sr.build_demo_signal()
    with pytest.raises(ValueError):
        sr.refine_tones(sig, fs, n_tones=0)
    with pytest.raises(ValueError):
        sr.fft_peak_seeds(sig, fs, n_tones=10 ** 6)


def test_cli_demo_prints_required_keys(capsys) -> None:
    """验收 1 的口径：--demo 输出里必须有 rmse_fft / rmse_refined / iterations。"""
    assert sr.main(["--demo"]) == 0
    out = capsys.readouterr().out
    for key in ("rmse_fft", "rmse_refined", "iterations"):
        assert key in out, f"缺少 {key}"


def test_cli_json(capsys) -> None:
    import json
    assert sr.main(["--demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "tones" in payload and "convergence_hz" in payload
    assert len(payload["tones"]) == len(sr.DEMO_TRUE_HZ)
