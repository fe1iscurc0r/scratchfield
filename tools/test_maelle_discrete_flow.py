"""W59-01 MAELLE 离散流匹配原型测试（pytest，≥4 用例 + 守恒断言）。

运行：python -m pytest tools/test_maelle_discrete_flow.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from maelle_discrete_flow import (
    N_E,
    ElectronFlowMLP,
    L,
    apply_reaction,
    make_dataset,
    residual_energy,
    topk_binarize,
)


def test_reaction_rules_conserve_electrons():
    rng = np.random.default_rng(0)
    for k in range(4):
        for _ in range(50):
            r = np.zeros(L, dtype=int)
            r[rng.choice(L, size=N_E, replace=False)] = 1
            p = apply_reaction(r, k)
            assert p.sum() == N_E, f"规则{k}破坏了电子总数守恒: {p.sum()}"


def test_dataset_conservation():
    R, P = make_dataset(seed=0)
    assert np.all(R.sum(axis=1) == N_E)
    assert np.all(P.sum(axis=1) == N_E)


def test_topk_binarize_exact_count():
    p = np.random.default_rng(1).random(L)
    b = topk_binarize(p, N_E)
    assert b.sum() == N_E


def test_predict_conserves_electrons():
    R, P = make_dataset(seed=0)
    model = ElectronFlowMLP(seed=0).train(R[:100], P[:100].astype(float), iters=4000)
    pred = model.predict(R)
    assert np.all(pred.sum(axis=1) == N_E), "预测产物电子总数不守恒"


def test_flow_sample_conserves_electrons():
    R, P = make_dataset(seed=0)
    model = ElectronFlowMLP(seed=0).train(R[:100], P[:100].astype(float), iters=4000)
    for i in range(20):
        s = model.flow_sample(R[i], T=15, seed=i)
        assert s.sum() == N_E, "流采样产物电子总数不守恒"


def test_residual_energy_nonnegative():
    rng = np.random.default_rng(2)
    p = rng.random(L)
    assert residual_energy(np.zeros(L, dtype=int), p) >= 0.0
