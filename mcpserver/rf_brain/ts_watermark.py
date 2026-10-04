"""S18 LVQMark 时序水印（频谱/传感数据鲁棒水印，编辑攻击下稳定检测）

来源授粉点：digest-g1-1 2608.19727（LVQMark Time Series Watermark）——对时序数据
嵌入不可见水印，编辑攻击下仍可稳定检测。迁移到 rf_brain：用「确定性的伪随机 ±1 码
（按密钥展开）」做扩频式水印，检测端做归一化相关。扩频天然抗噪、抗局部篡改、抗截断
（截断后仍按位置对齐同一码序列）。

不可见性：水印幅度 = strength × 信号标准差（默认 3%），数据质量影响 ≤5%。

纯 numpy 实现，无第三方依赖。安全注意：密钥只做哈希派生，不落地明文。
"""
from __future__ import annotations

import hashlib

import numpy as np

_DEFAULT_STRENGTH = 0.03
_DEFAULT_THRESHOLD = 0.5 * _DEFAULT_STRENGTH  # 检测阈值 = 0.5× 嵌入强度


def _seed_of(key: str) -> int:
    """把密钥字符串哈希成 64 位随机种子（不落地明文）。"""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _chip(key: str, length: int) -> np.ndarray:
    """按密钥确定性展开长度为 `length` 的 ±1 码序列。

    关键性质：同一密钥不同 length 时，前 min(lengths) 个元素一致 → 支持截断对齐。
    """
    rng = np.random.default_rng(_seed_of(key))
    return (rng.integers(0, 2, size=length) * 2 - 1).astype(float)


def embed(series: np.ndarray, key: str, strength: float = _DEFAULT_STRENGTH) -> np.ndarray:
    """嵌入不可见水印：series + strength·std·chip。"""
    series = np.asarray(series, dtype=float)
    chip = _chip(key, series.size)
    scale = strength * (float(np.std(series)) if np.std(series) > 0 else 1.0)
    return series + scale * chip


def detect(series: np.ndarray, key: str, threshold: float = _DEFAULT_THRESHOLD) -> bool:
    """检测水印：归一化相关 > 阈值则判存在。"""
    series = np.asarray(series, dtype=float)
    if series.size < 8 or np.std(series) == 0.0:
        return False
    chip = _chip(key, series.size)
    rho = float(np.mean((series - series.mean()) * chip) / np.std(series))
    return rho > threshold


def correlation(series: np.ndarray, key: str) -> float:
    """返回归一化相关系数（诊断用）。"""
    series = np.asarray(series, dtype=float)
    if series.size < 8 or np.std(series) == 0.0:
        return 0.0
    chip = _chip(key, series.size)
    return float(np.mean((series - series.mean()) * chip) / np.std(series))


def quality_impact(original: np.ndarray, watermarked: np.ndarray) -> float:
    """数据质量影响 = 相对 RMSE（水印幅度相对原信号 RMS 的比例）。"""
    original = np.asarray(original, dtype=float)
    watermarked = np.asarray(watermarked, dtype=float)
    denom = float(np.std(original)) or 1.0
    return float(np.sqrt(np.mean((watermarked - original) ** 2)) / denom)


# ---------- 编辑攻击（评测用，非攻击工具） ----------


def edit_add_noise(series: np.ndarray, snr_db: float = 20.0, seed: int = 0) -> np.ndarray:
    """加性高斯噪声（SNR dB）。"""
    series = np.asarray(series, dtype=float)
    rng = np.random.default_rng(seed)
    noise_power = 10.0 ** (-snr_db / 10.0) * float(np.var(series))
    return series + np.sqrt(noise_power) * rng.standard_normal(series.size)


def edit_perturb(series: np.ndarray, frac: float = 0.2, factor: float = 2.0, seed: int = 0) -> np.ndarray:
    """局部篡改：随机 frac 比例的样本乘以 factor。"""
    series = np.asarray(series, dtype=float).copy()
    rng = np.random.default_rng(seed)
    idx = rng.choice(series.size, int(series.size * frac), replace=False)
    series[idx] *= factor
    return series


def edit_crop(series: np.ndarray, frac: float = 0.7) -> np.ndarray:
    """截断：只保留前 frac 比例的样本。"""
    series = np.asarray(series, dtype=float)
    return series[: int(series.size * frac)]
