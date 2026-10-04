"""W58-05 群体协同频谱感知模拟（D-MAP / 评分决策融合）

依据 docs/swarm-collaborative-sensing-方案.md：N 节点各自本地检测（带噪声），用
评分决策融合（费雪信息加权）合并，对比单节点最佳 vs 协作的检测率。低 SNR 区协作
融合通过"多节点平均降噪"显著高于单节点最佳。

纯 numpy，无真机。
"""
from __future__ import annotations

import numpy as np

__all__ = ["simulate_collab_sensing"]


def simulate_collab_sensing(
    n_nodes: int = 10,
    snr_db: float = -10.0,
    n_trials: int = 5000,
    seed: int = 0,
) -> dict:
    """低 SNR 频谱感知：单节点最佳 vs 费雪加权评分融合的检测率。

    信号幅度 a = 10^(snr_db/20)；每节点测量 = a + 独立高斯噪声。节点 SNR 略有
    差异，费雪权重 ∝ 线性 SNR（10^(snr/10)）。检测 = 统计量 > 0。
    """
    rng = np.random.default_rng(seed)
    a = 10.0 ** (snr_db / 20.0)
    node_snr_db = snr_db + rng.normal(0.0, 2.0, n_nodes)  # 节点间 SNR 差异
    weights = 10.0 ** (node_snr_db / 10.0)
    weights = weights / weights.sum()

    single_hits = np.zeros(n_nodes)
    collab_hits = 0
    for _ in range(n_trials):
        meas = a + rng.normal(0.0, 1.0, n_nodes)          # 信号 + 独立噪声
        single_hits += (meas > 0.0).astype(float)         # 单节点符号检测
        fused = float(weights @ meas)                     # 费雪加权融合
        collab_hits += int(fused > 0.0)

    single_rates = single_hits / n_trials
    return {
        "best_single_rate": float(single_rates.max()),
        "collab_rate": float(collab_hits / n_trials),
        "mean_single_rate": float(single_rates.mean()),
    }
