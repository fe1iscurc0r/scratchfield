"""W58-02 验收测试：自适应跳频（≥4 用例）。

运行：python -m pytest tools/test_adaptive_fh.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from adaptive_fh import loss_rate, simulate_delivery, uep_to_fh_policy


def test_policy_mapping():
    """语义等级 → 跳频策略映射正确。"""
    assert uep_to_fh_policy(0) == (True, 2)
    assert uep_to_fh_policy(1) == (True, 1)
    assert uep_to_fh_policy(2) == (False, 0)


def test_high_significance_loss_lower_than_low():
    """高显著符号在干扰下的丢包率 < 低显著符号。"""
    rng = np.random.default_rng(0)
    levels = rng.integers(0, 3, 2000)
    res = simulate_delivery(levels, seed=0)
    assert loss_rate(res, "semantic", 0) < loss_rate(res, "semantic", 2)
    assert loss_rate(res, "semantic", 1) < loss_rate(res, "semantic", 2)


def test_semantic_beats_uniform_for_high_significance():
    """语义感知跳频对高显著符号送达率高于均匀跳频。"""
    rng = np.random.default_rng(0)
    levels = rng.integers(0, 3, 2000)
    res = simulate_delivery(levels, seed=0)
    assert res["semantic"][0] > res["uniform"][0]
    assert res["semantic"][1] > res["uniform"][1]


def test_low_significance_not_extra_consumed():
    """L2 常规数据不额外消耗资源（语义与均匀接近）。"""
    rng = np.random.default_rng(0)
    levels = rng.integers(0, 3, 2000)
    res = simulate_delivery(levels, seed=0)
    assert abs(res["semantic"][2] - res["uniform"][2]) < 0.05
