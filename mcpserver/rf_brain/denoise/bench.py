"""漂移补偿基准（D-02 · 漂移前后指标对比 + 去噪→RC 端到端）"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.denoise import drift, n2n, reservoir
from mcpserver.rf_brain.denoise import eval as ev


def drift_metrics(clean, drifted, compensated) -> dict:
    """漂移补偿前后指标对比。"""
    mse_before = ev.mse(clean, drifted)
    mse_after = ev.mse(clean, compensated)
    return {
        "mse_before": mse_before,
        "mse_after": mse_after,
        "reduction_ratio": (mse_before / mse_after) if mse_after > 1e-12 else float("inf"),
        "snr_before_db": ev.snr_db(clean, drifted),
        "snr_after_db": ev.snr_db(clean, compensated),
    }


def compare_table(clean, drifted, compensated) -> str:
    """漂移前后文本指标表。"""
    m = drift_metrics(clean, drifted, compensated)
    return "\n".join([
        "指标            | 漂移后(before) | 补偿后(after)",
        "----------------+----------------+----------------",
        f"MSE             | {m['mse_before']:>14.4f} | {m['mse_after']:>14.4f}",
        f"SNR (dB)        | {m['snr_before_db']:>14.2f} | {m['snr_after_db']:>14.2f}",
        f"误差下降倍数     | {m['reduction_ratio']:>14.2f}x",
    ])


def end_to_end(sample_rate: float = 1000.0, n: int = 3000, seed: int = 0) -> dict:
    """去噪(N2N) → 漂移补偿(RC) 端到端管线，返回指标 dict。

    流程：干净慢变信号 → 加测量噪声 → N2N 去噪 → 叠加漂移 → RC 补偿。
    """
    t = np.arange(n) / float(sample_rate)
    clean = (np.sin(2 * np.pi * 2.0 * t)
             + 0.3 * np.sin(2 * np.pi * 0.5 * t))
    clean = clean - clean.mean()

    # 1) 测量噪声 + N2N 去噪（两次独立带噪观测无标签训练）
    y1 = clean + 0.2 * np.random.default_rng(seed).normal(0.0, 1.0, clean.shape)
    y2 = clean + 0.2 * np.random.default_rng(seed + 1).normal(0.0, 1.0, clean.shape)
    model = n2n.N2NDenoiser(window=15, hidden=(48, 48), seed=seed)
    model.train(y1, y2, epochs=40)
    denoised = model.denoise(y1)

    # 2) 漂移（施加在去噪后信号上）
    drifted, _ = drift.simulate_drift(
        denoised, mode="offset_gain_baseline", offset=0.2, gain=1.1,
        baseline_amplitude=0.15, seed=seed,
    )

    # 3) RC 补偿：前 1/3 段作为配对标定，全段补偿
    split = n // 3
    comp = drift.DriftCompensator(reservoir.Reservoir(n_units=64, input_dim=1, seed=seed))
    comp.fit(drifted[:split], denoised[:split])
    compensated = comp.compensate(drifted)

    return {
        "clean": clean, "noisy": y1, "denoised": denoised,
        "drifted": drifted, "compensated": compensated,
        "denoise": ev.snr_gain(clean, y1, denoised),
        "drift": drift_metrics(denoised, drifted, compensated),
    }
