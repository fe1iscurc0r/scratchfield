"""R55 验收测试：Agentic Autoresearch 功率控制（规则池 + 选择/微调循环）。

覆盖：
  1. SyntheticCellScenario：增益矩阵对称性、吞吐有限、坏参数拒绝
  2. 规则池：各策略返回合法功率向量（0..1、长度正确）
  3. PowerControlAgent：合成小区场景吞吐较固定满功率提升 ≥10%
  4. 迭代日志可审计（每轮有吞吐记录）

运行：python -m pytest mcpserver/rf_brain/test_power_control_agentic.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import power_control_agentic as pc


def test_scenario_gain_and_throughput():
    sc = pc.default_scenario(0)
    g = sc.gain_matrix
    assert g.shape == (3, 3)
    # 服务链路（对角线）应强于大部分干扰链路
    assert g[1, 1] > max(g[1, 0], g[1, 2])
    tp = sc.throughput(np.ones(3))
    assert np.isfinite(tp) and tp > 0


def test_scenario_rejects_bad_input():
    with pytest.raises(ValueError):
        pc.SyntheticCellScenario(np.array([0.0, 1.0]), np.array([0.0]))
    sc = pc.default_scenario(0)
    with pytest.raises(ValueError):
        sc.throughput(np.ones(2))


def test_rule_pool_returns_valid_power():
    sc = pc.default_scenario(0)
    for name, fn in pc.default_rule_pool().items():
        p = np.asarray(fn(sc), dtype=float)
        assert p.shape == (3,), name
        assert np.all(p >= 0.0) and np.all(p <= 1.0), name


def test_agent_improves_over_fixed_policy():
    """合成小区场景：Agent 找到的功率策略吞吐较固定满功率提升 ≥10%。"""
    sc = pc.default_scenario(seed=0)
    result = pc.PowerControlAgent(seed=0).search(sc)
    assert result.throughput > result.baseline_throughput
    assert result.improvement >= 1.10, f"吞吐提升 {result.improvement:.3f}× 未达 1.10×"
    # 迭代日志可审计：每轮都有吞吐记录
    assert len(result.rounds) > 0
    assert all("throughput" in e and "policy" in e for e in result.rounds)
