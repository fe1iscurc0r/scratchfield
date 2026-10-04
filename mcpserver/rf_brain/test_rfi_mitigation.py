"""R03 验收测试：RFI 缓解模块（rfi_mitigation）。

覆盖：
  1. notch_filter：单音陷波后残余能量显著下降
  2. butterworth_bandstop：滤除干扰带、保留带外弱信号
  3. adaptive_notch：LMS 自适应对消单音干扰
  4. detect_rfi_narrowband：检出显著窄带干扰频点
  5. detect_rfi_dual_channel：极化域能量比失衡 → RFI mask
  6. mitigate_rfi：合成干扰下 S/N 提升 ≥ 1.5×

运行：python -m pytest mcpserver/rf_brain/test_rfi_mitigation.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import rfi_mitigation as rfi


def _tone(freq_hz: float, sr: float, n: int, amp: float = 1.0) -> np.ndarray:
    t = np.arange(n) / sr
    return amp * np.sin(2.0 * np.pi * freq_hz * t)


def test_notch_filter_removes_tone():
    sr, n, f_int = 4000.0, 8000, 500.0
    x = _tone(f_int, sr, n, amp=1.0)
    y = rfi.notch_filter(x, sr, f_int, bw_hz=50.0)
    # 稳态残余（跳过滤波器起振）应远小于原信号
    assert np.sqrt(np.mean(y[1000:] ** 2)) < 0.1 * np.sqrt(np.mean(x ** 2))


def test_butterworth_bandstop_preserves_offband():
    sr, n = 4000.0, 8000
    f_int, f_sig = 500.0, 800.0
    x = _tone(f_int, sr, n, amp=1.0) + _tone(f_sig, sr, n, amp=0.3)
    y = rfi.butterworth_bandstop(x, sr, f_int, bw_hz=50.0)
    # 干扰带被抑制、带外信号保留
    _, power_in = rfi.power_spectrum(x, sr)
    _, power_out = rfi.power_spectrum(y, sr)
    bin_int = int(f_int / (sr / n))
    bin_sig = int(f_sig / (sr / n))
    assert power_out[bin_int] < power_in[bin_int] * 0.05
    assert power_out[bin_sig] > power_in[bin_sig] * 0.5


def test_adaptive_notch_cancels_tone():
    sr, n, f_int = 4000.0, 8000, 500.0
    x = _tone(f_int, sr, n, amp=1.0)
    y = rfi.adaptive_notch(x, sr, f_int, mu=0.005)
    # LMS 收敛后残余应显著下降
    assert np.sqrt(np.mean(y[-2000:] ** 2)) < 0.15 * np.sqrt(np.mean(x ** 2))


def test_detect_rfi_narrowband():
    sr, n, f_int = 4000.0, 8000, 500.0
    rng = np.random.default_rng(0)
    x = _tone(f_int, sr, n, amp=1.0) + 0.01 * rng.standard_normal(n)
    peaks = rfi.detect_rfi_narrowband(x, sr, prominence_db=20.0)
    assert any(abs(p - f_int) < sr / n * 2 for p in peaks)


def test_detect_rfi_dual_channel():
    sr, n, f_int = 4000.0, 8000, 500.0
    rng = np.random.default_rng(0)
    # 通道 A：强干扰 + 噪声；通道 B：仅噪声（能量失衡 → RFI）
    ch_a = _tone(f_int, sr, n, amp=1.0) + 0.01 * rng.standard_normal(n)
    ch_b = 0.01 * rng.standard_normal(n)
    freqs, mask = rfi.detect_rfi_dual_channel(ch_a, ch_b, sr, imbalance_db=6.0)
    bin_int = int(f_int / (sr / n))
    assert mask[bin_int]


def test_mitigate_rfi_snr_improvement():
    sr, n = 4000.0, 16000
    f_int, f_sig = 500.0, 800.0
    rng = np.random.default_rng(1)
    # 弱信号 + 强窄带干扰 + 小噪声
    s = _tone(f_sig, sr, n, amp=0.1)
    interf = _tone(f_int, sr, n, amp=1.0)
    noise = 0.005 * rng.standard_normal(n)
    x = s + interf + noise

    res = rfi.mitigate_rfi(x, sr, reference=s, prominence_db=20.0)
    assert any(abs(p - f_int) < sr / n * 2 for p in res.detected_freqs_hz)
    assert res.snr_after_db > res.snr_before_db
    assert res.snr_improvement >= 1.5
