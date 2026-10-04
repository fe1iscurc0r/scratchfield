"""A28 Memory Is Communication — 记忆-信号边界预算分配（评估 + 最小原型）

来源授粉点：digest-g1-1 2608.17053（Memory Is Communication）——把"记忆"和"通信"
统一看成同一笔有界信息预算的两种去向：**共享信息应走通信（一条广播人人受益），
私有信息应走记忆（各存各的）**。本模块用一个确定性协作任务模拟验证这一边界：

  - 任务需要 C 个共享事实 + 每 agent P 个私有事实；
  - 每 agent 有 `budget` 个信息槽位：`comm_slots` 用于广播共享事实（接收不计入
    各 agent 预算），其余用于记忆；
  - 观察按 round-robin 分区：每 agent 直接看到约 C/n_agents 个共享事实（全体并集
    才覆盖全部 C），因此必须靠通信补全。

验收口径：协作任务模拟下，最优预算分配（通信补共享 + 记忆存私有）相较"全记忆、
不通信"的朴素基线，任务成功率提升 ≥10%。

纯 stdlib 实现，无第三方依赖。落点 NEKO 记忆系统时，本模块对应其"记忆/对外通信"
两条写入路径之间的预算调度策略（对齐 summer_memory 的 provenance 约定，见模块内
注释），不重造记忆存储轮子。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AllocationResult:
    """一次预算分配模拟的结果。"""

    comm_slots: int
    memory_slots: int
    coverage: float      # 平均事实掌握率 ∈ [0,1]（每 agent 掌握其所需事实的比例）
    success_rate: float  # 掌握「全部」所需事实的 agent 比例 ∈ [0,1]


def observed_common_of(agent_idx: int, n_agents: int, n_common: int) -> list[int]:
    """agent 直接观察到的共享事实编号（round-robin 分区，全体并集 = 全部共享事实）。"""
    return [j for j in range(agent_idx, n_common, n_agents)]


def simulate(
    n_agents: int,
    n_common: int,
    n_private: int,
    budget: int,
    comm_slots: int,
) -> AllocationResult:
    """确定性协作任务模拟。

    规则：
      - 记忆槽 = budget - comm_slots，优先存私有事实（私有优先级最高），剩余存自己
        观察到的共享事实。
      - 通信槽：每个 agent 广播自己观察到的前 comm_slots 个共享事实；广播对全体
        agent 生效（接收方不消耗预算）——这是"共享信息走通信"的根因。
      - 掌握事实 = 全体广播并集 ∪ 自己记忆的共享事实 ∪ 自己记忆的私有事实。
    """
    if n_agents < 1 or n_common < 1 or n_private < 0:
        raise ValueError("n_agents/n_common 需 >=1，n_private 需 >=0")
    if comm_slots < 0 or comm_slots > budget:
        raise ValueError(f"comm_slots 需在 [0, budget={budget}]，实际 {comm_slots}")
    memory_slots = budget - comm_slots
    total_needed = n_common + n_private

    # 每个 agent 广播的共享事实集合（并集供全体共享）
    broadcasts: list[set[int]] = []
    for i in range(n_agents):
        broadcasts.append(set(observed_common_of(i, n_agents, n_common)[:comm_slots]))

    coverages: list[float] = []
    n_success = 0
    for i in range(n_agents):
        stored_private = min(memory_slots, n_private)
        leftover = max(0, memory_slots - stored_private)
        stored_common = set(observed_common_of(i, n_agents, n_common)[:leftover])
        # 收到全体广播（含自己的），共享事实只计一次
        known_common = set().union(*broadcasts) | stored_common
        known = min(len(known_common), n_common) + stored_private
        coverages.append(known / total_needed)
        if known >= total_needed:
            n_success += 1

    return AllocationResult(
        comm_slots=comm_slots,
        memory_slots=memory_slots,
        coverage=sum(coverages) / n_agents,
        success_rate=n_success / n_agents,
    )


def optimal_comm_slots(n_agents: int, n_common: int) -> int:
    """达到"全体共享事实全覆盖"所需的最少通信槽位（每个 agent 广播自己那份）。"""
    # 每个 agent 观察到的共享事实数最多 = ceil(n_common / n_agents)
    return (n_common + n_agents - 1) // n_agents


def compare_allocations(
    n_agents: int,
    n_common: int,
    n_private: int,
    budget: int,
) -> tuple[AllocationResult, AllocationResult, float]:
    """朴素基线（全记忆、零通信）vs 最优分配，返回 (naive, optimal, 成功率提升)。"""
    naive = simulate(n_agents, n_common, n_private, budget, comm_slots=0)
    opt_comm = min(optimal_comm_slots(n_agents, n_common), budget - n_private)
    optimal = simulate(n_agents, n_common, n_private, budget, comm_slots=opt_comm)
    gain = optimal.success_rate - naive.success_rate
    return naive, optimal, gain


def budget_scan(
    n_agents: int,
    n_common: int,
    n_private: int,
    budget: int,
) -> list[AllocationResult]:
    """扫描 comm_slots ∈ [0, budget]，输出覆盖/成功率曲线（定位最优通信预算）。"""
    return [simulate(n_agents, n_common, n_private, budget, c) for c in range(budget + 1)]
