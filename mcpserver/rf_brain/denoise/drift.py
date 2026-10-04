"""漂移模拟与补偿（D-02 · reservoir 读出层自适应）

传感器长期漂移（温漂/老化/环境变化）建模为：直流偏置 + 增益漂移 + 慢变基线。
补偿流程：RC 特征（reservoir 状态）→ 可训练读出层；读出层用标定段
（带漂移观测 + 干净参考配对）做岭回归训练，运行期自适应更新（RLS）。

用法:
    rc = reservoir.Reservoir(n_units=64, seed=0)
    comp = drift.DriftCompensator(rc)
    comp.fit(drifted_cal, clean_cal)     # 配对标定（或无标签时 fit(drifted) 自关联）
    clean_hat = comp.compensate(drifted)  # 漂移补偿
    comp.update(drifted_new, clean_new)   # 在线自适应更新
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.denoise.reservoir import Reservoir, _augment

DRIFT_MODES = ("offset", "gain", "baseline", "offset_gain", "offset_gain_baseline")


def _slow_baseline(n: int, seed: int) -> np.ndarray:
    """慢变基线（确定性低频正弦，明显慢于信号，可被读出层学习/补偿）。

    相位由 seed 决定（可复现），但形状是平滑慢变函数，读出层在标定段
    学到后可外推到全段——这是漂移补偿能泛化的前提（随机游走不可预测，
    无法外推，故用确定性慢变基线）。
    """
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0.0, 2.0 * np.pi)
    k = np.arange(int(n)) / max(int(n) - 1, 1)
    return (np.sin(2.0 * np.pi * 0.5 * k + phase)
            + 0.5 * np.sin(2.0 * np.pi * 0.25 * k + phase / 2.0))


def simulate_drift(clean, mode: str = "offset_gain_baseline", *, offset: float = 0.0,
                   gain: float = 1.0, baseline_amplitude: float = 0.0,
                   seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """对干净信号叠加漂移，返回 (drifted, drift_component)。

    drift_component = drifted - clean，供评估漂移补偿效果。
    """
    clean = np.asarray(clean, dtype=float)
    if clean.ndim != 1:
        raise ValueError("输入必须为一维")
    if mode not in DRIFT_MODES:
        raise ValueError(f"未知漂移模式 {mode!r}，可选: {DRIFT_MODES}")
    n = clean.size
    drift_comp = np.zeros(n)
    if "offset" in mode:
        drift_comp += float(offset)
    if "gain" in mode:
        drift_comp += (float(gain) - 1.0) * clean
    if "baseline" in mode:
        drift_comp += float(baseline_amplitude) * _slow_baseline(n, seed)
    return clean + drift_comp, drift_comp


class DriftCompensator:
    """RC 漂移补偿器：reservoir 特征 → 读出层映射（可岭回归 + RLS 在线更新）。"""

    def __init__(self, reservoir: Reservoir, ridge: float = 1e-6) -> None:
        self.reservoir = reservoir
        self.ridge = float(ridge)

    def fit(self, x, y=None) -> "DriftCompensator":
        """训练读出层。

        y 缺省时自关联（x → x，标称流形重建，弱监督漂移过滤）；
        给定 y 时做配对补偿映射（x=带漂移观测 → y=干净参考），更稳。
        """
        x = np.asarray(x, dtype=float)
        if x.ndim != 1:
            raise ValueError("输入必须为一维")
        y = x if y is None else np.asarray(y, dtype=float)
        states = self.reservoir.run(x)
        if states.shape[0] != y.shape[0]:
            raise ValueError(f"输入/目标长度不一致: {states.shape[0]} vs {y.shape[0]}")
        self.reservoir.train_readout(states, y, ridge=self.ridge)
        return self

    def compensate(self, x) -> np.ndarray:
        """漂移补偿：reservoir 状态 → 读出层重建，返回干净估计。"""
        x = np.asarray(x, dtype=float)
        if x.ndim != 1:
            raise ValueError("输入必须为一维")
        states = self.reservoir.run(x)
        return self.reservoir.predict(states)

    def update(self, x, y) -> "DriftCompensator":
        """RLS 在线自适应更新读出层（新配对样本增量修正 W_out）。"""
        if self.reservoir.W_out is None or self.reservoir._precision is None:
            raise RuntimeError("先 fit 再 update")
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        states = self.reservoir.run(x)
        s = _augment(states)
        w = self.reservoir.W_out.copy()
        p = self.reservoir._precision.copy()
        for row, target in zip(s, y):
            row = row[:, None]
            denom = 1.0 + float((row.T @ p @ row).item())
            gain_k = (p @ row) / denom
            err = float(target) - float((row.T @ w).item())
            w += (gain_k * err).reshape(w.shape)
            p -= gain_k @ (row.T @ p)
        self.reservoir.W_out = w
        self.reservoir._precision = p
        return self
