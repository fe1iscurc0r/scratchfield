"""自测 / 演示入口（D-01/D-02 · --simulate 无真机自测）

python -m mcpserver.rf_brain.denoise.demo --simulate

- demo_n2n_spectrum: 接收 spectrum.py 合成音频的频谱包络输出做演示去噪（D-01 适配）。
- demo_drift: 漂移补偿前后指标（D-02）。
- demo_end_to_end: 去噪 → RC 补偿端到端（D-01 + D-02 集成）。
"""
from __future__ import annotations

import argparse

import numpy as np

from mcpserver.rf_brain import spectrum
from mcpserver.rf_brain.denoise import bench, drift, n2n, reservoir, synthetic
from mcpserver.rf_brain.denoise import eval as ev


def _train_denoise(y1, y2, seed=0):
    model = n2n.N2NDenoiser(window=15, hidden=(48, 48), seed=seed)
    model.train(y1, y2, epochs=40)
    return model


def demo_n2n_spectrum(sample_rate: float = 48000.0, n: int = 4096, seed: int = 0) -> dict:
    """接收 spectrum 合成音频的幅度包络，做 Noise2Noise 演示去噪。"""
    audio = spectrum.synthetic_spectrum_audio(sample_rate, int(n), seed=seed)
    env = np.abs(audio)  # 幅度包络作为演示信号
    scale = float(np.std(env)) if float(np.std(env)) > 1e-12 else 1.0
    y1 = env + 0.3 * scale * np.random.default_rng(seed).normal(0.0, 1.0, env.shape)
    y2 = env + 0.3 * scale * np.random.default_rng(seed + 1).normal(0.0, 1.0, env.shape)
    model = _train_denoise(y1, y2, seed=seed)
    denoised = model.denoise(y1)
    return {
        "clean": env, "noisy": y1, "denoised": denoised,
        "gain": ev.snr_gain(env, y1, denoised),
        "params": model.parameter_count(),
    }


def demo_n2n_synthetic(sample_rate: float = 1000.0, n: int = 2048, seed: int = 0) -> dict:
    """合成正弦 + 高斯噪声的标准演示（指标稳定）。"""
    d = synthetic.generate("sine", "gaussian", n, sample_rate,
                           noise_params={"sigma": 0.3}, seed=seed)
    model = _train_denoise(d["noisy1"], d["noisy2"], seed=seed)
    denoised = model.denoise(d["noisy1"])
    return {
        "clean": d["clean"], "noisy": d["noisy1"], "denoised": denoised,
        "gain": ev.snr_gain(d["clean"], d["noisy1"], denoised),
        "params": model.parameter_count(),
    }


def demo_drift(sample_rate: float = 1000.0, n: int = 3000, seed: int = 0) -> dict:
    """RC 漂移补偿前后指标。"""
    t = np.arange(n) / float(sample_rate)
    clean = np.sin(2 * np.pi * 2.0 * t) + 0.3 * np.sin(2 * np.pi * 0.5 * t)
    drifted, _ = drift.simulate_drift(clean, mode="offset_gain_baseline",
                                      offset=0.2, gain=1.1, baseline_amplitude=0.15, seed=seed)
    split = n // 3
    comp = drift.DriftCompensator(reservoir.Reservoir(n_units=64, input_dim=1, seed=seed))
    comp.fit(drifted[:split], clean[:split])
    compensated = comp.compensate(drifted)
    return {
        "clean": clean, "drifted": drifted, "compensated": compensated,
        "metrics": bench.drift_metrics(clean, drifted, compensated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Noise2Noise + reservoir 漂移补偿 演示")
    parser.add_argument("--simulate", action="store_true", help="无真机自测（合成数据）")
    args = parser.parse_args()
    if not args.simulate:
        parser.print_help()
        return 0

    print("=" * 60)
    print("D-01 · Noise2Noise 去噪演示（spectrum 包络）")
    print("=" * 60)
    r = demo_n2n_spectrum()
    print(ev.report_table(r["clean"], r["noisy"], r["denoised"]))
    print(f"\n模型参数量: {r['params']} (<100K)")

    print("\n" + "=" * 60)
    print("D-02 · reservoir 漂移补偿演示")
    print("=" * 60)
    d = demo_drift()
    print(bench.compare_table(d["clean"], d["drifted"], d["compensated"]))

    print("\n" + "=" * 60)
    print("D-01 + D-02 · 去噪 → RC 补偿 端到端")
    print("=" * 60)
    e = bench.end_to_end()
    print("去噪 SNR 增益:", {k: round(v, 2) for k, v in e["denoise"].items()})
    print("漂移 MSE 前后:", round(e["drift"]["mse_before"], 4), "->",
          round(e["drift"]["mse_after"], 4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
