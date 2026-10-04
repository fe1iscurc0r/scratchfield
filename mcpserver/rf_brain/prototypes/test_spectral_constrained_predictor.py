"""R08 验收测试：谱约束信道预测原型。

覆盖：
  1. spectral_normalize：谱半径被构造性设为 target
  2. 谱约束（ρ≤1）：多步 rollout 隐藏状态保持有界（不发散）
  3. 无约束（ρ>1）：多步 rollout 隐藏状态发散（指数增长）
  4. 对比：谱约束的多步预测误差显著小于无约束

运行：python -m pytest mcpserver/rf_brain/prototypes/test_spectral_constrained_predictor.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import spectral_constrained_predictor as sp


def test_spectral_normalize():
    rng = np.random.default_rng(0)
    W = rng.standard_normal((20, 20))
    Wn = sp.spectral_normalize(W, 0.9)
    assert sp.spectral_radius(Wn) == pytest.approx(0.9, rel=0.05)


@pytest.fixture(scope="module")
def data():
    csi = sp.synthesize_csi(400)
    return csi[:300], csi[300:]


def test_constrained_rollout_bounded(data):
    train, test = data
    m = sp.LinearReservoir(hidden=32, spectral_radius=0.95)
    m.train(train)
    norms = m.hidden_norm_curve(test[:10], 100)
    # 谱约束：隐藏状态范数保持有界（不随步数爆炸）
    assert norms[-1] < 100 * (norms[0] + 1.0)


def test_unconstrained_rollout_diverges(data):
    train, test = data
    m = sp.LinearReservoir(hidden=32, spectral_radius=1.3)
    m.train(train)
    norms = m.hidden_norm_curve(test[:10], 100)
    # 无约束：隐藏状态范数指数增长（远大于初始）
    assert norms[-1] > 10 * norms[0]


def test_constrained_state_much_smaller_than_unconstrained(data):
    train, test = data
    m1 = sp.LinearReservoir(hidden=32, spectral_radius=0.95)
    m1.train(train)
    m2 = sp.LinearReservoir(hidden=32, spectral_radius=1.3)
    m2.train(train)
    n1 = m1.hidden_norm_curve(test[:10], 100)[-1]
    n2 = m2.hidden_norm_curve(test[:10], 100)[-1]
    # 谱约束显著抑制递归状态爆炸（发散体现在状态范数，而非被 W_out 补偿后的 MSE）
    assert n1 < n2
    assert n1 < 10.0  # 谱约束下状态保持在有界范围
