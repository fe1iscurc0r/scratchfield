"""射频大脑 · 轨迹自适应 conformal 信道预测（R56）

授粉自 digest-g1-4 2608.27124（TRACE-CRC: Trajectory-Adaptive Conformal Risk
Control for CSI）：给 R08 的谱约束信道预测（``spectral_constrained_predictor``）
补「覆盖率保证」——多步 CSI 预测不再只给点估计，而是给带覆盖保证的预测区间，
控制任意预测帧的覆盖风险。

方法（split conformal，轨迹自适应）：
  1. 点预测复用 R08 的 LinearReservoir（谱半径 ≤1 构造性稳定，多步不发散）
  2. 校准集上按预测步 t 分别统计残差 |y_true − ŷ|（越往后误差越大）
  3. 每步取 conformal 修正分位数 q_t = quantile(残差_t, target_coverage·(1+1/n))
  4. 预测区间 [ŷ_t − q_t, ŷ_t + q_t]——沿轨迹自适应展宽（后步更宽）

验收口径：合成信道覆盖率 ≥90%，且区间宽度随 target_coverage 可控（覆盖越高越宽）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mcpserver.rf_brain.prototypes.spectral_constrained_predictor import (
    LinearReservoir,
    synthesize_csi,
)

__all__ = [
    "PredictionInterval",
    "ConformalChannelPredictor",
    "synthesize_csi",
]


@dataclass
class PredictionInterval:
    """一次多步预测的区间结果（长度均 = horizon）。"""
    point: np.ndarray   # 点预测
    lower: np.ndarray   # 下界
    upper: np.ndarray   # 上界
    horizon: int

    @property
    def width(self) -> np.ndarray:
        return self.upper - self.lower

    def coverage(self, truth: np.ndarray) -> float:
        """真值落在区间内的比例（覆盖率）。"""
        t = np.asarray(truth, dtype=float)
        m = min(t.size, self.horizon)
        inside = (t[:m] >= self.lower[:m]) & (t[:m] <= self.upper[:m])
        return float(inside.mean())


class ConformalChannelPredictor:
    """轨迹自适应 conformal 信道预测器：点预测 + 覆盖保证区间。"""

    def __init__(self, point: LinearReservoir | None = None, *, hidden: int = 32,
                 spectral_radius: float = 0.9, seed: int = 0) -> None:
        self.point = point or LinearReservoir(hidden=hidden, spectral_radius=spectral_radius, seed=seed)
        self._quantiles: np.ndarray | None = None
        self._horizon = 0

    def train(self, series: np.ndarray, *, reg: float = 1e-6, washout: int = 10) -> None:
        self.point.train(np.asarray(series, dtype=float), reg=reg, washout=washout)

    def calibrate(self, series: np.ndarray, *, horizon: int = 20,
                  target_coverage: float = 0.9, warmup: int = 20, stride: int = 10) -> "ConformalChannelPredictor":
        """split conformal 校准：滑动窗口预测，按步统计残差 → 每步分位数。

        每步独立取 conformal 修正分位数（q_t 随步增大）——「轨迹自适应」。
        """
        s = np.asarray(series, dtype=float)
        if horizon < 1:
            raise ValueError("horizon 必须 >= 1")
        if not (0.0 < target_coverage < 1.0):
            raise ValueError("target_coverage 必须在 (0,1)")
        residuals: list[list[float]] = [[] for _ in range(horizon)]
        for start in range(0, s.size - warmup - horizon, max(1, stride)):
            init = s[start:start + warmup]
            truth = s[start + warmup:start + warmup + horizon]
            if truth.size < horizon:
                break
            preds = self.point.rollout(init, horizon)  # 长度 horizon+1，preds[1:] 为预测
            for t in range(horizon):
                residuals[t].append(abs(float(truth[t]) - float(preds[t + 1])))

        qs = np.empty(horizon, dtype=float)
        for t in range(horizon):
            n = len(residuals[t])
            if n == 0:
                raise ValueError(f"校准窗口不足（第 {t} 步无样本），请加长校准序列")
            # 精确有限样本 conformal 分位数：取 ⌈(n+1)·coverage⌉ 阶残差，
            # 保证边际覆盖率 ≥ target_coverage（比 np.quantile 线性插值更稳）。
            k = min(n, int(np.ceil((n + 1) * target_coverage)))
            qs[t] = float(np.sort(residuals[t])[k - 1])
        self._quantiles = qs
        self._horizon = horizon
        return self

    def predict_interval(self, init_seq: np.ndarray, n_steps: int | None = None) -> PredictionInterval:
        """输出带覆盖保证的多步预测区间。"""
        if self._quantiles is None:
            raise RuntimeError("尚未 calibrate")
        h = self._horizon if n_steps is None else int(n_steps)
        if h > self._horizon:
            raise ValueError(f"预测步数 {h} 超过校准 horizon {self._horizon}")
        preds = self.point.rollout(np.asarray(init_seq, dtype=float), h)
        point = preds[1:]
        q = self._quantiles[:h]
        return PredictionInterval(point=point, lower=point - q, upper=point + q, horizon=h)
