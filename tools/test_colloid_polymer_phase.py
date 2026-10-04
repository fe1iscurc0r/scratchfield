"""M161 胶体-聚合物相行为原型测试（pytest）。

运行：python -m pytest tools/test_colloid_polymer_phase.py -q
验收：S(0) 随耗散强度单调上升（RDF→压缩率链路正确），且能定位相分离阈值。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from colloid_polymer_phase import (
    compressibility_vs_depletion,
    find_spinodal,
    radial_distribution,
)


def test_hard_core_and_depletion_g():
    r = np.linspace(0.0, 3.0, 1000)
    g0 = radial_distribution(r, depletion=0.0)      # 纯硬球
    g1 = radial_distribution(r, depletion=1.0)      # 有耗散
    assert np.all(g0[r < 1.0] == 0.0)               # 硬核内 g=0
    # 接触附近：耗散使 g>1（粒子聚集），纯硬球不聚集
    near = (r > 1.0) & (r < 1.5)
    assert np.mean(g1[near]) > np.mean(g0[near])


def test_compressibility_monotonic_and_spinodal():
    deps = np.linspace(0.0, 6.0, 61)
    deps, S0 = compressibility_vs_depletion(deps, rho=0.4)
    # S(0) 随耗散强度单调上升（越聚集越接近相分离）
    assert np.all(np.diff(S0) > 0), "S(0) 未随耗散单调上升"
    spin = find_spinodal(deps, S0, threshold=10.0)
    assert spin is not None, "未检测到相分离阈值"
    assert 0.0 < spin < 6.0
