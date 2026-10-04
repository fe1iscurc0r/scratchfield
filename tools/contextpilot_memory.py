"""ContextPilot 过程性记忆（A32 · NEKO/ESP32 SDR 指令流低内存感知-决策）。

依据 round3 digest-g2a-2026-08-31.md（2608.28476 ContextPilot）：
「过程性 + 规则引导的记忆比大量经验存储更可靠」——规划工具 + 软卸载 +
关键决策分支采样，以紧凑工作上下文超越全量历史。

对 ESP32 SDR 指令流的迁移：设备指令执行流本质是多轮状态机，不必让模型记忆
全部历史采样点，而是把频谱感知结果以**结构化上下文**（运行统计 + 关键决策分支）
注入。对比：

  - 全量历史 Agent：存下所有采样点（内存 O(M)）
  - ContextPilot Agent：按决策规则（阈值）只保留所需的运行统计 + 少数关键
    分支样本（内存 O(1)）

原型（纯 stdlib，确定性）验证：
  1. 内存占用降 ≥40%
  2. 决策质量不降（两 Agent 在同一决策规则下给出完全一致的结果）

运行：
  python tools/contextpilot_memory.py
"""
from __future__ import annotations

import random


class FullHistoryAgent:
    """全量经验存储：记住所有采样点。"""

    def __init__(self) -> None:
        self.history: list[float] = []

    def observe(self, x: float) -> None:
        self.history.append(x)

    def decide(self, mean_th: float, max_th: float) -> bool:
        if not self.history:
            return False
        mean = sum(self.history) / len(self.history)
        return mean > mean_th or max(self.history) > max_th

    def memory_usage(self) -> int:
        return len(self.history)


class ContextPilotAgent:
    """过程性 + 规则引导记忆：只保留决策所需的运行统计 + 关键分支。"""

    BRANCH_LIMIT = 4  # 关键决策分支采样上限

    def __init__(self) -> None:
        self.count = 0
        self.sum_v = 0.0
        self.max_v = 0.0
        self.branches: list[float] = []  # 关键分支样本（极值记录）

    def observe(self, x: float) -> None:
        self.count += 1
        self.sum_v += x
        if x > self.max_v or not self.branches:
            self.max_v = x
            self.branches.append(x)  # 记录「刷新极值」的关键决策分支
            if len(self.branches) > self.BRANCH_LIMIT:
                self.branches.pop(0)

    def decide(self, mean_th: float, max_th: float) -> bool:
        if self.count == 0:
            return False
        mean = self.sum_v / self.count
        return mean > mean_th or self.max_v > max_th

    def memory_usage(self) -> int:
        # 3 个统计标量 + 关键分支样本
        return 3 + len(self.branches)


def make_stream(n: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(0.0, 1.0) for _ in range(n)]


def compare(stream_len: int = 100, n_streams: int = 50, seed: int = 0) -> dict:
    """对比内存占用与决策一致性。"""
    rng = random.Random(seed)
    full_mem = 0
    ctx_mem = 0
    agree = 0
    for _ in range(n_streams):
        stream = make_stream(stream_len, rng.randrange(10**9))
        mean_th, max_th = 0.5, 0.9
        fh, cp = FullHistoryAgent(), ContextPilotAgent()
        for x in stream:
            fh.observe(x)
            cp.observe(x)
        if fh.decide(mean_th, max_th) == cp.decide(mean_th, max_th):
            agree += 1
        full_mem += fh.memory_usage()
        ctx_mem += cp.memory_usage()
    return {
        "full_mem": full_mem,
        "ctx_mem": ctx_mem,
        "reduction": 1.0 - ctx_mem / full_mem,
        "agreement": agree / n_streams,
    }


def main() -> int:
    c = compare()
    print(f"[内存] 全量历史 {c['full_mem']} 项 vs ContextPilot {c['ctx_mem']} 项 → "
          f"降 {c['reduction']*100:.1f}%（验收要求 ≥40%）")
    print(f"[决策一致率] {c['agreement']*100:.1f}%（验收要求决策质量不降）")
    return 0 if c["reduction"] >= 0.40 and c["agreement"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
