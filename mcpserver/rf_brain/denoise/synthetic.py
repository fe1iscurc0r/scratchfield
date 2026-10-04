"""合成信号与噪声生成器（D-01 · Noise2Noise 无标签训练对）

纯 numpy，无硬件依赖。Noise2Noise 的核心假设是「噪声独立且零均值」——
对同一干净信号 x 取两次独立带噪观测 y1 = x + n1、y2 = x + n2，
用 y1 预测 y2 训练去噪网络即可收敛到干净信号（网络无法预测独立噪声，
只能学到其期望 = x）。本模块生成干净的 x 与成对的 (y1, y2)。

信号类型: sine（正弦）/ sweep（扫频 chirp）/ pulse（脉冲串，模拟 OOK 包络）。
噪声类型: gaussian（高斯）/ salt_pepper（椒盐脉冲）/ rf_envelope（射频包络起伏）。
"""
from __future__ import annotations

import numpy as np

SIGNAL_TYPES = ("sine", "sweep", "pulse")
NOISE_TYPES = ("gaussian", "salt_pepper", "rf_envelope")


# --------------------------------------------------------------------------- #
# 信号生成
# --------------------------------------------------------------------------- #

def sine(n: int, sample_rate: float, *, freq: float = 3.0,
         amplitude: float = 1.0, phase: float = 0.0) -> np.ndarray:
    """正弦信号。freq 单位 Hz（相对慢变，便于 MCU 端低采样率演示）。"""
    t = np.arange(int(n)) / float(sample_rate)
    return amplitude * np.sin(2.0 * np.pi * freq * t + phase)


def sweep(n: int, sample_rate: float, *, f0: float = 0.5, f1: float = 8.0,
          amplitude: float = 1.0) -> np.ndarray:
    """线性扫频（chirp）信号，f0 → f1 线性过渡。"""
    t = np.arange(int(n)) / float(sample_rate)
    total = max(float(int(n) - 1) / float(sample_rate), 1e-12)
    phase = 2.0 * np.pi * (f0 * t + (f1 - f0) / (2.0 * total) * t ** 2)
    return amplitude * np.sin(phase)


def pulse_train(n: int, sample_rate: float, *, period: float = 20.0,
                duty: float = 0.3, amplitude: float = 1.0) -> np.ndarray:
    """脉冲串（矩形脉冲），模拟 OOK 包络。period 单位样本，duty ∈ (0,1)。"""
    n = int(n)
    period = max(int(period), 1)
    duty = float(np.clip(duty, 0.05, 0.95))
    t = np.arange(n)
    on = (t % period) < int(period * duty)
    return np.where(on, amplitude, 0.0).astype(float)


_SIGNAL_BUILDERS = {
    "sine": sine,
    "sweep": sweep,
    "pulse": pulse_train,
}


def make_signal(signal_type: str, n: int, sample_rate: float,
                signal_params: dict | None = None) -> np.ndarray:
    """按类型名生成干净信号。未知类型抛 ValueError。"""
    if signal_type not in _SIGNAL_BUILDERS:
        raise ValueError(f"未知信号类型 {signal_type!r}，可选: {SIGNAL_TYPES}")
    return _SIGNAL_BUILDERS[signal_type](int(n), sample_rate, **(signal_params or {}))


# --------------------------------------------------------------------------- #
# 噪声（每次调用按 seed 独立，保证两次观测噪声不相关）
# --------------------------------------------------------------------------- #

def gaussian_noise(clean: np.ndarray, sigma: float = 0.3, seed: int = 0) -> np.ndarray:
    """加性高斯白噪声。"""
    clean = np.asarray(clean, dtype=float)
    rng = np.random.default_rng(seed)
    return clean + rng.normal(0.0, float(sigma), clean.shape)


def salt_pepper_noise(clean: np.ndarray, density: float = 0.05,
                      amplitude: float = 1.5, seed: int = 0) -> np.ndarray:
    """椒盐脉冲噪声：随机位置叠加 ±amplitude 脉冲（零均值、独立）。"""
    clean = np.asarray(clean, dtype=float)
    rng = np.random.default_rng(seed)
    k = int(clean.size * float(np.clip(density, 0.0, 0.5)))
    idx = rng.choice(clean.size, size=k, replace=False) if k > 0 else np.array([], dtype=int)
    signs = rng.choice([-1.0, 1.0], size=k)
    noisy = clean.copy()
    noisy[idx] = clean[idx] + signs * amplitude
    return noisy


def _slow_envelope(n: int, seed: int) -> np.ndarray:
    """慢变随机包络（低通随机游走 → tanh 压到 (0,1) 附近），模拟射频带内起伏。"""
    rng = np.random.default_rng(seed)
    walk = np.cumsum(rng.normal(0.0, 1.0, n))
    kern = np.ones(20) / 20.0
    smooth = np.convolve(walk, kern, mode="same")
    smooth = smooth - smooth.mean()
    s = float(np.std(smooth))
    if s > 1e-12:
        smooth = smooth / s
    return 0.5 + 0.5 * np.tanh(smooth)


def rf_envelope_noise(clean: np.ndarray, sigma: float = 0.3, seed: int = 0) -> np.ndarray:
    """射频包络噪声：慢变包络调制的加性高斯噪声（模拟带内起伏底噪）。"""
    clean = np.asarray(clean, dtype=float)
    env = _slow_envelope(clean.size, seed)
    rng = np.random.default_rng(seed + 99991)  # 包络与瞬时噪声用不同随机流
    return clean + env * rng.normal(0.0, float(sigma), clean.shape)


_NOISE_BUILDERS = {
    "gaussian": gaussian_noise,
    "salt_pepper": salt_pepper_noise,
    "rf_envelope": rf_envelope_noise,
}


def apply_noise(clean, noise_type: str, seed: int = 0, **noise_params) -> np.ndarray:
    """按类型名叠加噪声（seed 固定可复现）。"""
    if noise_type not in _NOISE_BUILDERS:
        raise ValueError(f"未知噪声类型 {noise_type!r}，可选: {NOISE_TYPES}")
    return _NOISE_BUILDERS[noise_type](clean, seed=seed, **noise_params)


def make_pair(clean, noise_type: str, seed: int = 0, **noise_params) -> tuple[np.ndarray, np.ndarray]:
    """两次独立带噪观测（Noise2Noise 无标签训练对）。"""
    y1 = apply_noise(clean, noise_type, seed=seed, **noise_params)
    y2 = apply_noise(clean, noise_type, seed=seed + 1, **noise_params)
    return y1, y2


def generate(signal_type: str, noise_type: str, n: int, sample_rate: float, *,
             signal_params: dict | None = None, noise_params: dict | None = None,
             seed: int = 0) -> dict:
    """一次性生成干净信号 + 成对带噪观测。

    返回 dict: {"clean": ..., "noisy1": ..., "noisy2": ...}
    """
    clean = make_signal(signal_type, int(n), sample_rate, signal_params)
    y1, y2 = make_pair(clean, noise_type, seed=seed, **(noise_params or {}))
    return {"clean": clean, "noisy1": y1, "noisy2": y2}
