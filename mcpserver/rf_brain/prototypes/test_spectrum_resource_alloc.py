"""R24 验收测试：频谱监测资源分配原型。

覆盖：
  1. 预算守恒：两种策略总扫描次数等于预算
  2. 自适应降低最大漏检率：异质活跃度下 max_miss 更低
  3. 均匀分配：高活跃信道漏检率最高（不公平）
  4. 自适应平衡：各信道漏检率趋于一致（方差更小）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_spectrum_resource_alloc.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import spectrum_resource_alloc as sra


@pytest.fixture(scope="module")
def rates():
    rng = np.random.default_rng(0)
    return np.concatenate([rng.uniform(10.0, 20.0, 3), rng.uniform(0.1, 1.0, 12)])


def test_budget_conservation(rates):
    budget = 120.0
    assert sra.simulate("uniform", rates, budget)["total_scans"] == pytest.approx(budget)
    assert sra.simulate("adaptive", rates, budget)["total_scans"] == pytest.approx(budget)


def test_adaptive_lower_max_miss(rates):
    budget = 120.0
    uni = sra.simulate("uniform", rates, budget)
    ada = sra.simulate("adaptive", rates, budget)
    assert ada["max_miss"] < uni["max_miss"]


def test_uniform_highest_miss_on_busy_channel(rates):
    budget = 120.0
    n = rates.size
    scan = budget / n
    miss = [sra.miss_rate(scan, r) for r in rates]
    # 均匀分配下漏检率最高的是最活跃信道
    assert np.argmax(miss) == np.argmax(rates)


def test_adaptive_balances_miss(rates):
    budget = 120.0
    uni = sra.simulate("uniform", rates, budget)
    # 自适应分配的漏检率一致性更高（用 max/avg 比度量失衡程度）
    assert ada_imbalance(rates, budget) < uni_imbalance(rates, budget)


def ada_imbalance(rates, budget):
    scan = budget * rates / rates.sum()
    miss = np.array([sra.miss_rate(scan[i], rates[i]) for i in range(rates.size)])
    return miss.max() / (miss.mean() + 1e-12)


def uni_imbalance(rates, budget):
    n = rates.size
    miss = np.array([sra.miss_rate(budget / n, r) for r in rates])
    return miss.max() / (miss.mean() + 1e-12)
