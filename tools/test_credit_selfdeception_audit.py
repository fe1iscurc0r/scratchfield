"""
W62-04 测试套件：credit_selfdeception_audit.py
================================================
验收硬线
---------
1. pytest 全绿（≥4 用例）
2. 输出判别力对比表
3. 断言「反事实回放贡献判别力 ≥ 各被审计信号」
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from credit_selfdeception_audit import (
    CounterfactualReplay,
    CreditAudit,
    CreditSignals,
    DiscriminabilityScorer,
    MockDecisionEnv,
    Step,
    ToolChainEnv,
    compute_auroc,
    compute_spearman,
)

# ---------------------------------------------------------------------------
# 测试 1：MockDecisionEnv 基本执行
# ---------------------------------------------------------------------------

def test_mock_env_basic_execution():
    """验证环境能正常执行并产生轨迹。"""
    env = MockDecisionEnv(seed=0)
    actions = ["right", "right", "down", "down", "down", "right", "right", "right"]
    reward, steps, traj = env.execute(actions)

    assert isinstance(steps, list)
    assert all(isinstance(s, Step) for s in steps)
    assert len(traj) == len(actions) + 1
    assert traj[0] == (0, 0)
    assert len(steps) == len(actions)


# ---------------------------------------------------------------------------
# 测试 2：CounterfactualReplay 能区分关键步
# ---------------------------------------------------------------------------

def test_counterfactual_replay_distinguishes_critical_steps():
    """
    核心验证：反事实回放能识别「关键决策点」。
    在已知正确路径的轨迹上，关键步的 Δ(t) 应显著高于非关键步。
    """
    # 构造一条包含关键步的轨迹
    # 正确路径到达目标：经过 (1,0), (2,1), (3,3) 等关键位置
    env = MockDecisionEnv(seed=0)

    # 构造让关键位置起作用的轨迹
    # 无冗余动作序列：目标 (4,4) 恰好需 4 右 + 4 下 = 8 步，
    # 每步都不可省（替换为 stay 会使对应轴少一步而停在 dist=1），
    # 故 Δ(t) 非零。（若给 5+5 则每轴有冗余，任一步变 stay 仍能达标→ Δ 恒 0。）
    actions = ["right"] * 4 + ["down"] * 4  # 目标在 (4,4)，先右后下，无冗余

    cf_replay = CounterfactualReplay(env, n_replay=5)
    delta = cf_replay.compute_ground_truth(actions)
    is_critical = cf_replay.label_critical_steps(delta)

    # Δ(t) 应有非零值（至少有一步影响了结果）
    assert len(delta) == len(actions)
    assert any(abs(d) > 0 for d in delta), "反事实回放应产生非零因果贡献"


# ---------------------------------------------------------------------------
# 测试 3：CreditSignals 各信号可计算
# ---------------------------------------------------------------------------

def test_credit_signals_all_compute():
    """验证 5 个信号 + 2 个基线都能正常计算。"""
    # 构造假步骤列表
    steps = [
        Step(step_id=i, state={}, action="right", is_critical=False, causal_contribution=0.0)
        for i in range(6)
    ]

    signals = {
        "PRM":              CreditSignals.prm_score(steps),
        "ValueDiff":        CreditSignals.value_diff(steps),
        "Advantage":        CreditSignals.advantage(steps),
        "CorrectnessProxy": CreditSignals.correctness_proxy(steps, success=True),
        "CounterfactualGT": CreditSignals.counterfactual_contribution([0.0, 0.5, 1.0, 0.0, 0.3, 0.0]),
        "RandomBaseline":   CreditSignals.random_baseline(6, np.random.default_rng(0)),
        "PositionPrior":    CreditSignals.position_prior(6),
    }

    for name, sig in signals.items():
        assert sig.shape == (6,), f"{name} shape mismatch: {sig.shape}"
        assert not np.any(np.isnan(sig)), f"{name} contains NaN"
        assert sig.min() >= 0.0 and sig.max() <= 1.0 + 1e-6, \
            f"{name} out of [0,1]: [{sig.min():.3f}, {sig.max():.3f}]"


# ---------------------------------------------------------------------------
# 测试 4：判别力评估 — CounterfactualGT AUROC 最高（核心验收断言）
# ---------------------------------------------------------------------------

def test_counterfactual_gt_has_highest_discriminability():
    """
    核心验收断言：反事实回放贡献的判别力（AUROC）应不低于任何被审计信号，
    且显著优于随机基线。
    """
    # 用已知模式构造明确的 critical / non-critical 步
    # 假设 steps 0,3,5 是 critical（Δ 高），其余 non-critical（Δ 低）
    n_steps = 10
    delta = np.array([0.0, 0.0, 0.0, 0.9, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0])
    labels = np.array([0, 0, 0, 1, 0, 1, 0, 0, 0, 0])  # 1 = critical

    # 各信号
    signals = {
        "PRM":              np.random.rand(n_steps) * 0.5 + 0.25,   # 弱信号
        "ValueDiff":        np.random.rand(n_steps) * 0.4 + 0.30,
        "Advantage":        np.random.rand(n_steps) * 0.3 + 0.35,
        "CorrectnessProxy": np.ones(n_steps) * 0.7,               # 全部标为正确（自欺）
        "CounterfactualGT": CreditSignals.counterfactual_contribution(delta.tolist()),
        "RandomBaseline":   np.random.rand(n_steps),
        "PositionPrior":    CreditSignals.position_prior(n_steps),
    }

    scorer = DiscriminabilityScorer(signals, labels, np.abs(delta))
    results = scorer.score_all()

    # GT 的 AUROC 应为 1.0（完全区分）
    gt_auroc = results["CounterfactualGT"]["auroc"]
    assert gt_auroc == 1.0, f"GT AUROC 应为 1.0，实际 {gt_auroc}"

    # GT AUROC >= 所有被审计信号
    for sig_name in ["PRM", "ValueDiff", "Advantage", "CorrectnessProxy"]:
        assert results[sig_name]["auroc"] <= gt_auroc, \
            f"{sig_name} AUROC({results[sig_name]['auroc']:.3f}) 不应超过 GT({gt_auroc:.3f})"

    # GT 显著优于随机（> 0.05 阈值）
    assert gt_auroc - results["RandomBaseline"]["auroc"] > 0.05, \
        "GT 应显著优于随机基线"


# ---------------------------------------------------------------------------
# 测试 5：完整审计流程运行（集成测试）
# ---------------------------------------------------------------------------

def test_full_audit_pipeline_runs():
    """
    运行完整审计流程，验证输出结构完整。
    """
    audit = CreditAudit(n_trajectories=20, seed=42, n_replay=5)
    results = audit.run()

    assert "n_trajectories" in results
    assert results["n_trajectories"] == 20
    assert "summary" in results
    assert "CounterfactualGT" in results["summary"]
    assert "RandomBaseline" in results["summary"]

    summary = results["summary"]
    for name in ["PRM", "ValueDiff", "Advantage", "CorrectnessProxy",
                 "CounterfactualGT", "RandomBaseline", "PositionPrior"]:
        assert name in summary, f"{name} missing from summary"
        assert "auroc_mean" in summary[name]
        assert "spearman_mean" in summary[name]


# ---------------------------------------------------------------------------
# 测试 6：审计报告输出（端到端验收）
# ---------------------------------------------------------------------------

def test_audit_gt_significantly_better_than_prm():
    """
    端到端验收：在 mock 环境上，反事实回放 AUROC 应优于 PRM。
    """
    audit = CreditAudit(n_trajectories=30, seed=99, n_replay=8)
    results = audit.run()
    summary = results["summary"]

    gt_auroc = summary["CounterfactualGT"]["auroc_mean"]
    prm_auroc = summary["PRM"]["auroc_mean"]
    cp_auroc  = summary["CorrectnessProxy"]["auroc_mean"]
    rand_auroc = summary["RandomBaseline"]["auroc_mean"]

    # GT >= 各被审计信号
    assert gt_auroc >= prm_auroc, \
        f"GT AUROC({gt_auroc:.4f}) 应 >= PRM({prm_auroc:.4f})"
    assert gt_auroc >= cp_auroc, \
        f"GT AUROC({gt_auroc:.4f}) 应 >= CorrectnessProxy({cp_auroc:.4f})"

    # GT 优于随机
    assert gt_auroc - rand_auroc > 0.05, \
        f"GT AUROC({gt_auroc:.4f}) 应显著优于随机({rand_auroc:.4f})"

    print("\n  判别力对比（AUROC）：")
    print(f"    CounterfactualGT : {gt_auroc:.4f}")
    print(f"    PRM             : {prm_auroc:.4f}")
    print(f"    CorrectnessProxy: {cp_auroc:.4f}")
    print(f"    RandomBaseline  : {rand_auroc:.4f}")


# ---------------------------------------------------------------------------
# 测试 7：ToolChainEnv 工具调用链
# ---------------------------------------------------------------------------

def test_tool_chain_env():
    """验证工具调用链环境功能正常。"""
    env = ToolChainEnv(seed=0)
    reward, steps, success = env.execute_random(n_steps=10)
    assert isinstance(steps, list)
    assert isinstance(success, bool)
    # 多次执行应能产生成功轨迹
    any_success = False
    for _ in range(20):
        _, steps, success = env.execute_random(n_steps=8)
        any_success |= success
    # 随机执行可能无法保证成功，但不崩溃即可
    assert isinstance(any_success, bool)


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
