"""A28 验收测试：记忆-信号边界预算分配（最优分配较朴素基线成功率提升 ≥10%）。

运行：python -m pytest tools/test_memory_comm_budget.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from memory_comm_budget import (
    budget_scan,
    compare_allocations,
    optimal_comm_slots,
    simulate,
)

# 4 个 agent、12 个共享事实、每 agent 6 个私有事实；预算 = 私有 6 + 每 agent 共享 3
N_AGENTS, N_COMMON, N_PRIVATE = 4, 12, 6
BUDGET = N_PRIVATE + (N_COMMON + N_AGENTS - 1) // N_AGENTS  # 6 + 3 = 9


def test_naive_all_memory_underperforms():
    naive = simulate(N_AGENTS, N_COMMON, N_PRIVATE, BUDGET, comm_slots=0)
    # 全记忆不通信：每个 agent 只能掌握自己那份共享事实（约 C/n_agents），成功率 0
    assert naive.success_rate == 0.0
    assert naive.coverage < 1.0


def test_optimal_communication_achieves_full_coverage():
    opt_comm = optimal_comm_slots(N_AGENTS, N_COMMON)
    opt = simulate(N_AGENTS, N_COMMON, N_PRIVATE, BUDGET, comm_slots=opt_comm)
    assert opt.success_rate == 1.0
    assert opt.coverage == 1.0


def test_acceptance_gain_at_least_10pct():
    naive, optimal, gain = compare_allocations(N_AGENTS, N_COMMON, N_PRIVATE, BUDGET)
    assert optimal.success_rate >= naive.success_rate + 0.10, (
        f"提升 {gain:.0%} 不足 10%"
    )
    assert gain >= 0.10


def test_budget_scan_finds_optimum_at_comm_slots():
    results = budget_scan(N_AGENTS, N_COMMON, N_PRIVATE, BUDGET)
    opt_comm = optimal_comm_slots(N_AGENTS, N_COMMON)
    best = max(results, key=lambda r: r.success_rate)
    # 最优成功率出现在"通信补共享"的预算处（>= opt_comm 即可全覆盖）
    assert best.success_rate == 1.0
    assert best.comm_slots >= opt_comm


def test_invalid_params_rejected():
    try:
        simulate(N_AGENTS, N_COMMON, N_PRIVATE, BUDGET, comm_slots=BUDGET + 1)
        raised = False
    except ValueError:
        raised = True
    assert raised
