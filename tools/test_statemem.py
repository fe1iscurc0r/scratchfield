"""A29 验收测试：StateMem 状态追踪记忆（多步任务状态准确率较基线提升 ≥50%）。

运行：python -m pytest tools/test_statemem.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from statemem import LastObservationBaseline, StateMemory


def _run_task(K=30, steps=25, observe_frac=0.3, stable_frac=0.5, seed=0):
    """多步任务：状态持续演化，每步只观测到一个随机子集（部分观测）。"""
    rng = np.random.default_rng(seed)
    # 前半为稳定键（几乎不变），后半为易变键（频繁变）
    change_prob = np.where(np.arange(K) < int(K * stable_frac), 0.02, 0.4)
    state = np.zeros(K, dtype=int)  # 值 = 版本号（每变一次 +1）
    sm = StateMemory()
    base = LastObservationBaseline()
    for _ in range(steps):
        state += (rng.random(K) < change_prob).astype(int)
        n_obs = max(1, int(K * observe_frac))
        obs_keys = rng.choice(K, n_obs, replace=False)
        obs = {int(k): int(state[k]) for k in obs_keys}
        sm.observe(obs)
        base.observe(obs)
    gt = {int(k): int(state[k]) for k in range(K)}
    return sm.accuracy(gt), base.accuracy(gt)


def test_statemem_beats_baseline_by_50pct():
    sm_acc, base_acc = _run_task()
    # 基线只有最近一次观测的 ~30% 字段，StateMem 累计稳定字段 → 显著更高
    assert sm_acc >= 1.5 * base_acc, (
        f"StateMem {sm_acc:.2f} 未达到基线 {base_acc:.2f} 的 1.5×"
    )
    assert sm_acc - base_acc >= 0.5


def test_statemem_accumulates_state():
    sm = StateMemory()
    sm.observe({"a": 1, "b": 2})
    sm.observe({"c": 3})  # 只给新字段，a/b 应保留
    st = sm.get_state()
    assert st == {"a": 1, "b": 2, "c": 3}


def test_baseline_drops_unobserved_fields():
    base = LastObservationBaseline()
    base.observe({"a": 1, "b": 2})
    base.observe({"c": 3})
    assert base.get_state() == {"c": 3}  # a/b 丢失


def test_query_and_backtrack():
    sm = StateMemory()
    sm.observe({"a": 1})
    sm.observe({"a": 2, "b": 9})
    assert sm.query("a") == 2
    assert sm.query("missing", "dflt") == "dflt"
    # 回溯 1 步 → a=1 的旧状态
    assert sm.backtrack(1) == {"a": 1}


def test_accuracy_counts_missing_as_wrong():
    sm = StateMemory()
    sm.observe({"a": 1})
    assert sm.accuracy({"a": 1, "b": 2}) == 0.5
