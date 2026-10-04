"""R07 验收测试：RIS CS-AO 相位闭合解原型。

覆盖：
  1. 无约束（γ=0）：CS-AO 退化为纯波束对准，目标增益 ≈ N
  2. QoS 满足：中等 γ 下用户增益 ≥ γ
  3. 单调权衡：γ 越大目标增益越小（闭合解在两者间折中）
  4. 优于随机：同 QoS 下 CS-AO 目标增益显著高于随机相位

运行：python -m pytest mcpserver/rf_brain/prototypes/test_ris_csao.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import ris_csao as ris

N = 64
PHI_T = np.radians(10.0)
PHI_U = np.radians(-25.0)


def test_unconstrained_matches_steering():
    r = ris.cs_ao(N, PHI_T, PHI_U, gamma=0.0)
    assert r["satisfied"]
    assert r["target_gain"] == pytest.approx(N, rel=0.01)  # 纯对准 → 满增益


def test_qos_satisfied():
    gamma = 0.4 * N
    r = ris.cs_ao(N, PHI_T, PHI_U, gamma)
    assert r["satisfied"]
    assert r["user_gain"] >= gamma - 1e-6


def test_monotonic_tradeoff():
    g1 = ris.cs_ao(N, PHI_T, PHI_U, 0.1 * N)["target_gain"]
    g2 = ris.cs_ao(N, PHI_T, PHI_U, 0.7 * N)["target_gain"]
    assert g2 < g1  # 更严 QoS → 目标增益被挤占


def test_better_than_random():
    gamma = 0.4 * N
    r = ris.cs_ao(N, PHI_T, PHI_U, gamma)
    rng = np.random.default_rng(0)
    c_rand = np.exp(1j * rng.uniform(0, 2 * np.pi, N))
    g_t = ris.ris_steering(N, PHI_T)
    g_u = ris.ris_steering(N, PHI_U)
    assert r["target_gain"] > ris.ris_gain(c_rand, g_t)
    # 且随机方案大概率不满足 QoS，CS-AO 满足
    assert r["user_gain"] >= gamma - 1e-6
