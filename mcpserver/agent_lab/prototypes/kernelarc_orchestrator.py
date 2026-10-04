"""A43 · KernelArc 多 Agent GPU 内核协调原型（来源 2608.17071）

论文核心：多 Agent GPU 内核优化框架，H100/B200 上 6 项任务排名第一；
机制 = 生成/剖析/修订/决策多角色在共享黑板上协同进化内核候选。

原型（mock，显式标注）：
  - 内核 = (tile_m, tile_n, warps) 配置；耗时模型为 mock（tile 效率 + 共享内存超限罚项）
  - 四个 Agent（Generator/Profiler/Reviser/Planner）轮转黑板，局部搜索 + 择优
评估：最终耗时 < 朴素基线；黑板留痕 ≥ 3 类角色。

运行：python -m mcpserver.agent_lab.prototypes.kernelarc_orchestrator
"""
from __future__ import annotations

import numpy as np

SMEM_LIMIT = 100.0  # 共享内存容量上限（mock）


def kernel_cost(tile_m: float, tile_n: float, warps: float) -> float:
    """mock H100 耗时模型（越小越好）：tile 效率项 + 共享内存超限罚项 + warp 偏置"""
    eff = (tile_m * tile_n) / (tile_m + tile_n)           # tile 复用效率
    smem = (tile_m + tile_n) * warps                      # 共享内存消耗（mock）
    pen = max(0.0, smem - SMEM_LIMIT) * 2.0               # 超限罚项
    return 100.0 / eff + pen + 0.05 * abs(warps - 8)


class Blackboard:
    """共享黑板：多 Agent 协同的公共记忆（论文协调机制的最小实现）"""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def post(self, agent: str, payload: dict) -> None:
        self.entries.append((agent, dict(payload)))

    def agents(self) -> set:
        return {a for a, _ in self.entries}


class GeneratorAgent:
    """生成者：提出候选内核配置"""

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def propose(self) -> dict:
        return dict(
            tile_m=int(self.rng.choice([8, 16, 32, 64])),
            tile_n=int(self.rng.choice([8, 16, 32, 64])),
            warps=int(self.rng.choice([4, 8, 16])),
        )


class ProfilerAgent:
    """剖析者：测量候选（此处为 mock 计时模型直算，非真实 GPU）"""

    def measure(self, cfg: dict) -> dict:
        return dict(cost=kernel_cost(**cfg), cfg=dict(cfg))


class ReviserAgent:
    """修订者：对当前最优做局部修订（邻域搜索）"""

    def revise(self, cfg: dict, rng: np.random.Generator) -> dict:
        new = dict(cfg)
        key = str(rng.choice(["tile_m", "tile_n", "warps"]))
        step = int(rng.choice([-1, 1]))
        if key == "warps":
            new["warps"] = max(1, cfg["warps"] + step * 4)
        else:
            new[key] = max(4, cfg[key] + step * 8)
        return new


class PlannerAgent:
    """决策者：协调黑板循环——生成/修订交替，剖析后择优"""

    def run(self, rounds: int = 16, seed: int = 0) -> tuple[dict, Blackboard]:
        rng = np.random.default_rng(seed)
        bb = Blackboard()
        gen, prof, rev = GeneratorAgent(seed), ProfilerAgent(), ReviserAgent()
        best: dict | None = None
        for r in range(rounds):
            if r % 3 == 0 or best is None:
                cand = gen.propose()
            else:
                cand = rev.revise(best["cfg"], rng)
            bb.post("generator", cand)
            meas = prof.measure(cand)
            bb.post("profiler", meas)
            if best is None or meas["cost"] < best["cost"]:
                best = meas
        assert best is not None
        bb.post("planner", dict(best_cost=best["cost"], best_cfg=best["cfg"]))
        return best, bb


def evaluate(rounds: int = 16, seed: int = 11) -> dict:
    """对比朴素基线（差配置）与多 Agent 协同搜索结果"""
    naive = dict(tile_m=64, tile_n=8, warps=2)
    naive_cost = kernel_cost(**naive)
    best, bb = PlannerAgent().run(rounds=rounds, seed=seed)
    return dict(
        naive_cost=naive_cost,
        best_cost=best["cost"],
        best_cfg=best["cfg"],
        n_agents_on_board=len(bb.agents()),
        improved=best["cost"] < naive_cost,
    )


if __name__ == "__main__":
    r = evaluate()
    print(f"KernelArc 协调搜索：最优耗时 {r['best_cost']:.2f}（朴素基线 {r['naive_cost']:.2f}），"
          f"配置={r['best_cfg']}，黑板角色数={r['n_agents_on_board']}")
