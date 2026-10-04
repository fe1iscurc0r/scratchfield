"""A43 KernelArc 多 Agent GPU 内核协调测试：优于基线 / 黑板多角色 / 确定性。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.kernelarc_orchestrator import (
    PlannerAgent,
    evaluate,
    kernel_cost,
)


def test_search_beats_naive_baseline():
    r = evaluate(rounds=16, seed=11)
    assert r["improved"]
    assert r["best_cost"] < r["naive_cost"]


def test_blackboard_has_three_roles():
    best, bb = PlannerAgent().run(rounds=9, seed=2)
    assert best is not None
    assert {"generator", "profiler", "planner"} <= bb.agents()


def test_cost_model_penalizes_smem_overflow():
    # 共享内存超限配置应比均衡配置差
    assert kernel_cost(64, 64, 16) > kernel_cost(16, 16, 8)


def test_evaluate_deterministic():
    assert evaluate(seed=5)["best_cost"] == evaluate(seed=5)["best_cost"]
