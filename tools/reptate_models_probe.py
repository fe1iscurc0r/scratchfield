"""缠结高分子理论最小拟合（卷101 W101-03 · GPL-3.0 只参考设计，独立实现）。

设计参考：jorge-ramirez-upm/RepTate（GPL-3.0）的 reptation/Doi-Edwards 理论模型族——
本模块为**从零独立实现**（仅 numpy/scipy），未引用/复制 RepTate 源码：
- 单链 reptation 松弛谱：连续谱 H(τ) ∝ (τ/τd)^(-1/2)（τ<τd），长时截断
- 多模 Maxwell 离散谱逼近 + 松弛模量 G(t) 重建
- 理论谱与实验 G(t) 的最小二乘对齐（仅谱参数缩放）
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit


def reptation_spectrum(tau: np.ndarray, g0: float, tau_d: float) -> np.ndarray:
    """Doi-Edwards 单链松弛谱：H(τ) = G0 * (τ/τd)^(-1/2)，τ ≤ τd；τ > τd 截为 0。"""
    tau = np.asarray(tau, dtype=float)
    out = np.where(tau <= tau_d, g0 * np.power(tau / tau_d, -0.5), 0.0)
    return out


def relaxation_modulus(t: np.ndarray, g0: float, tau_d: float, n_modes: int = 50) -> np.ndarray:
    """Doi-Edwards 松弛模量（Rouse 模态和形式，标准教材式）：

        G(t) = G0 * (8/π²) * Σ_{p 奇} (1/p²) exp(-p² t/τd)

    τd 只出现在指数内，函数平滑可微（拟合友好）；独立实现，未复制 RepTate 源码。
    """
    t = np.asarray(t, dtype=float)
    out = np.zeros_like(t, dtype=float)
    for p in range(1, 2 * n_modes, 2):
        out = out + (1.0 / (p * p)) * np.exp(-(p * p) * t / tau_d)
    return g0 * (8.0 / np.pi ** 2) * out


def fit_tau_d(t: np.ndarray, g: np.ndarray, g0_fixed: float) -> float:
    """固定 G0 拟合解缠时间 τd（对数域最小二乘）。"""
    def _model(tt, tau_d):
        return relaxation_modulus(tt, g0_fixed, max(tau_d, 1e-6))

    popt, _ = curve_fit(
        _model, np.asarray(t, dtype=float), np.asarray(g, dtype=float),
        p0=[np.max(t)], maxfev=40000,
    )
    return float(popt[0])
