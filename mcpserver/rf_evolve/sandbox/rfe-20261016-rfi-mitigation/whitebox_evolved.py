"""白盒 RFI 抑制算法（演化所得）— 任务：窄带干扰抑制（RFI mitigation）参数演化

⚠️ 本文件由 `mcpserver/rf_evolve/codegen.py` **生成**，请勿手改 —— 要改就改编辑面参数并重跑演化。

它是 SeisEvo（arXiv:2608.18272v1）意义上的**白盒产物**：
推理期不需要 agent、不需要神经网络、不需要本仓任何模块 —— 只需要 `numpy`。
"""
from __future__ import annotations

import json

import numpy as np

#: 搜索得到的参数（= 本算法的全部自由量）
PARAMS = {'prominence_db': 30.0, 'notch_bw_hz': 5000.0, 'adaptive': False, 'mu': 0.02}

#: 这组参数是怎么来的（出处、读数、约束），由演化 harness 写入，便于审计
PROVENANCE = {'found_by': 'mcpserver.rf_evolve（提案器=rules，4 代，seed=20261016）',
 'task': '窄带干扰抑制（RFI mitigation）参数演化',
 'evolved_target': 'mcpserver.rf_brain.rfi_mitigation::mitigate_rfi',
 'frozen_components': ['detect_rfi_narrowband（检测算法：FFT 谱峰 + 显著度阈值）',
                       'notch_filter / notch_biquad（固定陷波拓扑：2 阶 Butterworth 带阻）',
                       'adaptive_notch（自适应拓扑：LMS 单频对消）',
                       '滤波链顺序（逐个频点串行陷波）'],
 'baseline_params': {'prominence_db': 20.0, 'notch_bw_hz': None, 'adaptive': False, 'mu': 0.01},
 'baseline_score': {'mean_db': 6.7658,
                    'min_db': 3.3958,
                    'per_scenario': {'three_strong_tones': 11.5748,
                                     'one_strong_two_weak': 5.3269,
                                     'interferer_inside_band': 3.3958},
                    'wall_s': 0.0989,
                    'snr_before_db': {'three_strong_tones': -3.7152,
                                      'one_strong_two_weak': -1.4757,
                                      'interferer_inside_band': -2.8553}},
 'best_score': {'mean_db': 16.4679,
                'min_db': 12.9993,
                'per_scenario': {'three_strong_tones': 19.5325,
                                 'one_strong_two_weak': 16.8718,
                                 'interferer_inside_band': 12.9993},
                'wall_s': 0.0059,
                'snr_before_db': {'three_strong_tones': -3.7152,
                                  'one_strong_two_weak': -1.4757,
                                  'interferer_inside_band': -2.8553}},
 'gate_stats': {'proposed': 17,
                'rejected_stage_A': 0,
                'rejected_stage_B': 5,
                'scored': 12,
                'saved_notch_ops': 3002368,
                'generated': 4,
                'unique_candidates': 18,
                'reject_rate': 0.2941},
 'note': '本产物推理期不需要 agent / 神经网络 / 本仓模块；参数由约束门 + 执行打分选出，读数见 best_score。'}


# --------------------------------------------------------------------------- 算法本体
def power_spectrum(signal: np.ndarray, sample_rate: float):
    """实信号 -> 单边功率谱（Hz, 功率）。不做归一化（保留绝对量级供阈值判定）。"""
    x = np.asarray(signal, dtype=float)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("signal 必须为非空一维实信号")
    n = x.size
    x_fft = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / float(sample_rate))
    return freqs.astype(float), np.abs(x_fft) ** 2


def detect_narrowband(signal: np.ndarray, sample_rate: float, prominence_db: float):
    """窄带峰检测：稳健中位数估计噪声底，超过 prominence_db 的局部极大值判为干扰。"""
    freqs, power = power_spectrum(signal, sample_rate)
    noise = float(np.median(power))
    if noise <= 0.0:
        noise = 1e-12
    thresh = noise * (10.0 ** (prominence_db / 10.0))
    peaks = []
    for i in np.flatnonzero(power > thresh):
        if i == 0 or i == power.size - 1:
            continue
        if power[i] >= power[i - 1] and power[i] >= power[i + 1]:
            peaks.append(float(freqs[i]))
    return peaks


