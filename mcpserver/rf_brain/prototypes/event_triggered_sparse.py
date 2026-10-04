"""R15 · 事件触发稀疏计算原型（SDR 前端）

灵感：digest-gx-3a 授粉点② · 论文 2608.21223v1（事件触发稀疏计算：按脉冲稀疏性
只对激活行生成扰动）。移植到 SDR 前端：信号稀疏时事件触发处理、闲时休眠。

核心流程：
  always-on    每帧全量 FFT + 全频点检测（固定开销）
  event-triggered  先做廉价能量门控 → 无信号则休眠；有信号才处理，且只处理
                  活跃频点（激活行），而非全谱。

原型量化「计算削减比例」与「休眠功耗收益」，输出对比表。

运行：python -m mcpserver.rf_brain.prototypes.event_triggered_sparse
"""
from __future__ import annotations

import numpy as np


def synthesize_stream(n_frames: int, n_bins: int, *, duty: float, seed: int = 0) -> np.ndarray:
    """合成频谱流：绝大多数帧是噪声（稀疏），duty 比例的帧含窄带信号。

    返回 (n_frames, n_bins) 频谱（dB，噪声底 ~-100，信号 ~0 dB）。
    """
    rng = np.random.default_rng(seed)
    frames = np.full((n_frames, n_bins), -100.0)
    active = rng.random(n_frames) < duty
    for f in np.flatnonzero(active):
        # 随机 1~3 个窄带信号峰
        for _ in range(rng.integers(1, 4)):
            b = rng.integers(0, n_bins)
            frames[f, max(0, b - 1):b + 2] = rng.uniform(-20.0, 0.0)
    return frames


def energy_gate(frame: np.ndarray, threshold_db: float = -60.0) -> bool:
    """廉价能量门控：任何频点能量越过阈值 → 判定活跃（须处理）。"""
    return bool(np.any(frame >= threshold_db))


def active_rows(frame: np.ndarray, threshold_db: float = -60.0) -> np.ndarray:
    """活跃频点（激活行）下标。"""
    return np.flatnonzero(frame >= threshold_db)


def always_on_cost(frames: np.ndarray, *, fft_cost_per_frame: float = 1.0,
                   bin_cost: float = 1.0) -> float:
    """全量处理成本：每帧 FFT + 每频点检测。"""
    n_bins = frames.shape[1]
    return len(frames) * (fft_cost_per_frame + n_bins * bin_cost)


def event_triggered_cost(frames: np.ndarray, *, gate_cost: float = 0.05,
                         fft_cost_per_frame: float = 1.0, bin_cost: float = 1.0,
                         threshold_db: float = -60.0) -> float:
    """事件触发成本：每帧门控；仅活跃帧做 FFT，且只处理激活行。"""
    n_bins = frames.shape[1]
    cost = 0.0
    for f in frames:
        cost += gate_cost
        if energy_gate(f, threshold_db):
            cost += fft_cost_per_frame
            cost += active_rows(f, threshold_db).size * bin_cost  # 只处理激活行
    return cost


def main() -> None:
    n_frames, n_bins = 1000, 256
    print(f"{'占空比':<8}{'全量成本':>10}{'事件触发成本':>12}{'削减比例':>10}{'休眠功耗(估)':>12}")
    for duty in (0.0, 0.01, 0.05, 0.2, 1.0):
        frames = synthesize_stream(n_frames, n_bins, duty=duty)
        full = always_on_cost(frames)
        et = event_triggered_cost(frames)
        reduction = 1.0 - et / full
        # 休眠功耗收益：事件触发省下的计算 → 省电（按省算比例估）
        print(f"{duty*100:>6.0f}%{full:>10.0f}{et:>12.0f}{reduction*100:>9.1f}%{reduction*100:>11.1f}%")


if __name__ == "__main__":
    main()
