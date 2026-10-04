# -*- coding: utf-8 -*-
"""rf_brain 滤波链（W61-03 · biquad + butterworth）。

依据 docs/dsp-filters-授粉报告.md §2：numpy 实现 biquad 基类 + butterworth
低通/带通/高通，闭环「sensor → feature_extractor 无滤波」断点。

系数采用 Audio EQ Cookbook 标准约定（Butterworth Q=1/√2）：
  ω = 2π·fc/fs,  α = sin(ω)/(2Q)
  LPF: b0=(1-cosω)/2, b1=1-cosω, b2=(1-cosω)/2
  HPF: b0=(1+cosω)/2, b1=-(1+cosω), b2=(1+cosω)/2
  共同 a: a0=1+α, a1=-2cosω, a2=1-α

纯 numpy。运行：python -m mcpserver.rf_brain.filters
"""
from __future__ import annotations

import math

import numpy as np


class Biquad:
    """二阶节滤波器（transposed direct form II），状态跨 chunk 保留。"""

    def __init__(self, b: np.ndarray, a: np.ndarray) -> None:
        self.b = b.astype(float) / a[0]
        self.a = a.astype(float) / a[0]
        self.z1 = 0.0
        self.z2 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        b0, b1, b2 = self.b
        a1, a2 = self.a[1], self.a[2]
        y = np.zeros_like(x, dtype=float)
        for i, xi in enumerate(x):
            out = b0 * xi + self.z1
            self.z1 = b1 * xi - a1 * out + self.z2
            self.z2 = b2 * xi - a2 * out
            y[i] = out
        return y


def _coeffs(fc: float, fs: float) -> tuple[float, float, float]:
    """ω 与 α（Butterworth Q=1/√2）。"""
    w = 2.0 * math.pi * fc / fs
    alpha = math.sin(w) / (2.0 * (1.0 / math.sqrt(2.0)))
    return w, alpha


def butterworth_lpf(fc: float, fs: float) -> Biquad:
    w, alpha = _coeffs(fc, fs)
    cosw = math.cos(w)
    b = np.array([(1 - cosw) / 2, 1 - cosw, (1 - cosw) / 2])
    a = np.array([1 + alpha, -2 * cosw, 1 - alpha])
    return Biquad(b, a)


def butterworth_hpf(fc: float, fs: float) -> Biquad:
    w, alpha = _coeffs(fc, fs)
    cosw = math.cos(w)
    b = np.array([(1 + cosw) / 2, -(1 + cosw), (1 + cosw) / 2])
    a = np.array([1 + alpha, -2 * cosw, 1 - alpha])
    return Biquad(b, a)


def butterworth_bpf(flow: float, fhigh: float, fs: float) -> Biquad:
    """带通（中心 fc、带宽 BW，用 cookbook BPF 公式）。"""
    fc = math.sqrt(flow * fhigh)
    bw = fhigh - flow
    w = 2.0 * math.pi * fc / fs
    sinw = math.sin(w)
    alpha = sinw / (2.0 * (1.0 / math.sqrt(2.0)))
    b = np.array([alpha, 0.0, -alpha])
    a = np.array([1 + alpha, -2 * math.cos(w), 1 - alpha])
    return Biquad(b, a)


if __name__ == "__main__":
    fs = 48000.0
    t = np.arange(fs) / fs
    x = np.sin(2 * np.pi * 1000 * t) + np.sin(2 * np.pi * 8000 * t)
    f = butterworth_lpf(2000.0, fs)
    y = f.process(x)
    print("LPF 输出 RMS:", round(float(np.sqrt(np.mean(y ** 2))), 3), "（应主要保留 1kHz 分量）")
