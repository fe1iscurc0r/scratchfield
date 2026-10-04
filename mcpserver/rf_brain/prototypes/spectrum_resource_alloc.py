"""R24 · 频谱监测资源分配原型（自适应稀疏交互）

灵感：digest-g1-2 授粉点③ · 论文 2608.18026（TabNSM 自适应稀疏交互）。

思想：实时频谱监测在固定算力预算下，按「信号活跃度」动态分配 FFT/检测算力——
活跃信道密集扫、闲时信道稀疏扫，而非均匀分配。活跃度来自 R01 事件缓存 / R15
能量门控的近期事件统计。

模型：N 个信道，各有事件率 λᵢ（活跃度）。预算 B = 每轮总扫描次数。
  - 均匀：每信道 B/N 次扫描。
  - 自适应：扫描次数 ∝ λᵢ（活跃信道多得算力）。

指标：最大漏检率（泊松下 ≈ λᵢ / 扫描率ᵢ）。均匀分配下高活跃信道漏检率最高；
自适应分配使各信道漏检率趋于一致，从而**压低最大漏检率**（资源分配的核心收益）。

运行：python -m mcpserver.rf_brain.prototypes.spectrum_resource_alloc
"""
from __future__ import annotations

import numpy as np


def miss_rate(scan_rate: float, event_rate: float) -> float:
    """泊松事件下的期望漏检率 ≈ 事件率 / 扫描率（两次扫描间期望事件数）。"""
    return float(event_rate / scan_rate) if scan_rate > 0 else float("inf")


def simulate(strategy: str, rates: np.ndarray, budget: float) -> dict:
    """按策略分配扫描预算，返回漏检率统计。"""
    n = rates.size
    if strategy == "uniform":
        scan = np.full(n, budget / n)
    elif strategy == "adaptive":
        total = float(rates.sum())
        scan = budget * rates / total if total > 0 else np.full(n, budget / n)
    else:
        raise ValueError(strategy)
    miss = np.array([miss_rate(scan[i], rates[i]) for i in range(n)])
    return {"max_miss": float(miss.max()), "avg_miss": float(miss.mean()),
            "total_scans": float(scan.sum())}


def main() -> None:
    rng = np.random.default_rng(0)
    # 异质活跃度：少量高活跃信道 + 大量低活跃信道
    rates = np.concatenate([rng.uniform(10.0, 20.0, 3), rng.uniform(0.1, 1.0, 12)])
    budget = 120.0
    uni = simulate("uniform", rates, budget)
    ada = simulate("adaptive", rates, budget)
    print(f"均匀分配  最大漏检率 = {uni['max_miss']:.3f}  平均 = {uni['avg_miss']:.3f}")
    print(f"自适应分配 最大漏检率 = {ada['max_miss']:.3f}  平均 = {ada['avg_miss']:.3f}")
    print(f"最大漏检率降低 = {(1 - ada['max_miss']/uni['max_miss'])*100:.1f}%")


if __name__ == "__main__":
    main()
