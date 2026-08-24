"""射频大脑 · 特征提取（Phase 1 骨架，Phase 4 接 liquid-dsp）

FFT → 平滑 → 峰值/带宽/平坦度/SNR → FeatureVector。
默认 numpy；liquid-dsp 可用时（``liquid_backend.is_available()``）
功率谱改走 spgramcf C 实现，两路特征结果应在容差内一致（见
``test_phase4_dsp.py`` 对拍验收）。

关键判据：频谱平坦度（flatness）区分噪声 vs 信号——
噪声频谱平坦（flatness→1），调制信号频谱集中（flatness→0）。
SNR 只作辅助，不作主判据（噪声的峰值天然比中位数高 ~10dB，会误判）。
"""
from __future__ import annotations

import logging

import numpy as np

from mcpserver.rf_brain import liquid_backend
from mcpserver.rf_brain.schemas import FeatureVector

logger = logging.getLogger(__name__)


def _smooth(x: np.ndarray, window: int = 11) -> np.ndarray:
    """滑动平均平滑，减小噪声假峰。"""
    if len(x) < window:
        return x.copy()
    kernel = np.ones(window) / window
    return np.convolve(x, kernel, mode="same")


def extract_features(
    iq: np.ndarray,
    sample_rate: float = 2_000_000.0,
    center_freq: float = 433_920_000.0,
    timestamp: str = "",
    force_numpy: bool = False,
) -> FeatureVector:
    """从 IQ 样本提取频谱特征向量。

    force_numpy=True 时禁用 liquid-dsp 路径（用于两路对拍验收）。
    """
    n = len(iq)
    use_liquid = not force_numpy and liquid_backend.is_available()
    if use_liquid:
        # Phase 4 真底座：spgramcf 周期图（Hamming 窗，线性功率）
        logger.debug("[rf_brain] 特征提取使用 liquid-dsp 后端（spgramcf）")
        power = liquid_backend.power_spectrum(iq)
    else:
        if force_numpy:
            logger.debug("[rf_brain] 特征提取使用 numpy 参考实现（force_numpy=True）")
        else:
            logger.debug("[rf_brain] 特征提取使用 numpy 参考实现（liquid-dsp 不可用）")
        window = np.hanning(n)
        spectrum = np.fft.fftshift(np.fft.fft(iq * window))
        power = np.abs(spectrum) ** 2
    freqs = np.fft.fftshift(np.fft.fftfreq(n, d=1.0 / sample_rate))
    power_db = 10 * np.log10(power + 1e-12)

    # 只取正频侧
    pos = freqs >= 0
    freqs_pos = freqs[pos]
    power_db_pos = power_db[pos]
    power_pos = power[pos]

    # 平滑功率谱（正频侧），减小假峰
    smoothed_db = _smooth(power_db_pos, window=11)

    # 噪声底：用低分位数（20%），避免强窄带信号抬高均值/中位数
    noise_floor_db = float(np.percentile(smoothed_db, 20))
    peak_db = float(np.max(smoothed_db))
    snr_db = peak_db - noise_floor_db

    # 频谱平坦度：几何均值 / 算术均值（1 = 完全平坦 = 噪声）
    if np.mean(power_pos) > 1e-15:
        flatness = float(np.exp(np.mean(np.log(power_pos + 1e-12))) / (np.mean(power_pos) + 1e-12))
    else:
        flatness = 1.0
    spectral_flatness = min(1.0, flatness)

    # 峰值检测：显著峰判定（相对主峰 -6dB 以内才计数，过滤旁瓣波纹假峰）
    # 先找主峰，再找其他显著峰
    if len(smoothed_db) == 0:
        peak_indices = []
    else:
        peak_db = float(np.max(smoothed_db))
        threshold_db = peak_db - 6.0  # 显著峰：主峰 6dB 以内
        above = smoothed_db > threshold_db
        peak_indices = []
        min_gap = 20  # 对应 ~10kHz 间隔，合并波纹
        for i in range(1, len(smoothed_db) - 1):
            if above[i] and smoothed_db[i] >= smoothed_db[i - 1] and smoothed_db[i] >= smoothed_db[i + 1]:
                if peak_indices and (i - peak_indices[-1]) < min_gap:
                    if smoothed_db[i] > smoothed_db[peak_indices[-1]]:
                        peak_indices[-1] = i
                else:
                    peak_indices.append(i)

    # 主峰频率
    if peak_indices:
        main_idx = max(peak_indices, key=lambda i: smoothed_db[i])
        peak_freq_offset = float(freqs_pos[main_idx])
        peak_freq_hz = center_freq + peak_freq_offset
        n_peaks = len(peak_indices)
        if n_peaks >= 2:
            sorted_peaks = sorted(peak_indices, key=lambda i: smoothed_db[i], reverse=True)[:2]
            peak_separation_hz = abs(float(freqs_pos[sorted_peaks[0]] - freqs_pos[sorted_peaks[1]]))
        else:
            peak_separation_hz = None
    else:
        peak_freq_hz = None
        n_peaks = 0
        peak_separation_hz = None

    # 带宽估计：主峰 -3dB 连续区间宽度
    if peak_indices:
        bw_indices = np.where(smoothed_db > (peak_db - 3.0))[0]
        if len(bw_indices) > 0:
            bandwidth_hz = float((bw_indices[-1] - bw_indices[0]) * (sample_rate / n))
        else:
            bandwidth_hz = None
    else:
        bandwidth_hz = None

    # 符号率估计：由带宽粗估
    symbol_rate_estimate_hz = bandwidth_hz if bandwidth_hz else None

    # 包络变异系数：区分 OOK（幅度键控）与 FSK/GFSK（恒定包络）
    envelope = np.abs(iq)
    envelope_mean = float(np.mean(envelope))
    envelope_cv = float(np.std(envelope) / envelope_mean) if envelope_mean > 1e-12 else 0.0

    # 瞬时频率轨迹斜率（Phase 4）：区分 FSK 硬切换 vs GFSK 高斯平滑。
    # 无量纲化：mean|Δf_逐样本| / std(f_inst) ≈ 2/sps（硬切换）或更小（平滑）。
    freq_transition_slope = _freq_transition_slope(iq, sample_rate)

    return FeatureVector(
        timestamp=timestamp,
        center_freq_hz=center_freq,
        sample_rate_hz=sample_rate,
        n_samples=n,
        peak_freq_hz=peak_freq_hz,
        bandwidth_hz=bandwidth_hz,
        snr_db=snr_db,
        spectral_flatness=spectral_flatness,
        symbol_rate_estimate_hz=symbol_rate_estimate_hz,
        n_peaks=n_peaks,
        peak_separation_hz=peak_separation_hz,
        envelope_cv=envelope_cv,
        freq_transition_slope=freq_transition_slope,
    )


