"""Y-04 验收测试：SDR 频谱 / 瀑布图纯计算（radio_suite Web 面板后端）。

覆盖：
  1. compute_spectrum：单音 → 峰值在对应频点、归一化 0 dB、底噪钳位
  2. compute_spectrum：复信号全谱 / 实信号正半边 / 零填充 / 空样本拒绝
  3. downsample：分块均值降采样（长度、均值保真、短序列原样、坏参数拒绝）
  4. Waterfall：滚动缓冲（有界）、下采样出图、空缓冲补底噪、行不足补空
  5. next_spectrum_frame：帧字段完整、频率联动、degraded 标记
  6. synthetic_spectrum_audio：含带内音、有限值、幅度归一化

运行：python -m pytest mcpserver/rf_brain/test_spectrum.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import spectrum as spec
from .device.sim import SimulatedSource

SR = 48_000.0


# ============ 1. compute_spectrum：单音 ============


def _tone(hz: float, n: int, sr: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(n) / sr
    return amp * np.sin(2.0 * np.pi * hz * t)


def test_compute_spectrum_tone_peak_at_freq():
    """1 kHz 单音 → 频谱峰值落在 1 kHz 附近，且峰值 ≈ 0 dB。"""
    x = _tone(1000.0, 4096, SR)
    freqs, db = spec.compute_spectrum(x, SR, fft_size=2048, window="hann")
    assert freqs.shape == db.shape
    peak_idx = int(np.argmax(db))
    assert abs(freqs[peak_idx] - 1000.0) < SR / 2048 * 2  # 峰值落在主瓣内
    assert db[peak_idx] > -3.0  # 峰值近 0 dB（归一化）


def test_compute_spectrum_normalized_and_floor():
    """峰值归一化到 0 dB，且全部 >= db_floor。"""
    x = _tone(1000.0, 4096, SR)
    _, db = spec.compute_spectrum(x, SR, fft_size=1024, db_floor=-80.0)
    assert db.max() <= 0.0 + 1e-9
    assert db.min() >= -80.0


def test_compute_spectrum_real_vs_complex():
    """实信号返回正半边（0..sr/2）；复信号返回全谱（-sr/2..sr/2）。"""
    real = _tone(1000.0, 4096, SR)
    freqs_r, _ = spec.compute_spectrum(real, SR, fft_size=1024)
    assert freqs_r[0] >= -1e-6 and freqs_r[-1] <= SR / 2 + 1e-6

    iq = real + 1j * _tone(1000.0, 4096, SR)
    freqs_c, _ = spec.compute_spectrum(iq, SR, fft_size=1024)
    assert freqs_c[0] < 0 and freqs_c[-1] > 0  # 双边谱
    assert freqs_c.size == 1024 and freqs_r.size == 1024 // 2 + 1


def test_compute_spectrum_zero_pads_short_input():
    """样本不足 fft_size → 零填充，仍返回 fft_size 长谱。"""
    x = _tone(1000.0, 256, SR)
    freqs, db = spec.compute_spectrum(x, SR, fft_size=1024)
    assert freqs.size == 1024 // 2 + 1  # 实信号 rfft
    assert db.size == freqs.size


def test_compute_spectrum_rejects_bad_input():
    """空样本 / 非一维 / 过小 fft_size / 未知窗 → 报错。"""
    with pytest.raises(ValueError):
        spec.compute_spectrum(np.zeros(0), SR)
    with pytest.raises(ValueError):
        spec.compute_spectrum(np.zeros((2, 100)), SR)
    with pytest.raises(ValueError):
        spec.compute_spectrum(_tone(1000.0, 4096, SR), SR, fft_size=4)
    with pytest.raises(ValueError):
        spec.compute_spectrum(_tone(1000.0, 4096, SR), SR, window="bogus")


# ============ 2. downsample ============


def test_downsample_length_and_mean():
    """降采样长度正确，均值近似保真。"""
    x = np.arange(1000, dtype=float)
    y = spec.downsample(x, 100)
    assert y.size == 100
    assert abs(y.mean() - x.mean()) < 1.0


def test_downsample_short_and_identity():
    """短于目标长度原样返回（长度不变）。"""
    x = np.linspace(0, 1, 50)
    assert spec.downsample(x, 100).size == 50


def test_downsample_rejects_bad_target():
    with pytest.raises(ValueError):
        spec.downsample(np.ones(10), 0)
    with pytest.raises(ValueError):
        spec.downsample(np.ones(10), -1)


def test_downsample_empty():
    assert spec.downsample(np.zeros(0), 10).size == 0


# ============ 3. Waterfall ============


def test_waterfall_bounded_and_frame_shape():
    """push 超过 height → 只保留最近 height 行；frame 输出 rows×cols。"""
    wf = spec.Waterfall(height=8)
    for _ in range(12):
        wf.push(np.linspace(0, -60, 64))
    assert wf.count == 8
    img = wf.frame(cols=32)
    assert img.shape == (8, 32)


def test_waterfall_empty_pads_floor():
    """空缓冲 → 全部 db_floor。"""
    wf = spec.Waterfall(height=4, db_floor=-100.0)
    img = wf.frame(cols=16)
    assert img.shape == (4, 16)
    assert np.allclose(img, -100.0)


def test_waterfall_insufficient_rows_pads_top():
    """行不足 → 顶部补 db_floor，最新行在底部。"""
    wf = spec.Waterfall(height=5, db_floor=-90.0)
    wf.push(np.full(16, -30.0))
    wf.push(np.full(16, -10.0))
    img = wf.frame(cols=16)
    assert img.shape == (5, 16)
    assert np.allclose(img[-1], -10.0)  # 最新行在底部
    assert np.allclose(img[0:3], -90.0)  # 顶部补底噪


# ============ 4. next_spectrum_frame ============


def _sim_source(center_hz: float = 7_074_000.0) -> SimulatedSource:
    return SimulatedSource(
        gen_fn=lambda sr, n: spec.synthetic_spectrum_audio(sr, n, seed=7),
        sample_rate=SR,
        duration_s=0.5,
        center_freq_hz=center_hz,
    )


def test_next_spectrum_frame_fields_and_linkage():
    """帧字段完整，freq_hz = center + 偏移，degraded=true（sim 源）。"""
    src = _sim_source(7_074_000.0)
    src.open()
    frame = spec.next_spectrum_frame(src, 7_074_000.0, fft_size=2048, cols=256)
    assert frame["type"] == "spectrum"
    assert frame["center_freq_hz"] == 7_074_000
    assert frame["center_freq_mhz"] == 7.074
    assert frame["cols"] == 256
    assert len(frame["freq_hz"]) == 256
    assert len(frame["spectrum_db"]) == 256
    assert frame["degraded"] is True
    assert frame["source"] == "sim"
    # 频率轴围绕中心频率展开
    assert min(frame["freq_hz"]) >= 7_074_000 - 1
    assert max(frame["freq_hz"]) <= 7_074_000 + SR / 2 + 1
    src.close()


def test_next_spectrum_frame_freq_moves_with_center():
    """切频联动：center 变化 → freq_hz 轴整体平移。"""
    src = _sim_source()
    src.open()
    f1 = spec.next_spectrum_frame(src, 7_074_000.0, cols=128)
    f2 = spec.next_spectrum_frame(src, 14_074_000.0, cols=128)
    assert f2["center_freq_hz"] == 14_074_000
    # 绝对频率轴应整体 +7 MHz
    assert abs(f2["freq_hz"][0] - f1["freq_hz"][0] - 7_000_000) < 1.0
    src.close()


# ============ 5. synthetic_spectrum_audio ============


def test_synthetic_spectrum_audio_finite_and_bounded():
    """合成音频有限值、幅度在 [-1, 1] 内，含能量。"""
    x = spec.synthetic_spectrum_audio(SR, 4096, seed=3)
    assert x.size == 4096
    assert np.all(np.isfinite(x))
    assert np.abs(x).max() <= 1.0
    assert np.abs(x).max() > 0.1  # 有带内音，非纯底噪


def test_synthetic_spectrum_audio_reproduces_peaks():
    """合成音频的频谱确实在带内音偏移处出峰。"""
    x = spec.synthetic_spectrum_audio(SR, 8192, seed=3)
    freqs, db = spec.compute_spectrum(x, SR, fft_size=4096)
    # 500 Hz 音最强，应为全局峰值附近
    peak_idx = int(np.argmax(db))
    assert abs(freqs[peak_idx] - 500.0) < SR / 4096 * 3