def notch_biquad(f0: float, sample_rate: float, bw_hz: float):
    """2 阶 Butterworth 带阻（陷波）系数；极半径 r 随带宽收窄趋近 1。"""
    sr = float(sample_rate)
    f0 = float(f0)
    bw = float(bw_hz)
    if not 0.0 < f0 < sr / 2.0:
        raise ValueError(f"陷波频率越界: {f0}（须在 0..{sr / 2} Hz）")
    if bw <= 0.0:
        raise ValueError(f"带宽必须 > 0: {bw}")
    w0 = 2.0 * np.pi * f0 / sr
    r = float(np.clip(1.0 - np.pi * bw / sr, 0.0, 0.9999))
    b = np.array([1.0, -2.0 * np.cos(w0), 1.0])
    a = np.array([1.0, -2.0 * r * np.cos(w0), r * r])
    return b, a


def biquad_lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """直接 II 型转置 biquad（2 阶）。逐样本循环，与仓内实现同式。"""
    b = np.asarray(b, dtype=float) / a[0]
    a = np.asarray(a, dtype=float) / a[0]
    x = np.asarray(x, dtype=float)
    y = np.zeros(x.size)
    z1 = z2 = 0.0
    b0, b1, b2 = b[0], b[1], b[2]
    a1, a2 = a[1], a[2]
    for i in range(x.size):
        xi = x[i]
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def adaptive_notch(signal: np.ndarray, sample_rate: float, f0: float, mu: float) -> np.ndarray:
    """LMS 单频自适应陷波：以 sin/cos 正交参考重构干扰并从输入减去。"""
    x = np.asarray(signal, dtype=float)
    t = np.arange(x.size) / float(sample_rate)
    ref_sin = np.sin(2.0 * np.pi * f0 * t)
    ref_cos = np.cos(2.0 * np.pi * f0 * t)
    w1 = w2 = 0.0
    two_mu = 2.0 * float(mu)
    y = np.zeros(x.size)
    for i in range(x.size):
        err = x[i] - (w1 * ref_sin[i] + w2 * ref_cos[i])
        w1 += two_mu * err * ref_sin[i]
        w2 += two_mu * err * ref_cos[i]
        y[i] = err
    return y


def mitigate(signal: np.ndarray, sample_rate: float, reference=None):
    """端到端：检测干扰频点 -> 逐频点陷波（固定或自适应）。返回 (cleaned, detected_freqs)。"""
    x = np.asarray(signal, dtype=float)
    sr = float(sample_rate)
    bw = float(PARAMS["notch_bw_hz"]) if PARAMS["notch_bw_hz"] else sr / 1000.0
    freqs = detect_narrowband(x, sr, float(PARAMS["prominence_db"]))
    cleaned = x.copy()
    for f0 in freqs:
        if PARAMS["adaptive"]:
            cleaned = adaptive_notch(cleaned, sr, f0, float(PARAMS["mu"]))
        else:
            b, a = notch_biquad(f0, sr, bw)
            cleaned = biquad_lfilter(b, a, cleaned)
    return cleaned, freqs


def snr_db(signal: np.ndarray, reference: np.ndarray) -> float:
    """相对参考信号的 S/N（dB）：P(参考) / P(残差)。与仓内 _snr_db 同式。"""
    s = np.asarray(signal, dtype=float)
    r = np.asarray(reference, dtype=float)
    sp = float(np.mean(r ** 2))
    rp = float(np.mean((s - r) ** 2))
    if rp <= 0.0:
        return 200.0
    return 10.0 * np.log10(sp / rp + 1e-12)


if __name__ == "__main__":  # pragma: no cover - 自检入口
    _sr = 1_000_000.0
    _n = 4096
    _t = np.arange(_n) / _sr
    _sweep = 100_000.0 / (_n / _sr)
    _ref = 0.5 * np.sin(2.0 * np.pi * (_sweep / 2.0) * _t ** 2) + 0.08 * np.random.default_rng(1).standard_normal(_n)
    _dirty = _ref + 0.6 * np.sin(2.0 * np.pi * 180_000.0 * _t + 0.3)
    _clean, _f = mitigate(_dirty, _sr)
    print(json.dumps({"detected": len(_f), "improvement_db": round(snr_db(_clean, _ref) - snr_db(_dirty, _ref), 4)},
                     ensure_ascii=False))
