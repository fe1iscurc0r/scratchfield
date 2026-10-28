"""RFI 相关监测（工单256 任务B）—— 在既有双通道检测之上加「相关统计」层。

## 授粉点（论文 → 落到哪个函数 → 取舍理由）

| 论文 | 机制 | 落到本模块 | 取舍 |
|---|---|---|---|
| 2610.20847 | 用**双通道相关统计**区分真信号与本地干扰 | `coherence_spectrum()` + `detect_by_coherence()` | 只借"相关判据"这一层；阈值/帧长全部显式参数化，不搬论文数值 |
| — | 既有 `detect_rfi_dual_channel()` 是**能量失衡**判据（极化域） | **不重写**，作为对照之一并存 | 见下"为什么不是重写" |

## 为什么这是**新增**而不是重写既有实现

仓内已有三种 RFI 判据，本模块补的是**第四种、且是不同的量**：

| 判据 | 函数 | 抓什么 | 抓不到什么 |
|---|---|---|---|
| 单通道能量峰 | `rfi_mitigation.detect_rfi_narrowband` | 强于噪声底的窄带峰 | **分不清"真信号"与"本地干扰"**——两者都是强窄带峰 |
| 双通道能量失衡 | `rfi_mitigation.detect_rfi_dual_channel` | 极化不对称（只进一路的强干扰） | 两路**都有**（功率相近）时无判据；对本仓构造的非偏振真信号也不敏感 |
| 统计子带检测 | `rfi_statistical.StatisticalRFIDetector` | 子带能量持续性 | 同上，无跨通道相关性 |
| **双通道相干（本模块）** | `coherence_spectrum` | **两路是否同源**（相干 ⇒ 真信号；不相干 ⇒ 本地干扰） | 需要多帧平均（帧数少时相干估计方差大） |

⇒ 相关判据给出的是「**同源性**」，与能量/失衡在信息上正交，因此需要新模块；
既有 `rfi_mitigation.py` / `rfi_statistical.py` 的公开签名与默认行为**零改动**。

## 统计量

对两路分别分帧（Hann 窗、50% 重叠），用**平均互谱**估幅度平方相干：

    γ²(f) = |⟨X_a(f) X_b*(f)⟩|² / (⟨|X_a(f)|²⟩ ⟨|X_b(f)|²⟩)        ∈ [0, 1]

- 同源真信号：两路共享同一相位关系 ⇒ γ² → 1；
- 只进一路的本地干扰：互谱只由噪声贡献 ⇒ γ² → ~1/K（K=帧数）；
- 判据：**能量超底噪阈值** 且 **γ² < coherence_threshold** ⇒ 判为本地干扰。

## 复现

    python -m mcpserver.rf_brain.rfi_correlated_monitor --demo
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field

import numpy as np

from .rfi_mitigation import detect_rfi_narrowband, power_spectrum

DEFAULT_FRAME_LEN = 256
DEFAULT_HOP = 128
DEFAULT_COHERENCE_THRESHOLD = 0.5
DEFAULT_PROMINENCE_DB = 12.0
EVAL_HALF_WIDTH_BINS = 1          # 真值 tone 的评估半宽（±1 bin）


@dataclass
class ConfusionMatrix:
    """以「候选 tone bin」为评估集：正类 = RFI tone bin，负类 = 真信号 tone bin。"""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def detection_rate(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else float("nan")

    @property
    def false_alarm_rate(self) -> float:
        denom = self.fp + self.tn
        return self.fp / denom if denom else float("nan")

    def as_dict(self) -> dict:
        # NaN（无正类/无负类）序列化成 None —— 既让 dict 可比较，也让 --json 合法（JSON 无 NaN）
        def _num(v: float) -> float | None:
            return None if math.isnan(v) else round(v, 6)

        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
                "detection_rate": _num(self.detection_rate),
                "false_alarm_rate": _num(self.false_alarm_rate)}


@dataclass
class ScenarioResult:
    name: str
    correlation: ConfusionMatrix
    energy_baseline: ConfusionMatrix
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"scenario": self.name,
                "correlation": self.correlation.as_dict(),
                "energy_baseline": self.energy_baseline.as_dict(),
                "extra": self.extra}


def _frames(x: np.ndarray, frame_len: int, hop: int) -> np.ndarray:
    """按固定 hop 切帧（尾帧不足则丢弃），返回 (K, frame_len)。"""
    if frame_len <= 0 or hop <= 0:
        raise ValueError("frame_len/hop 必须为正")
    start = 0
    out: list[np.ndarray] = []
    while start + frame_len <= x.size:
        out.append(x[start:start + frame_len])
        start += hop
    if not out:
        raise ValueError("信号长度不足一帧")
    return np.asarray(out, dtype=float)


def coherence_spectrum(ch_a: np.ndarray, ch_b: np.ndarray, sample_rate: float, *,
                       frame_len: int = DEFAULT_FRAME_LEN,
                       hop: int = DEFAULT_HOP) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """平均互谱估幅度平方相干。

    返回 ``(freqs, gamma2, total_power)``；``total_power`` 是两路平均功率谱之和
    （用作能量门限，避免把纯噪声 bin 拉进候选）。
    """
    a = np.asarray(ch_a, dtype=float)
    b = np.asarray(ch_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("两通道长度必须一致")
    fa = _frames(a, frame_len, hop)
    fb = _frames(b, frame_len, hop)
    window = np.hanning(frame_len)
    XA = np.fft.rfft(fa * window, axis=1)
    XB = np.fft.rfft(fb * window, axis=1)
    S_ab = np.mean(XA * np.conj(XB), axis=0)
    S_aa = np.mean(np.abs(XA) ** 2, axis=0)
    S_bb = np.mean(np.abs(XB) ** 2, axis=0)
    eps = 1e-20
    gamma2 = (np.abs(S_ab) ** 2) / (S_aa * S_bb + eps)
    freqs = np.fft.rfftfreq(frame_len, 1.0 / float(sample_rate))
    return freqs.astype(float), np.clip(gamma2, 0.0, 1.0), S_aa + S_bb


def detect_by_coherence(ch_a: np.ndarray, ch_b: np.ndarray, sample_rate: float, *,
                        coherence_threshold: float = DEFAULT_COHERENCE_THRESHOLD,
                        prominence_db: float = DEFAULT_PROMINENCE_DB,
                        frame_len: int = DEFAULT_FRAME_LEN,
                        hop: int = DEFAULT_HOP) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """相关判据：能量超底噪 **且** 相干低于阈值 ⇒ 本地干扰。

    返回 ``(freqs, mask, gamma2)``。
    """
    freqs, gamma2, total = coherence_spectrum(ch_a, ch_b, sample_rate,
                                              frame_len=frame_len, hop=hop)
    floor = float(np.median(total))
    if floor <= 0.0:
        floor = 1e-20
    energetic = total > floor * (10.0 ** (float(prominence_db) / 10.0))
    mask = energetic & (gamma2 < float(coherence_threshold))
    return freqs, mask, gamma2


def _bin_mask(freqs: np.ndarray, freqs_hz: list[float], half_width: int = EVAL_HALF_WIDTH_BINS) -> np.ndarray:
    """把若干"真值频点"映射成 bin 掩码（每点 ±half_width 个 bin）。"""
    mask = np.zeros(freqs.size, dtype=bool)
    for f in freqs_hz:
        idx = int(np.argmin(np.abs(freqs - float(f))))
        lo = max(0, idx - half_width)
        hi = min(freqs.size, idx + half_width + 1)
        mask[lo:hi] = True
    return mask


def _confusion(pred: np.ndarray, positives: np.ndarray, negatives: np.ndarray) -> ConfusionMatrix:
    tp = int(np.count_nonzero(pred & positives))
    fp = int(np.count_nonzero(pred & negatives))
    fn = int(np.count_nonzero(~pred & positives))
    tn = int(np.count_nonzero(~pred & negatives))
    return ConfusionMatrix(tp=tp, fp=fp, fn=fn, tn=tn)


def evaluate_scenario(name: str, ch_a: np.ndarray, ch_b: np.ndarray, sample_rate: float, *,
                      rfi_freqs_hz: list[float], signal_freqs_hz: list[float],
                      coherence_threshold: float = DEFAULT_COHERENCE_THRESHOLD,
                      prominence_db: float = DEFAULT_PROMINENCE_DB) -> ScenarioResult:
    """在一个构造场景上同时跑「相关判据」与「单通道能量基线」，出混淆矩阵。"""
    freqs, mask_corr, gamma2 = detect_by_coherence(
        ch_a, ch_b, sample_rate, coherence_threshold=coherence_threshold,
        prominence_db=prominence_db)

    # 基线：既有单通道能量峰判据（在其原始分辨率上算，再映射到本模块的 bin 网格）
    base_freqs, base_power = power_spectrum(np.asarray(ch_a, dtype=float), sample_rate)
    base_peaks = detect_rfi_narrowband(np.asarray(ch_a, dtype=float), sample_rate)
    mask_base = _bin_mask(freqs, base_peaks)

    positives = _bin_mask(freqs, rfi_freqs_hz)
    negatives = _bin_mask(freqs, signal_freqs_hz)
    # 两者重叠时（频点太近）以正类为准，避免同一个 bin 既算 TP 又算 FP
    negatives &= ~positives

    extra = {
        "frames": int(_frames(np.asarray(ch_a, dtype=float), DEFAULT_FRAME_LEN, DEFAULT_HOP).shape[0]),
        "coherence_threshold": coherence_threshold,
        "prominence_db": prominence_db,
        "gamma2_at_rfi": [round(float(gamma2[int(np.argmin(np.abs(freqs - f)))]), 4) for f in rfi_freqs_hz],
        "gamma2_at_signal": [round(float(gamma2[int(np.argmin(np.abs(freqs - f)))]), 4) for f in signal_freqs_hz],
        "baseline_peaks_hz": [round(p, 2) for p in base_peaks],
        "base_bin_hz": round(float(base_freqs[1] - base_freqs[0]) if base_freqs.size > 1 else 0.0, 4),
        "eval_bin_hz": round(float(freqs[1] - freqs[0]) if freqs.size > 1 else 0.0, 4),
        "baseline_peak_power_db": [round(float(10.0 * np.log10(base_power[int(np.argmin(np.abs(base_freqs - p)))] + 1e-20)), 2)
                                   for p in base_peaks],
    }
    return ScenarioResult(name=name,
                          correlation=_confusion(mask_corr, positives, negatives),
                          energy_baseline=_confusion(mask_base, positives, negatives),
                          extra=extra)


# --------------------------------------------------------------------------- #
# 三个构造场景（测试与 demo 共用）
# --------------------------------------------------------------------------- #
DEMO_SAMPLE_RATE = 1000.0
DEMO_N = 4096
RFI_HZ = 180.0            # 本地干扰：**只进 ch_a**
SIGNAL_HZ = 120.0         # 真信号：两路同源（固定相位差）
CH_PHASE_RAD = 0.4
DEMO_SEED = 20261017
DEMO_SNR_DB = 12.0


def _tone(n: int, fs: float, f: float, amp: float, phase: float = 0.0) -> np.ndarray:
    t = np.arange(n, dtype=float) / float(fs)
    return amp * np.cos(2.0 * math.pi * f * t + phase)


def build_scenarios(seed: int = DEMO_SEED, snr_db: float = DEMO_SNR_DB) -> list[tuple[str, np.ndarray, np.ndarray, list[float], list[float]]]:
    """构造三类场景：纯本地干扰 / 纯真信号 / 混合。

    返回 ``[(name, ch_a, ch_b, rfi_freqs, signal_freqs), …]``
    """
    rng = np.random.default_rng(seed)
    n, fs = DEMO_N, DEMO_SAMPLE_RATE
    sig_power = 0.5

    def noise() -> np.ndarray:
        return rng.normal(0.0, math.sqrt(sig_power / (10.0 ** (snr_db / 10.0))), n)

    scenarios = []
    # 1) 纯本地干扰：只进 ch_a
    a = _tone(n, fs, RFI_HZ, 1.0) + noise()
    b = noise()
    scenarios.append(("local_only", a, b, [RFI_HZ], []))
    # 2) 纯真信号：两路同源（固定相位差）
    common = _tone(n, fs, SIGNAL_HZ, 1.0)
    a = common + noise()
    b = _tone(n, fs, SIGNAL_HZ, 1.0, CH_PHASE_RAD) + noise()
    scenarios.append(("signal_only", a, b, [], [SIGNAL_HZ]))
    # 3) 混合：本地干扰（只 ch_a）+ 真信号（两路）
    a = _tone(n, fs, RFI_HZ, 1.0) + common + noise()
    b = _tone(n, fs, SIGNAL_HZ, 1.0, CH_PHASE_RAD) + noise()
    scenarios.append(("mixed", a, b, [RFI_HZ], [SIGNAL_HZ]))
    return scenarios


def run_all(seed: int = DEMO_SEED, snr_db: float = DEMO_SNR_DB) -> list[ScenarioResult]:
    return [evaluate_scenario(name, a, b, DEMO_SAMPLE_RATE,
                              rfi_freqs_hz=rfi, signal_freqs_hz=sig)
            for name, a, b, rfi, sig in build_scenarios(seed=seed, snr_db=snr_db)]


def _fmt_matrix(label: str, cm: ConfusionMatrix) -> str:
    dr = "n/a" if math.isnan(cm.detection_rate) else f"{cm.detection_rate * 100:.1f}%"
    fa = "n/a" if math.isnan(cm.false_alarm_rate) else f"{cm.false_alarm_rate * 100:.1f}%"
    return (f"  {label:16s} confusion(tp={cm.tp} fp={cm.fp} fn={cm.fn} tn={cm.tn})  "
            f"detection_rate={dr}  false_alarm={fa}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RFI 相关监测（工单256 任务B）")
    ap.add_argument("--demo", action="store_true", help="跑三场景并打印混淆矩阵/检测率/误报率")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--snr-db", type=float, default=DEMO_SNR_DB)
    args = ap.parse_args(argv)

    results = run_all(snr_db=args.snr_db)
    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=1))
        return 0

    print("RFI 相关监测（工单256 任务B）· 扩既有 rfi 模块，未重写任何既有函数")
    print(f"场景：fs={DEMO_SAMPLE_RATE:.0f} Hz, N={DEMO_N}, 干扰 {RFI_HZ} Hz(仅 ch_a), "
          f"真信号 {SIGNAL_HZ} Hz(两路同源, 相位差 {CH_PHASE_RAD} rad), SNR={args.snr_db:.0f} dB")
    print(f"帧长 {DEFAULT_FRAME_LEN} / hop {DEFAULT_HOP}；相干阈值 {DEFAULT_COHERENCE_THRESHOLD}；"
          f"能量门限 {DEFAULT_PROMINENCE_DB} dB")
    print()
    for r in results:
        print(f"[{r.name}]")
        print(_fmt_matrix("相关判据", r.correlation))
        print(_fmt_matrix("单通道能量基线", r.energy_baseline))
        print(f"  γ²@rfi={r.extra['gamma2_at_rfi']}  γ²@signal={r.extra['gamma2_at_signal']}  "
              f"基线峰={r.extra['baseline_peaks_hz']}")
        print()
    mixed = next(r for r in results if r.name == "mixed")
    print(f"混合场景误报率：相关 {mixed.correlation.false_alarm_rate * 100:.1f}% "
          f"vs 单通道能量 {mixed.energy_baseline.false_alarm_rate * 100:.1f}%")
    print("⚠️ 指标仅为本仓构造场景实测，非论文数值复现。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
