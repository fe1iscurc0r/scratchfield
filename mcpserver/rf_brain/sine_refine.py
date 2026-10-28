"""高阶正弦频率精修（工单256 任务A）—— ICP/解调后处理的**可选精修级**。

## 授粉点（论文 → 落到哪个函数 → 取舍理由）

| 论文 | 机制 | 落到本模块 | 取舍 |
|---|---|---|---|
| 2610.21643 | 高阶（含导数项）正弦模型 + analysis-by-synthesis 式迭代精修 | `refine_tones()` 的「拟合 → 残差 → 频率更新」主循环 | **未实现高阶导数项**：论文正文不可达（本机直连 arxiv 被墙，见报告 §7），按工单允许条款实现**基础迭代精修**，并在报告里如实标注差异 |
| — | FFT 峰值法作为**基线**（bin 分辨率受限） | `fft_peak_seeds()` | 只用来给**初值**与算基线 RMSE，绝不用真值初始化 |

**为什么需要它**：FFT 峰值法的频率误差上界是半个 bin。两个音间隔不到 2 个 bin 时，
谱峰还会糊成一个 —— 峰值法直接给出一个错得很离谱的频率。迭代精修能在**同一段数据**上
把每个音的频率逼到远小于一个 bin 的误差。

## 算法（纯 numpy + 标准库，无 scipy）

1. **初值**：`power_spectrum()` 取功率最大的 `n_tones` 个 bin（相邻 bin 也允许，因为两音可能只差 1~2 bin）；
2. **迭代**（最多 `max_iter` 次，收敛容差 `freq_tol_hz`）：
   a. 固定频率集，用 `{cos, -sin}` 实基做**最小二乘**拟合并算每个音的（幅度, 相位）；
   b. 对每个音：从信号里**减去其它音**的拟合分量 ⇒ 该音的残差；
   c. 在 `[f-Δ, f+Δ]`（Δ = 1.5 bin）内用**三段网格细化**最大化 `|<残差, e^{j2πft}>|` ⇒ 更新频率；
   d. 若本次最大频率改动 < `freq_tol_hz` ⇒ 收敛；
3. **输出**：`ToneEstimate(freq_hz, amplitude, phase_rad, iterations)` + 收敛曲线。

确定性：全部 float64 定点运算，无随机数；同输入两次调用**逐位一致**。

## 复现

    python -m mcpserver.rf_brain.sine_refine --demo
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass

import numpy as np

from .rfi_mitigation import power_spectrum

DEFAULT_MAX_ITER = 40
DEFAULT_FREQ_TOL_HZ = 1e-4
_GRID_POINTS = 41          # 三段网格每段的采样点数（固定 ⇒ 确定性）
_GRID_PASSES = 3


@dataclass(frozen=True)
class ToneEstimate:
    """单音估计结果。"""

    freq_hz: float
    amplitude: float
    phase_rad: float


@dataclass
class RefineReport:
    """精修报告：估计值 + 收敛曲线 + 与基线的对比（有真值时才填 rmse）。"""

    tones: list[ToneEstimate]
    iterations: int
    convergence: list[float]          # 每次迭代的最大频率改动（Hz）
    seeds_hz: list[float]
    rmse_fft: float | None = None
    rmse_refined: float | None = None

    def as_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "seeds_hz": [round(f, 6) for f in self.seeds_hz],
            "tones": [{"freq_hz": round(t.freq_hz, 6), "amplitude": round(t.amplitude, 6),
                       "phase_rad": round(t.phase_rad, 6)} for t in self.tones],
            "convergence_hz": [round(c, 9) for c in self.convergence],
            "rmse_fft": None if self.rmse_fft is None else round(self.rmse_fft, 6),
            "rmse_refined": None if self.rmse_refined is None else round(self.rmse_refined, 6),
        }


def fft_peak_seeds(signal: np.ndarray, sample_rate: float, n_tones: int) -> list[float]:
    """FFT 峰值法的**初值**与**基线**：取功率最大的 `n_tones` 个 bin 频率。

    允许选相邻 bin（两音间隔 < 2 bin 时谱峰合并，但峰两侧的 bin 仍落在各自真值附近）。
    """
    x = np.asarray(signal, dtype=float)
    if n_tones <= 0:
        raise ValueError("n_tones 必须为正")
    freqs, power = power_spectrum(x, sample_rate)
    if power.size < 2 * n_tones + 2:
        raise ValueError("信号太短，无法给出足够的初值")
    order = np.argsort(power)[::-1]
    seeds: list[float] = []
    for idx in order:
        if idx == 0 or idx >= power.size - 1:
            continue
        seeds.append(float(freqs[idx]))
        if len(seeds) == n_tones:
            break
    return sorted(seeds)


def _fit_amplitudes(x: np.ndarray, t: np.ndarray, freqs: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """固定频率，用 {cos, -sin} 实基最小二乘拟合 ⇒ (a, b)；幅度=hypot，相位=atan2(b,a)。"""
    cols: list[np.ndarray] = []
    for f in freqs:
        w = 2.0 * math.pi * f * t
        cols.append(np.cos(w))
        cols.append(-np.sin(w))
    A = np.column_stack(cols)
    coef, *_ = np.linalg.lstsq(A, x, rcond=None)
    return coef[0::2], coef[1::2]


def _synthesize(t: np.ndarray, freqs: list[float], a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros_like(t)
    for i, f in enumerate(freqs):
        w = 2.0 * math.pi * f * t
        out += a[i] * np.cos(w) - b[i] * np.sin(w)
    return out


def _corr_magnitude(residual: np.ndarray, t: np.ndarray, freq: float) -> float:
    """`|<residual, e^{j2πft}>|`（对实信号取等效的 cos/sin 投影模长）。"""
    w = 2.0 * math.pi * freq * t
    c = float(np.dot(residual, np.cos(w)))
    s = float(np.dot(residual, np.sin(w)))
    return math.hypot(c, s)


def _refine_single_freq(residual: np.ndarray, t: np.ndarray, f0: float,
                        span_hz: float) -> float:
    """在 [f0-span, f0+span] 内三段网格细化，返回使相关模长最大的频率（确定性）。"""
    lo, hi = f0 - span_hz, f0 + span_hz
    best = f0
    for _ in range(_GRID_PASSES):
        grid = np.linspace(lo, hi, _GRID_POINTS)
        vals = [_corr_magnitude(residual, t, float(f)) for f in grid]
        k = int(np.argmax(vals))
        best = float(grid[k])
        step = (hi - lo) / (_GRID_POINTS - 1)
        lo, hi = best - step, best + step
    return best


def refine_tones(signal: np.ndarray, sample_rate: float, n_tones: int, *,
                 max_iter: int = DEFAULT_MAX_ITER,
                 freq_tol_hz: float = DEFAULT_FREQ_TOL_HZ,
                 true_freqs_hz: list[float] | None = None) -> RefineReport:
    """迭代精修多音频率（analysis-by-synthesis）。

    ``true_freqs_hz`` 只用于**计算 RMSE 指标**，绝不参与初值或更新 —— 这一点由
    `test_seeds_do_not_use_truth` 守住。
    """
    x = np.asarray(signal, dtype=float)
    n = x.size
    t = np.arange(n, dtype=float) / float(sample_rate)
    bin_hz = float(sample_rate) / float(n)
    span = 1.5 * bin_hz

    seeds = fft_peak_seeds(x, sample_rate, n_tones)
    freqs = list(seeds)
    convergence: list[float] = []
    iters = 0

    for it in range(1, max_iter + 1):
        iters = it
        a, b = _fit_amplitudes(x, t, freqs)
        max_delta = 0.0
        updated = list(freqs)
        for i in range(len(freqs)):
            # 残差 = 原始 − 其它音（保留本音，避免把本音也减掉）
            others = [j for j in range(len(freqs)) if j != i]
            residual = x - _synthesize(t, [freqs[j] for j in others], a[others], b[others])
            new_f = _refine_single_freq(residual, t, freqs[i], span)
            max_delta = max(max_delta, abs(new_f - freqs[i]))
            updated[i] = new_f
        freqs = updated
        convergence.append(max_delta)
        if max_delta < freq_tol_hz:
            break

    a, b = _fit_amplitudes(x, t, freqs)
    tones = [ToneEstimate(freq_hz=float(freqs[i]), amplitude=float(math.hypot(a[i], b[i])),
                          phase_rad=float(math.atan2(b[i], a[i])))
             for i in range(len(freqs))]

    report = RefineReport(tones=tones, iterations=iters, convergence=convergence,
                          seeds_hz=seeds)
    if true_freqs_hz is not None:
        truth = sorted(float(f) for f in true_freqs_hz)
        est = sorted(t.freq_hz for t in tones)
        report.rmse_fft = _rmse(sorted(seeds), truth)
        report.rmse_refined = _rmse(est, truth)
    return report


def _rmse(est: list[float], truth: list[float]) -> float:
    k = min(len(est), len(truth))
    if k == 0:
        return float("nan")
    diffs = np.asarray(est[:k], dtype=float) - np.asarray(truth[:k], dtype=float)
    return float(np.sqrt(np.mean(diffs ** 2)))


# --------------------------------------------------------------------------- #
# 演示场景（测试与 demo 共用同一份构造，避免两处漂移）
# --------------------------------------------------------------------------- #
DEMO_SAMPLE_RATE = 1000.0
DEMO_N = 1024
DEMO_TRUE_HZ = (100.0, 101.2)      # 间隔 1.2 bin（< 1.5 bin）—— 峰值法必然分不开
DEMO_SEED = 20261017


def build_demo_signal(seed: int = DEMO_SEED, snr_db: float = 30.0) -> tuple[np.ndarray, float]:
    """构造「两音间隔 < 1.5 bin + 已知失配」的确定性信号（含白噪声）。"""
    rng = np.random.default_rng(seed)
    n = DEMO_N
    t = np.arange(n, dtype=float) / DEMO_SAMPLE_RATE
    clean = np.zeros(n)
    for i, f in enumerate(DEMO_TRUE_HZ):
        clean += (1.0 if i == 0 else 0.7) * np.cos(2.0 * math.pi * f * t + 0.3 * (i + 1))
    sig_power = float(np.mean(clean ** 2))
    noise_power = sig_power / (10.0 ** (snr_db / 10.0))
    noise = rng.normal(0.0, math.sqrt(noise_power), n)
    return clean + noise, DEMO_SAMPLE_RATE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="高阶正弦频率精修（工单256 任务A）")
    ap.add_argument("--demo", action="store_true", help="跑内置两音场景并打印精修 vs FFT 基线")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--snr-db", type=float, default=30.0)
    args = ap.parse_args(argv)

    sig, fs = build_demo_signal(snr_db=args.snr_db)
    rep = refine_tones(sig, fs, n_tones=len(DEMO_TRUE_HZ), true_freqs_hz=list(DEMO_TRUE_HZ))

    if args.json:
        print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=1))
        return 0

    print("高阶正弦频率精修（工单256 任务A）· 纯 numpy，无 scipy")
    print(f"场景：fs={fs:.0f} Hz, N={DEMO_N}, bin={fs / DEMO_N:.4f} Hz, "
          f"两音间隔 {abs(DEMO_TRUE_HZ[1] - DEMO_TRUE_HZ[0]):.2f} Hz "
          f"= {abs(DEMO_TRUE_HZ[1] - DEMO_TRUE_HZ[0]) / (fs / DEMO_N):.2f} bin, SNR={args.snr_db:.0f} dB")
    print(f"真值      : {list(DEMO_TRUE_HZ)}")
    print(f"FFT 初值  : {[round(rep.seeds_hz[0], 4), round(rep.seeds_hz[-1], 4)]}"
          if len(rep.seeds_hz) > 1 else f"FFT 初值  : {rep.seeds_hz}")
    print(f"精修结果  : {[round(t.freq_hz, 4) for t in rep.tones]}")
    print(f"rmse_fft     = {rep.rmse_fft:.6f} Hz")
    print(f"rmse_refined = {rep.rmse_refined:.6f} Hz")
    print(f"iterations   = {rep.iterations}")
    print(f"收敛曲线(最大频率改动, Hz): {[round(c, 8) for c in rep.convergence[:6]]}"
          + (" …" if len(rep.convergence) > 6 else ""))
    print()
    print(f"指标改善：RMSE 降低 {100.0 * (1.0 - rep.rmse_refined / rep.rmse_fft):.1f}%"
          if rep.rmse_fft else "")
    print("⚠️ 未实现论文 2610.21643 的高阶导数项（正文不可达）—— 见报告 §7。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
