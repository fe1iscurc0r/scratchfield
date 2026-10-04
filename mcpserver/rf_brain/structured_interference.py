"""射频大脑 · 结构化 RF 干扰抑制（R57）

授粉自 digest-g1-4 2608.24974（Clearing the Underbrush: AI-Enhanced RF Interference
Suppression）：AI 干扰抑制的关键是「先按结构分类、再对症抑制」——窄带/脉冲/宽带
三类干扰需要不同的抑制手段，一刀切的窄带陷波（R03）对非窄带干扰无能为力。

本模块承接 R03（``rfi_mitigation``）滤波链，把干扰按结构分类后分别抑制：
  - 窄带（单音/强谱峰） → 陷波（复用 rfi_mitigation.notch_filter）
  - 脉冲（时域突发）     → 时域门限置零（gating）
  - 宽带（白/色噪声底）   → 谱减法（Wiener 增益，估计噪声底后从幅度谱减去）

保真度口径与 R03 一致：相对干净参考的 S/N。验收：合成多类干扰场景下，
结构化抑制的保真度较 R03（仅窄带陷波）提升 ≥15%。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mcpserver.rf_brain import rfi_mitigation as rfi


def signal_fidelity_db(signal: np.ndarray, reference: np.ndarray) -> float:
    """相对干净参考的保真度（S/N，dB）：P(参考)/P(残差)，越大越好。"""
    s = np.asarray(signal, dtype=float)
    r = np.asarray(reference, dtype=float)
    sp = float(np.mean(r ** 2))
    rp = float(np.mean((s - r) ** 2))
    if rp <= 0.0:
        return 200.0
    return 10.0 * np.log10(sp / rp + 1e-12)


@dataclass
class InterferenceProfile:
    """结构化干扰分类结果。"""
    narrowband_hz: list[float] = field(default_factory=list)   # 窄带干扰频点
    pulse_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))  # 脉冲样本掩码
    wideband_level: float = 0.0   # 宽带噪声底估计（线性功率）


def classify_interference(
    signal: np.ndarray,
    sample_rate: float,
    *,
    prominence_db: float = 20.0,
    pulse_k: float = 2.0,
) -> InterferenceProfile:
    """按结构分类干扰：窄带（谱峰）、脉冲（时域突发）、宽带（噪声底）。"""
    x = np.asarray(signal, dtype=float)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("signal 必须为非空一维信号")

    # 窄带：显著谱峰（复用 R03 检测）
    narrowband = rfi.detect_rfi_narrowband(x, sample_rate, prominence_db=prominence_db)

    # 脉冲：时域幅度远超基线（基线 = 中位数幅度，脉冲样本只占极少数故不影响中位数）
    med = float(np.median(np.abs(x)))
    thr = pulse_k * max(med, 1e-9)
    pulse_mask = np.abs(x) > thr

    # 宽带：功率谱中位数（稳健噪声底估计）
    _, power = rfi.power_spectrum(x, sample_rate)
    wideband = float(np.median(power))

    return InterferenceProfile(narrowband_hz=narrowband, pulse_mask=pulse_mask, wideband_level=wideband)


def _spectral_subtract(x: np.ndarray, noise_level: float, alpha: float = 1.0) -> np.ndarray:
    """谱减法（Wiener 增益）：从幅度谱减去宽带噪声底，保留相位。

    Gain = sqrt(max(1 − α·noise/|X|², 0))，落在噪声底附近的 bin 被压低，
    高于噪声底的信号分量保留——抑制宽带噪声同时尽量保留信号。
    """
    X = np.fft.rfft(x)
    P = np.abs(X) ** 2
    gain = np.sqrt(np.clip(1.0 - alpha * noise_level / (P + 1e-12), 0.0, 1.0))
    return np.fft.irfft(X * gain, n=x.size)


@dataclass
class StructuredSuppressionResult:
    """结构化抑制结果。"""
    cleaned: np.ndarray
    profile: InterferenceProfile
    fidelity_db: float = 0.0

    def fidelity_linear(self) -> float:
        return 10.0 ** (self.fidelity_db / 10.0)


def suppress_structured(
    signal: np.ndarray,
    sample_rate: float,
    *,
    reference: np.ndarray | None = None,
    prominence_db: float = 20.0,
    pulse_k: float = 2.0,
    notch_bw_hz: float | None = None,
    wideband_alpha: float = 1.0,
) -> StructuredSuppressionResult:
    """端到端结构化抑制：窄带陷波 → 脉冲门限 → 宽带谱减。"""
    x = np.asarray(signal, dtype=float)
    sr = float(sample_rate)
    bw = float(notch_bw_hz) if notch_bw_hz else sr / 1000.0

    profile = classify_interference(x, sr, prominence_db=prominence_db, pulse_k=pulse_k)

    cleaned = x.copy()
    # 1) 窄带陷波
    for f0 in profile.narrowband_hz:
        cleaned = rfi.notch_filter(cleaned, sr, f0, bw)
    # 2) 脉冲门限置零
    if profile.pulse_mask.any():
        cleaned[profile.pulse_mask] = 0.0
    # 3) 宽带谱减
    if profile.wideband_level > 0.0:
        cleaned = _spectral_subtract(cleaned, profile.wideband_level, alpha=wideband_alpha)

    result = StructuredSuppressionResult(cleaned=cleaned, profile=profile)
    if reference is not None:
        result.fidelity_db = signal_fidelity_db(cleaned, reference)
    return result


def mixed_interference_signal(
    sample_rate: float = 4000.0,
    n: int = 16000,
    *,
    f_sig: float = 800.0,
    f_nb: float = 500.0,
    pulse_amp: float = 3.0,
    wideband_sigma: float = 0.2,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """合成「弱信号 + 窄带 + 脉冲 + 宽带」混合干扰场景。

    返回 (污染信号, 干净参考)。脉冲为时域强突发（R03 窄带陷波无法去除）。
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sample_rate
    s = 0.2 * np.sin(2.0 * np.pi * f_sig * t)                    # 弱信号（参考）
    nb = 1.0 * np.sin(2.0 * np.pi * f_nb * t)                    # 窄带干扰
    pulse = np.zeros(n)
    pulse[n // 2:n // 2 + 200] = pulse_amp                        # 时域脉冲突发
    wideband = wideband_sigma * rng.standard_normal(n)            # 宽带噪声
    return s + nb + pulse + wideband, s


__all__ = [
    "InterferenceProfile",
    "StructuredSuppressionResult",
    "classify_interference",
    "suppress_structured",
    "signal_fidelity_db",
    "mixed_interference_signal",
]
