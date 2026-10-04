"""RHEOS 风格流变数据处理最小骨架（卷101 W101-01 · 独立实现）。

设计参考：JuliaRheology/RHEOS.jl（MIT，Julia）——只抄 API 设计到 Python，不移植代码：
- RheoTimeData（时间-应力/应变）+ RheoFreqData（频率-储能/损耗模量）数据模型
- 应力松弛（广义 Maxwell）与蠕变（Voigt/Kelvin）拟合
纯 numpy/scipy 独立实现，无 RHEOS 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import curve_fit


@dataclass
class RheoTimeData:
    """时间域数据（RheoTimeData 的 Python 等价）：t/stress/strain。"""
    t: np.ndarray
    stress: np.ndarray | None = None
    strain: np.ndarray | None = None

    def has_stress(self) -> bool:
        return self.stress is not None

    def has_strain(self) -> bool:
        return self.strain is not None


@dataclass
class RheoFreqData:
    """频率域数据：freq/storage(G')/loss(G'')。"""
    freq: np.ndarray
    storage: np.ndarray | None = None
    loss: np.ndarray | None = None


def maxwell_relaxation(t: np.ndarray, g0: float, tau: float) -> np.ndarray:
    """单模 Maxwell 应力松弛：G(t) = G0 * exp(-t/τ)。"""
    t = np.asarray(t, dtype=float)
    return g0 * np.exp(-t / tau)


def fit_maxwell_relaxation(t: np.ndarray, g: np.ndarray) -> tuple[float, float]:
    """对松弛数据拟合单模 Maxwell，返回 (G0, τ)。"""
    popt, _ = curve_fit(maxwell_relaxation, t, g, p0=[np.max(g), np.median(t)], maxfev=20000)
    return float(popt[0]), float(popt[1])


def voigt_creep(t: np.ndarray, j0: float, tau: float) -> np.ndarray:
    """Voigt/Kelvin 蠕变：J(t) = J0 * (1 - exp(-t/τ))。"""
    t = np.asarray(t, dtype=float)
    return j0 * (1.0 - np.exp(-t / tau))


def fit_voigt_creep(t: np.ndarray, j: np.ndarray) -> tuple[float, float]:
    """对蠕变数据拟合 Voigt 模型，返回 (J0, τ)。"""
    popt, _ = curve_fit(voigt_creep, t, j, p0=[np.max(j), np.median(t)], maxfev=20000)
    return float(popt[0]), float(popt[1])


def generalized_maxwell(t: np.ndarray, params: list[tuple[float, float]], g_inf: float = 0.0) -> np.ndarray:
    """广义 Maxwell：多模松弛之和 + G∞。"""
    out = np.full_like(np.asarray(t, dtype=float), g_inf)
    for g0, tau in params:
        out = out + g0 * np.exp(-np.asarray(t, dtype=float) / tau)
    return out
