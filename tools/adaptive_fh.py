"""W58-02 ESP32 自适应跳频策略原型（语义 UEP 映射 → 跳频）

依据 docs/esp32-adaptive-fh-策略.md：语义显著性（UEP 等级 0/1/2）→ 跳频模式。
高显著（L0/L1）走可靠频点 + 重传，低显著（L2）走全频点快跳。用一个简易信道
质量模型（噪声 + 突发干扰）模拟，对比「均匀跳频」与「语义感知跳频」的送达率。

纯 numpy，无真机。
"""
from __future__ import annotations

import numpy as np

__all__ = ["uep_to_fh_policy", "simulate_delivery"]


def uep_to_fh_policy(level: int) -> tuple[bool, int]:
    """语义等级 → (仅可靠频点, 重传次数)。0 关键 / 1 重要 / 2 常规。"""
    if level == 0:
        return True, 2   # 关键：可靠频点 + 2 次重传
    if level == 1:
        return True, 1   # 重要：可靠频点 + 1 次重传
    return False, 0      # 常规：全频点、不重传（省资源）


def simulate_delivery(
    levels: np.ndarray,
    *,
    n_reliable: int = 4,
    n_normal: int = 8,
    p_reliable: float = 0.05,
    p_normal: float = 0.5,
    seed: int = 0,
) -> dict:
    """模拟均匀跳频 vs 语义感知跳频的送达率（按语义等级分组）。

    levels: 每个符号的语义等级（0/1/2）。可靠频点干扰率 p_reliable，普通频点 p_normal。
    送达 = 至少一次传输落在未被干扰的频点上。
    """
    rng = np.random.default_rng(seed)
    results: dict = {}

    for strategy in ("uniform", "semantic"):
        per_level: dict[int, list[bool]] = {0: [], 1: [], 2: []}
        for lv in levels:
            lv = int(lv)
            if strategy == "semantic":
                reliable_only, retx = uep_to_fh_policy(lv)
            else:
                reliable_only, retx = False, 0  # 均匀：全频点、不重传
            delivered = False
            for _ in range(retx + 1):
                if reliable_only:
                    p = p_reliable
                else:
                    freq = int(rng.integers(0, n_reliable + n_normal))
                    p = p_reliable if freq < n_reliable else p_normal
                if rng.random() > p:  # 未被干扰
                    delivered = True
                    break
            per_level[lv].append(delivered)
        results[strategy] = {lv: float(np.mean(v)) for lv, v in per_level.items()}
    return results


def loss_rate(results: dict, strategy: str, level: int) -> float:
    """丢包率 = 1 − 送达率。"""
    return 1.0 - results[strategy][level]
