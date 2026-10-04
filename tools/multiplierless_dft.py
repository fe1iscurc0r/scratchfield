"""multiplierless DFT 最小原型（W73-11 · 端上无乘法 FFT）。

依据 docs/edge-dsp-tools-评估.md：multiplierless DFT 用移位/加法近似 DFT 旋转
因子，省去乘法器，适配 FPGA/MCU（ESP32-S3 整数运算）。

原型（numpy）：
  - dft(x)：标准 DFT（参考）
  - multiplierless_dft(x)：把旋转因子量化到 2 的幂（±1, ±0.5, ±0.25, ±0.125），
    使每个「乘法」退化为移位（shift）——演示无乘法近似及其精度代价。

运行：
  python tools/multiplierless_dft.py
"""
from __future__ import annotations

import math

import numpy as np

# 2 的幂量化字典：把 cos/sin 值就近映射到可移位表示
_POW2 = [1.0, 0.5, 0.25, 0.125, 0.0625, 0.0]


def _quant(v: float) -> float:
    """就近映射到 2 的幂（含符号），乘法退化为移位。"""
    if v == 0:
        return 0.0
    sign = 1.0 if v >= 0 else -1.0
    a = abs(v)
    best = min(_POW2, key=lambda p: abs(p - a))
    return sign * best


def dft(x: np.ndarray) -> np.ndarray:
    """标准 DFT（参考）。"""
    n = len(x)
    k = np.arange(n)
    W = np.exp(-2j * math.pi * np.outer(k, k) / n)
    return W @ x


def multiplierless_dft(x: np.ndarray) -> np.ndarray:
    """multiplierless DFT：旋转因子量化到 2 的幂，乘法→移位+加法。"""
    n = len(x)
    X = np.zeros(n, dtype=complex)
    for f in range(n):
        acc = 0j
        for t in range(n):
            ang = 2 * math.pi * f * t / n
            c = _quant(math.cos(ang))   # 量化后乘法 = 移位
            s = _quant(-math.sin(ang))
            # 复数乘法由 (c + 1j*s) 与 x[t] 的移位-加法实现（概念上无真乘法）
            acc += complex(c * x[t].real, s * x[t].real)
        X[f] = acc
    return X


def approximation_error(x: np.ndarray) -> float:
    """量化 DFT 相对标准 DFT 的均方误差。"""
    a = dft(x)
    b = multiplierless_dft(x)
    return float(np.mean(np.abs(a - b) ** 2) / max(np.mean(np.abs(a) ** 2), 1e-12))


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    x = rng.normal(size=16)
    err = approximation_error(x)
    print(f"[multiplierless DFT] 相对 MSE = {err:.4f}")
    print(f"[标准 DFT] {np.round(dft(x)[:4], 3)}")
    print(f"[量化 DFT] {np.round(multiplierless_dft(x)[:4], 3)}")