def _freq_transition_slope(iq: np.ndarray, sample_rate: float) -> float | None:
    """瞬时频率轨迹的归一化跳变幅度（中值滤波保边去噪后测量）。

    鉴频噪声重尾（相位跳变尖刺），滑动均值会把 FSK 硬切换的陡边
    摊平到和噪声同量级；中值滤波则保边去噪：FSK 跳变仍是孤立尖峰
    （稀疏、幅度≈2×频偏），GFSK 高斯成形是连续坡道（无孤立尖峰）。
    指标 = p99(|Δf|) / 轨迹峰峰值：FSK≈1，GFSK≪1；与频偏无关。
    样本太少返回 None。
    """
    n = len(iq)
    if n < 64:
        return None
    phase = np.unwrap(np.angle(iq))
    inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
    sps = sample_rate / 48_000  # 默认符号率 48k 对应的每符号样本数
    # 两级去噪（SNR 20dB 时鉴频噪声 σ 比频偏还大，单级压不住）：
    # 1) 短滑动均值（窗 ~sps/8，带宽 ≈ 8×符号率）：保硬切换陡边，
    #    噪声减半以上；
    w_avg = max(3, int(sps / 8))
    if w_avg % 2 == 0:
        w_avg += 1
    kern = np.ones(w_avg) / w_avg
    avg = np.convolve(inst_freq, kern, mode="same")
    # 2) 滑动中值（窗 ~sps/2，必须 < sps 才不跨符号边界抹跳变）：
    #    保 FSK 硬切换陡边，压残余高斯噪声与相位尖刺
    w_med = max(3, int(sps / 2))
    if w_med % 2 == 0:
        w_med += 1
    half = w_med // 2
    padded = np.pad(avg, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, w_med)
    med = np.median(windows, axis=1)
    rng = float(np.ptp(np.percentile(med, [5, 95])))
    if rng < 1e-6:
        # 无频移分量（OOK/纯噪声）：指标无意义
        return None
    d = np.abs(np.diff(med))
    return float(np.percentile(d, 99) / rng)
