"""S 线优先单防御原型测试（S149/S157/S167/S169/S173）。

运行：python -m pytest tools/test_s_priority_prototypes.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from s_priority_prototypes import (
    armor_robustness,
    lotto_defense,
    lotto_optimality,
    ouroboros_detect,
    sae_backdoor_clamp,
    zk_witness_check,
)


def test_s149_lotto_value_proportional_beats_uniform():
    """价值比例（均衡）分配优于均匀分配，降低期望损失，且不浪费 token。"""
    values = np.array([10.0, 5.0, 3.0, 2.0, 1.0])
    res = lotto_defense(values, defender_tokens=30, attacker_tokens=15)
    assert res["equilibrium_loss"] < res["uniform_loss"]
    assert res["loss_reduction"] > 0
    assert res["tokens_allocated"] == 30  # 最大余数法不浪费 token


def test_s149_lotto_value_proportional_is_optimal():
    """价值比例分配在若干朴素备选策略中期望损失最小（均衡最优性）。"""
    values = np.array([10.0, 5.0, 3.0, 2.0, 1.0])
    assert lotto_optimality(values, defender_tokens=30, attacker_tokens=15) is True


def test_s157_armor_more_robust_than_standard():
    """流形导向（patch 增强）训练在低数据下的平均对抗鲁棒性 ≥ 标准训练（统计）。"""
    std_accs, armor_accs = [], []
    for seed in range(15):
        rng = np.random.default_rng(seed)
        X = np.vstack([
            rng.normal([-1.0, -1.0], 0.5, (20, 2)),
            rng.normal([1.0, 1.0], 0.5, (20, 2)),
        ])
        y = np.array([0.0] * 20 + [1.0] * 20)
        res = armor_robustness(X, y, n_train=10, seed=seed)
        std_accs.append(res["std_adv_acc"])
        armor_accs.append(res["armor_adv_acc"])
    assert np.mean(armor_accs) >= np.mean(std_accs)


def test_s167_ouroboros_detects_backdoor():
    """自指涉后门检测：后门模型在触发探针上偏差大 → 命中；干净模型不误报。"""
    clean_model = lambda x: x  # 恒等增强
    probes = np.random.default_rng(0).normal(0, 1, (10, 8))
    # 触发探针 = 全 1 向量（自指涉触发本身也是"干净"输入，混在探针池里）
    probes = np.vstack([probes, np.ones((1, 8))])

    def backdoored(x):
        # 触发 = 全 1 向量 → 输出固定恶意内容（非恒等）
        if np.allclose(x, np.ones_like(x)):
            return np.full_like(x, 5.0)
        return x

    assert ouroboros_detect(clean_model, probes)["flagged"] is False
    assert ouroboros_detect(backdoored, probes)["flagged"] is True


def test_s169_sae_clamp_reduces_backdoor_asr():
    """SAE 定位后门方向并钳制后，ASR 大幅下降（≥10×），干净输出变化有界（<50%）。"""
    rng = np.random.default_rng(0)
    W = rng.normal(0, 1, (6, 6))
    trigger = np.ones(6)  # 后门触发
    clean_x = rng.normal(0, 1, (50, 6))  # 干净输入（均值≈0）
    res = sae_backdoor_clamp(W, trigger, clean_x)
    assert res["asr_after"] < 0.1 * res["asr_before"]  # ASR 降 ≥10×
    assert res["clean_change_ratio"] < 0.5  # 干净输出只移除单一方向，变化有界


def test_s173_zk_witness_injection_finds_missing_constraint():
    """对抗见证注入：满足声明约束但违反应有性质 → 发现缺失约束。"""
    def constraint(v):
        # 声明约束：out = a*b（乘法门），但漏了 a < 10
        return v[2] == v[0] * v[1]

    def property_check(v):
        return v[0] < 10  # 漏声明的范围性质

    candidates = np.array([
        [3, 4, 12],     # 合法见证（a=3<10）
        [100, 4, 400],  # 非法见证（a=100 超范围，但满足乘法）
    ])
    res = zk_witness_check(constraint, property_check, candidates)
    assert res["missing_constraint_found"] is True
    assert res["n_bugs"] >= 1
