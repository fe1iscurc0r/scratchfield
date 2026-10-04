"""sdr_proc 验收硬线（99号 W99-01 · 合成 IQ 自检）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radio.sdr_proc import (  # noqa: E402
    am_modulate,
    demod_am,
    demod_fm,
    fm_modulate,
    lfm_chirp,
    pulse_compress,
    spectrum_dbm,
)


def test_lfm_pulse_compression_peak():
    """LFM 脉冲压缩尖峰验证：回波（信号+噪声+延迟）经匹配滤波在正确延迟处出尖峰。"""
    rng = np.random.default_rng(0)
    fs, dur, bw = 10_000.0, 0.5, 2000.0
    chirp = lfm_chirp(fs, dur, bw)                 # 5000 样本参考波形

    # 合成回波：先放 3000 样本噪声，再叠入波形，再接噪声
    delay = 3000
    noise = (rng.standard_normal(delay + chirp.size + 2000)
             + 1j * rng.standard_normal(delay + chirp.size + 2000)) * 0.05
    echo = noise.copy()
    echo[delay:delay + chirp.size] += chirp

    out = pulse_compress(echo, chirp)
    peak = int(np.argmax(np.abs(out)))
    # valid 相关下峰值出现在 delay 处
    assert abs(peak - delay) <= 2, f"峰值位置 {peak} 偏离延迟 {delay}"
    assert np.abs(out[peak]) > 10 * np.mean(np.abs(out)), "尖峰不明显"


def test_fm_demod_recovers_sine():
    """FM 解调恢复正弦消息：解调输出与原始消息相关性强。"""
    rng = np.random.default_rng(1)
    fs, dev = 20_000.0, 4000.0
    n = 8000
    t = np.arange(n) / fs
    msg = 0.8 * np.sin(2 * np.pi * 400.0 * t)

    iq = fm_modulate(msg, fs, deviation_hz=dev)
    iq = iq + 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))

    out = demod_fm(iq, fs, deviation_hz=dev, audio_cutoff_hz=2000.0)
    # 对齐（解调输出少 1 样本），用相关系数验证
    o = out[200:-200]
    m = msg[200:200 + o.size]
    assert m.size == o.size
    corr = np.corrcoef(m, o)[0, 1]
    assert corr > 0.9, f"FM 解调相关性过低: {corr:.3f}"


def test_am_demod_recovers_sine():
    """AM 解调恢复正弦消息（包络检波）。"""
    rng = np.random.default_rng(2)
    fs = 40_000.0
    n = 8000
    t = np.arange(n) / fs
    msg = 0.8 * np.sin(2 * np.pi * 300.0 * t)

    iq = am_modulate(msg, fs, carrier_hz=10_000.0)
    iq = iq + 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))

    out = demod_am(iq, fs, audio_cutoff_hz=3000.0)
    o = out[300:-300]
    m = msg[300:300 + o.size]
    assert m.size == o.size
    corr = np.corrcoef(m, o)[0, 1]
    assert corr > 0.9, f"AM 解调相关性过低: {corr:.3f}"


def test_spectrum_visualization_shape():
    """频谱可视化：PSD 频点与 dBm 数组长度对齐、功率量纲合理。"""
    rng = np.random.default_rng(3)
    fs = 20_000.0
    iq = rng.standard_normal(4096) + 1j * rng.standard_normal(4096)
    freqs, dbm = spectrum_dbm(iq, fs)
    assert freqs.size == dbm.size == 4096 // 2 + 1
    assert np.all(np.isfinite(dbm))
    assert freqs[0] == 0.0 and freqs[-1] <= fs / 2


def test_empty_input_rejected():
    """空输入明确报错（不静默）。"""
    with pytest.raises(ValueError):
        spectrum_dbm(np.array([], dtype=complex), 8000.0)
    with pytest.raises(ValueError):
        pulse_compress(np.zeros(10, dtype=complex), np.zeros(20, dtype=complex))
