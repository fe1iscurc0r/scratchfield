"""去噪评估（D-01 · 去噪前后 SNR / 波形对比指标表）

纯 numpy。snr_db 定义为 10*log10(var(ref) / var(ref - est))，越大越接近干净参考。
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-12


def mse(ref, est) -> float:
    ref = np.asarray(ref, dtype=float)
    est = np.asarray(est, dtype=float)
    return float(np.mean((ref - est) ** 2))


def mae(ref, est) -> float:
    ref = np.asarray(ref, dtype=float)
    est = np.asarray(est, dtype=float)
    return float(np.mean(np.abs(ref - est)))


def snr_db(ref, est) -> float:
    """信号-误差比（越高越好）。ref=干净参考，est=带噪/去噪估计。"""
    ref = np.asarray(ref, dtype=float)
    est = np.asarray(est, dtype=float)
    err = ref - est
    var_ref = float(np.var(ref))
    var_err = float(np.var(err))
    if var_err < _EPS:
        return float("inf")
    return float(10.0 * np.log10(var_ref / var_err))


def snr_gain(clean, noisy, denoised) -> dict:
    """去噪前后 SNR 对比，返回 in/out/gain 三项。"""
    snr_in = snr_db(clean, noisy)
    snr_out = snr_db(clean, denoised)
    gain = (snr_out - snr_in) if (np.isfinite(snr_in) and np.isfinite(snr_out)) else float("inf")
    return {"snr_in_db": snr_in, "snr_out_db": snr_out, "gain_db": gain}


def waveform_stats(clean, est) -> dict:
    """波形逐点对比指标。"""
    clean = np.asarray(clean, dtype=float)
    est = np.asarray(est, dtype=float)
    err = clean - est
    corr = 0.0
    if float(np.std(clean)) > _EPS and float(np.std(est)) > _EPS:
        corr = float(np.corrcoef(clean, est)[0, 1])
    return {
        "mse": mse(clean, est),
        "mae": mae(clean, est),
        "rms_error": float(np.sqrt(np.mean(err ** 2))),
        "peak_abs_error": float(np.max(np.abs(err))),
        "corr": corr,
    }


def report_table(clean, noisy, denoised) -> str:
    """文本指标表（baseline 带噪 vs 去噪后）。"""
    gain = snr_gain(clean, noisy, denoised)
    nw = waveform_stats(clean, noisy)
    dw = waveform_stats(clean, denoised)
    return "\n".join([
        "指标            | 带噪(baseline) | 去噪后",
        "----------------+----------------+----------------",
        f"SNR (dB)        | {gain['snr_in_db']:>14.2f} | {gain['snr_out_db']:>14.2f}",
        f"MSE             | {nw['mse']:>14.4f} | {dw['mse']:>14.4f}",
        f"MAE             | {nw['mae']:>14.4f} | {dw['mae']:>14.4f}",
        f"峰值绝对误差     | {nw['peak_abs_error']:>14.4f} | {dw['peak_abs_error']:>14.4f}",
        f"相关系数         | {nw['corr']:>14.4f} | {dw['corr']:>14.4f}",
        f"SNR 增益 (dB)    | {gain['gain_db']:>+14.2f}",
    ])
