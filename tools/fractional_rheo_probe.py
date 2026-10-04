"""分数阶流变本构拟合（卷101 W101-02 · GPL-3.0 只参考设计，独立实现）。

设计参考：mirandi1/pyRheo（GPL-3.0）的分数阶 Maxwell/Zener/springpot 模型族——
本模块为**从零独立实现**（仅 numpy/scipy），未引用/复制 pyRheo 源码：
- springpot（分数阶元件）：松弛模量 G(t) ∝ t^(-α)，0<α<1
- 分数阶 Maxwell：springpot 与弹簧串联的松弛
- 拟合：对数域最小二乘（curve_fit）
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import gamma


def springpot_modulus(t: np.ndarray, c: float, alpha: float) -> np.ndarray:
    """springpot 松弛模量：G(t) = C * t^(-α) / Γ(1-α)。"""
    t = np.asarray(t, dtype=float)
    return c * np.power(t, -alpha) / gamma(1.0 - alpha)


def fractional_maxwell(t: np.ndarray, c: float, alpha: float, tau: float) -> np.ndarray:
    """分数阶 Maxwell 松弛（单松弛时间近似）：G(t) = C * t^(-α) * exp(-t/τ)。"""
    t = np.asarray(t, dtype=float)
    return c * np.power(t, -alpha) * np.exp(-t / tau)


def fit_springpot(t: np.ndarray, g: np.ndarray) -> tuple[float, float]:
    """对数域拟合 springpot，返回 (C, α)。"""
    log_t = np.log(np.maximum(t, 1e-12))
    log_g = np.log(np.maximum(g, 1e-12))
    # log G = log(C/Γ(1-α)) - α log t → 线性拟合
    slope, intercept = np.polyfit(log_t, log_g, 1)
    alpha = float(-slope)
    c = float(np.exp(intercept) * gamma(1.0 - alpha))
    return c, alpha


def fit_fractional_maxwell(t: np.ndarray, g: np.ndarray) -> tuple[float, float, float]:
    """对数域拟合分数阶 Maxwell（先幂律后指数修正），返回 (C, α, τ)。"""
    c0, alpha0 = fit_springpot(t, g)

    def _model(tt, c, alpha, tau):
        return c * np.power(tt, -alpha) * np.exp(-tt / tau)

    popt, _ = curve_fit(
        _model, np.asarray(t, dtype=float), np.asarray(g, dtype=float),
        p0=[c0, alpha0, np.max(t) * 2.0], maxfev=20000,
    )
    return float(popt[0]), float(popt[1]), float(popt[2])
