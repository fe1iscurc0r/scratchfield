"""K23 验收测试：多速率 SSM→PDM 音频 DSP（1-bit 编码 + 包络重建 + 预算对比）。

运行：python -m pytest tools/test_multirate_ssm_pdm.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from multirate_ssm_pdm import (
    budget,
    cic_decimate,
    multirate_ssm,
    pdm_encode,
    pdm_encode2,
    reconstruction_snr,
    ssm_lowpass,
)

FS = 100_000.0   # PDM 高速率
DECIM = 200      # 降采样 200× → 500 Hz 低速率
N = int(FS) // 10  # 0.1 s


def _analog_signal():
    t = np.arange(N) / FS
    # 两个低频音 + 直流，幅度 < 1 防 Σ-Δ 积分溢出
    return 0.30 * np.sin(2 * np.pi * 50 * t) + 0.20 * np.sin(2 * np.pi * 120 * t) + 0.10


def test_pdm_encode_is_1bit():
    x = _analog_signal()
    bits = pdm_encode(x)
    assert set(np.unique(bits)) <= {-1.0, 1.0}
    assert bits.shape == x.shape


def test_pdm_encode2_is_1bit_and_higher_snr():
    """二阶 Σ-Δ 仍是 1-bit，配高阶 CIC 后重建 SNR 显著高于一阶（噪声整形更陡）。"""
    x = _analog_signal()
    bits2 = pdm_encode2(x)
    assert set(np.unique(bits2)) <= {-1.0, 1.0}
    # 正确配对：一阶 SDM + sinc^1 vs 二阶 SDM + sinc^2
    snr1 = reconstruction_snr(cic_decimate(pdm_encode(x), DECIM, order=1), cic_decimate(x, DECIM, order=1))
    snr2 = reconstruction_snr(cic_decimate(bits2, DECIM, order=2), cic_decimate(x, DECIM, order=2))
    assert snr2 > snr1 + 10.0, f"二阶 {snr2:.1f} dB 未显著高于一阶 {snr1:.1f} dB"


def test_multirate_recovers_signal_with_high_snr():
    """PDM→CIC 重建 vs 理想（无 PDM 噪声）CIC 降采样：量化噪声残留应很小。"""
    x = _analog_signal()
    est = cic_decimate(pdm_encode(x), DECIM)   # PDM → PCM
    ref = cic_decimate(x, DECIM)               # 理想降采样（无量化噪声）
    snr = reconstruction_snr(est, ref)
    assert snr > 30.0, f"重建 SNR {snr:.1f} dB 过低"


def test_ssm_lowpass_finite_and_stable():
    x = cic_decimate(_analog_signal(), DECIM)
    out = ssm_lowpass(x, alpha=0.2)
    assert np.all(np.isfinite(out))
    assert out.shape == x.shape


def test_multirate_uses_less_state_than_single_rate():
    b = budget(FS, DECIM)
    assert b["multirate_state_bytes"] < b["single_rate_state_bytes"]
    assert b["memory_ratio"] < 1.0
    assert b["ssm_params_per_stage"] == 2


def test_budget_improves_with_decimation():
    b1 = budget(FS, decim=50)
    b2 = budget(FS, decim=500)
    # 降采样越大，低速率状态越小 → 多速率内存占比越低
    assert b2["memory_ratio"] < b1["memory_ratio"]
