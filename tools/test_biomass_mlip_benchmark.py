"""M32 生物质分子势基准 基准脚本测试（pytest）。

运行：python -m pytest tools/test_biomass_mlip_benchmark.py -q
验收：基准脚本能计算统一指标，并能区分好/坏候选势。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from biomass_mlip_benchmark import (
    _make_reference,
    _perturb,
    bond_break_order_acc,
    energy_rmse,
    force_rmse,
    score,
)


def test_energy_rmse_meV_per_atom():
    # 单样本 1 meV 差（0.001 eV）→ RMSE = 1 meV
    pred = np.array([-100.001])
    ref = np.array([-100.0])
    assert abs(energy_rmse(pred, ref, n_atoms=1) - 1.0) < 1e-6


def test_bond_break_order_perfect_and_reversed():
    ref = np.array([0, 1, 2, 3])
    assert bond_break_order_acc(ref, ref) == 1.0
    assert bond_break_order_acc(np.array([3, 2, 1, 0]), ref) == 0.0


def test_benchmark_ranks_good_over_bad():
    ref = _make_reference(seed=0)
    good = _perturb(ref, noise=0.02, seed=1)
    bad = _perturb(ref, noise=0.5, bias=1.0, seed=2)
    s_good = score(good, ref, n_atoms=64)
    s_bad = score(bad, ref, n_atoms=64)
    assert s_good["energy_rmse_meV_atom"] < s_bad["energy_rmse_meV_atom"]
    assert s_good["stability_score"] > s_bad["stability_score"]
