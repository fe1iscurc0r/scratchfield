"""sdr 信号处理薄封装（W99-01 · mhostetter/sdr 接入）。

依赖：`pip install sdr`（0.0.30，MIT，纯 numpy；本封装只在滤波/量纲处使用 sdr 原语，
其余核心算法（FFT 谱 / LFM 生成 / 匹配滤波 / FM·AM 解调）用 numpy 直写——
sdr 0.0.30 无内置 lfm/matched_filter/fm_demodulate，如实不硬凑）。

暴露 3 个高频场景（IQ numpy 数组输入，与 rf_brain/频谱界面数据层对齐）：
    spectrum_dbm(iq, sample_rate)   → 频谱可视化（PSD 频点/dBm）
    pulse_compress(iq, waveform)    → 匹配滤波（LFM 脉冲压缩尖峰）
    demod_fm(iq, sample_rate, ...) / demod_am(iq, sample_rate, ...) → 解调
"""
from __future__ import annotations

import numpy as np
from sdr import FIR, db, lowpass_fir


def spectrum_dbm(iq: np.ndarray, sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
    """单边 PSD 谱：返回 (freqs_hz, power_dbm)。

    iq: 1D 复数样本；sample_rate: Hz。汉宁窗 FFT + 单边取谱（用复数 fft 而非
    rfft——本机 numpy 2.4.6 的 pocketfft rfft ufunc 有 ABI 缺陷，如实绕开），
    dBm 换算按 50Ω 归一（幅度平方 → dB，再换算 dBm：dBm = dB + 30）。
    """
    x = np.asarray(iq, dtype=complex)
    if x.size == 0:
        raise ValueError("IQ 为空")
    n = x.size
    window = np.hanning(n)
    spec = np.fft.fft(x * window) / (n / 2)
    half = n // 2 + 1
    power_w = np.abs(spec[:half]) ** 2 / 50.0
    power_dbm = db(np.maximum(power_w, 1e-12)) + 30.0
    freqs = np.arange(half) * (sample_rate / n)
    return freqs, power_dbm


def lfm_chirp(sample_rate: float, duration_s: float, bandwidth_hz: float) -> np.ndarray:
    """生成 LFM（线性调频）基带复数脉冲（numpy 直写，sdr 无内置）。"""
    n = int(sample_rate * duration_s)
    t = np.arange(n) / sample_rate
    k = bandwidth_hz / duration_s                    # 调频斜率 Hz/s
    phase = 2 * np.pi * (k / 2.0) * t ** 2
    return np.exp(1j * phase).astype(np.complex128)


def pulse_compress(iq: np.ndarray, waveform: np.ndarray) -> np.ndarray:
    """匹配滤波（脉冲压缩）：返回与参考波形相关的复数输出（峰值位置 = 目标延迟）。"""
    x = np.asarray(iq, dtype=complex)
    w = np.asarray(waveform, dtype=complex)
    if w.size == 0 or x.size < w.size:
        raise ValueError("波形为空或比输入长")
    return np.correlate(x, w, mode="valid")


def _analytic(iq: np.ndarray) -> np.ndarray:
    """实信号 → 解析信号（希尔伯特；用复数 FFT 而非 rfft——本机 numpy rfft ABI 缺陷绕开）。"""
    x = np.asarray(iq, dtype=float)
    n = x.size
    spec = np.fft.fft(x)
    h = np.zeros(n)
    h[0] = 1.0
    h[1:n // 2] = 2.0
    if n % 2 == 0:
        h[n // 2] = 1.0
    return np.real(np.fft.ifft(spec * h))


def demod_fm(iq: np.ndarray, sample_rate: float, deviation_hz: float = 5000.0,
             audio_cutoff_hz: float = 3000.0) -> np.ndarray:
    """FM 解调：相位差分 → 低通 → 输出基带消息（实信号）。"""
    x = np.asarray(iq)
    if np.iscomplexobj(x):
        y = x
    else:
        y = _analytic(x)
    inst = np.angle(y[1:] * np.conj(y[:-1]))
    demod = inst * (sample_rate / (2 * np.pi * deviation_hz))   # 归一化到 ±1
    taps = lowpass_fir(32, audio_cutoff_hz / (sample_rate / 2.0))
    out = np.asarray(FIR(taps)(demod), dtype=float)
    return np.roll(out, -(len(taps) - 1) // 2)[:demod.size]     # 补偿 FIR 群延迟 + 截回输入长


def demod_am(iq: np.ndarray, sample_rate: float, audio_cutoff_hz: float = 3000.0) -> np.ndarray:
    """AM 解调：包络检波（|解析信号|）→ 去直流 → 低通 → 输出基带消息（实信号）。"""
    x = np.asarray(iq)
    y = x if np.iscomplexobj(x) else _analytic(x)
    env = np.abs(y)
    env = env - np.mean(env)                            # 去载波直流
    taps = lowpass_fir(32, audio_cutoff_hz / (sample_rate / 2.0))
    out = np.asarray(FIR(taps)(env), dtype=float)
    return np.roll(out, -(len(taps) - 1) // 2)[:env.size]        # 补偿 FIR 群延迟 + 截回输入长


def fm_modulate(message: np.ndarray, sample_rate: float, deviation_hz: float = 5000.0) -> np.ndarray:
    """FM 调制（测试用合成器）：消息 → 复指数载波（相位积分）。"""
    m = np.asarray(message, dtype=float)
    phase = 2 * np.pi * deviation_hz * np.cumsum(m) / sample_rate
    return np.exp(1j * phase).astype(np.complex128)


def am_modulate(message: np.ndarray, sample_rate: float, carrier_hz: float = 10000.0) -> np.ndarray:
    """AM 调制（测试用合成器）：消息 → 载波包络（调制深度 1）。"""
    m = np.asarray(message, dtype=float)
    n = m.size
    t = np.arange(n) / sample_rate
    return ((1.0 + m) * np.cos(2 * np.pi * carrier_hz * t)).astype(np.complex128)
