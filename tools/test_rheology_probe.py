"""rheology_probe 验收硬线（卷101 W101-01）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.rheology_probe import (  # noqa: E402
    RheoFreqData,
    RheoTimeData,
    fit_maxwell_relaxation,
    fit_voigt_creep,
    generalized_maxwell,
    maxwell_relaxation,
    voigt_creep,
)


def test_time_data_class():
    """数据类构造：时间-应力/应变字段与存在性判断。"""
    d = RheoTimeData(np.linspace(0, 10, 100), stress=np.ones(100))
    assert d.has_stress() is True and d.has_strain() is False
    f = RheoFreqData(np.logspace(-2, 2, 50))
    assert f.freq.shape == (50,)


def test_maxwell_fit_converges():
    """应力松弛拟合收敛：从带噪合成数据恢复 (G0, τ)。"""
    t = np.linspace(0.01, 10, 200)
    rng = np.random.default_rng(0)
    g_true = 100.0 * np.exp(-t / 2.0)
    g = g_true + rng.normal(0, 1.0, t.size)
    g0, tau = fit_maxwell_relaxation(t, g)
    assert abs(g0 - 100.0) < 5.0
    assert abs(tau - 2.0) < 0.2


def test_voigt_creep_fit_converges():
    """蠕变拟合收敛：从合成数据恢复 (J0, τ)。"""
    t = np.linspace(0.01, 20, 200)
    rng = np.random.default_rng(1)
    j_true = 0.5 * (1.0 - np.exp(-t / 4.0))
    j = j_true + rng.normal(0, 0.005, t.size)
    j0, tau = fit_voigt_creep(t, j)
    assert abs(j0 - 0.5) < 0.03
    assert abs(tau - 4.0) < 0.3


def test_generalized_maxwell_superposition():
    """广义 Maxwell：多模叠加 + 长时趋近 G∞。"""
    t = np.linspace(1e-4, 100, 500)
    g = generalized_maxwell(t, [(50.0, 1.0), (30.0, 10.0)], g_inf=20.0)
    assert abs(g[0] - 100.0) < 1e-2  # t→0：G0 之和 + G∞
    assert abs(g[-1] - 20.0) < 5e-3  # t→∞：只剩 G∞（残余松弛 < 5e-3）
    assert np.all(np.diff(g) <= 1e-9)  # 单调不增


def test_maxwell_analytic_value():
    """解析值核对：G(t=τ) = G0/e。"""
    assert abs(maxwell_relaxation(np.array([2.0]), 10.0, 2.0)[0] - 10.0 / np.e) < 1e-9
    assert abs(voigt_creep(np.array([1e9]), 1.0, 5.0)[0] - 1.0) < 1e-9  # t→∞ 蠕变饱和
