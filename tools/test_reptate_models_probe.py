"""reptate_models_probe 验收硬线（卷101 W101-03）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reptate_models_probe import (  # noqa: E402
    fit_tau_d,
    relaxation_modulus,
    reptation_spectrum,
)


def test_reptation_spectrum_shape():
    """谱形状：τ≤τd 幂律 -1/2，τ>τd 截断为 0。"""
    tau = np.logspace(-6, 2, 200)
    h = reptation_spectrum(tau, g0=100.0, tau_d=1.0)
    assert h[0] > h[len(tau) // 2] > 0  # 幂律递减
    assert np.all(h[tau > 1.0] == 0.0)  # 截断


def test_relaxation_modulus_monotonic_decay():
    """G(t) 单调递减，t→0 极限为正、t→∞ 趋于 0。"""
    t = np.logspace(-4, 4, 300)
    g = relaxation_modulus(t, g0=100.0, tau_d=10.0)
    assert np.all(np.diff(g) <= 1e-12)
    assert g[0] > 0 and g[-1] < 1e-3


def test_fit_tau_d_reasonable():
    """τd 拟合：合成数据（τd=5）拟合回数量级正确（谱离散化近似）。"""
    t = np.logspace(-3, 3, 300)
    g_true = relaxation_modulus(t, g0=50.0, tau_d=5.0)
    tau_d = fit_tau_d(t, g_true, g0_fixed=50.0)
    assert 1.0 < tau_d < 25.0  # 数量级正确（离散谱近似容差宽）
