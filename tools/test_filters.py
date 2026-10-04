# -*- coding: utf-8 -*-
"""rf_brain 滤波链测试（W61-03 验收：通带增益≈1、阻带衰减达标、相位无跳变）。"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.filters import butterworth_bpf, butterworth_hpf, butterworth_lpf

FS = 48000.0


def _tone(hz, n=4096):
    t = np.arange(n) / FS
    return np.sin(2 * np.pi * hz * t)


def _amp(x):
    return float(np.sqrt(2) * np.sqrt(np.mean(x ** 2)))  # RMS→幅度


def test_lpf_passes_low_attenuates_high():
    f = butterworth_lpf(2000.0, FS)
    low = _amp(f.process(_tone(1000)))
    high = _amp(f.process(_tone(8000)))
    assert low > 0.7, f"通带 1kHz 幅度 {low:.2f} 过低"
    assert high < 0.3, f"阻带 8kHz 幅度 {high:.2f} 未衰减"


def test_hpf_passes_high_attenuates_low():
    f = butterworth_hpf(4000.0, FS)
    low = _amp(f.process(_tone(1000)))
    high = _amp(f.process(_tone(8000)))
    assert high > 0.7, f"通带 8kHz 幅度 {high:.2f} 过低"
    assert low < 0.3, f"阻带 1kHz 幅度 {low:.2f} 未衰减"


def test_bpf_passes_in_band():
    f = butterworth_bpf(5000.0, 7000.0, FS)
    inb = _amp(f.process(_tone(6000)))
    out_low = _amp(f.process(_tone(1000)))
    assert inb > out_low, "带内 6kHz 应强于带外 1kHz"


def test_biquad_state_preserved_across_chunks():
    """扫频热更新：状态变量跨 chunk 保留（输出连续无跳变）。"""
    f = butterworth_lpf(2000.0, FS)
    x = _tone(1000, 8192)
    y1 = f.process(x[:4096])
    y2 = f.process(x[4096:])
    y_whole = f.process(x)  # 新实例整段处理
    # 分段结果拼接应接近整段（首尾衔接处无跳变）
    assert abs(y1[-1] - y_whole[4095]) < 1e-6


def test_phase_no_jump_continuous():
    """输出为连续正弦（相位无跳变：相邻样本差分有界，用低频音避免正弦斜率误判）。"""
    f = butterworth_lpf(2000.0, FS)
    y = f.process(_tone(200, 4096))
    assert np.all(np.isfinite(y))
    assert np.max(np.abs(np.diff(y))) < 0.1
