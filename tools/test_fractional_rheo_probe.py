"""fractional_rheo_probe 验收硬线（卷101 W101-02）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fractional_rheo_probe import (  # noqa: E402
    fit_fractional_maxwell,
    fit_springpot,
    fractional_maxwell,
    springpot_modulus,
)


def test_springpot_power_law():
    """springpot 幂律：对数域斜率 = -α。"""
    t = np.logspace(-2, 2, 100)
    g = springpot_modulus(t, c=10.0, alpha=0.5)
    log_t, log_g = np.log(t), np.log(g)
    slope, _ = np.polyfit(log_t, log_g, 1)
    assert abs(slope + 0.5) < 1e-9


def test_fit_springpot_recovers_params():
    """springpot 拟合：从带噪合成数据恢复 (C, α)。"""
    t = np.logspace(-2, 2, 200)
    rng = np.random.default_rng(0)
    g_true = springpot_modulus(t, c=8.0, alpha=0.4)
    g = g_true * (1.0 + rng.normal(0, 0.01, t.size))
    c, alpha = fit_springpot(t, g)
    assert abs(alpha - 0.4) < 0.02
    assert abs(c - 8.0) < 1.0


def test_fractional_maxwell_decay_dominates_late():
    """分数阶 Maxwell：短时幂律、长时指数截断（单调递减）。"""
    t = np.logspace(-3, 3, 200)
    g = fractional_maxwell(t, c=5.0, alpha=0.3, tau=10.0)
    assert np.all(np.diff(g) <= 1e-12)  # 单调
    assert g[-1] < g[0] * 1e-3  # 长时指数衰减到接近零
