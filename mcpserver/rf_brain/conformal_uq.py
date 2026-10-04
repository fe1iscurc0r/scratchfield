"""K24 保形 UQ 神经算子——分裂保形校准，覆盖率保证（2608.28515）

来源授粉点：round3 digest-g7 2608.28515（Conformal UQ for Neural Operators）——
给神经算子的点预测补**保形不确定性量化**：不依赖分布假设，只要数据可交换，预测区间
就带有限样本覆盖率保证（P(真值 ∈ 区间) ≥ 1−α）。

与 R56 的轨迹自适应 conformal（`conformal_channel_pred.py`，按预测步分别取分位）
同族但更通用：本模块是**通用神经算子保形层**——包裹任意 `operator: X → 点预测`，
在校准集上统计残差分位数，输出带覆盖保证的预测区间。rf_brain 频谱/信道预测直接复用。

纯 numpy 实现，无第三方依赖。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["PredictionInterval", "SplitConformal", "MondrianConformal", "ConformalUQ", "linear_operator_fit"]


@dataclass
class PredictionInterval:
    """一次预测的区间结果。"""

    point: np.ndarray  # 点预测
    lower: np.ndarray  # 下界
    upper: np.ndarray  # 上界

    @property
    def width(self) -> np.ndarray:
        return self.upper - self.lower

    def coverage(self, truth: np.ndarray) -> float:
        t = np.asarray(truth, dtype=float)
        inside = (t >= self.lower) & (t <= self.upper)
        return float(np.mean(inside))


class SplitConformal:
    """分裂保形回归：校准集残差分位数 → 对称预测区间 [ŷ−q̂, ŷ+q̂]。"""

    def __init__(self, alpha: float = 0.10) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha 需在 (0,1)，实际 {alpha}")
        self.alpha = float(alpha)
        self.qhat: float | None = None

    def calibrate(self, y_pred: np.ndarray, y_true: np.ndarray) -> "SplitConformal":
        """用校准集残差 |y_true − y_pred| 求有限样本修正分位点。"""
        y_pred = np.asarray(y_pred, dtype=float)
        y_true = np.asarray(y_true, dtype=float)
        if y_pred.shape != y_true.shape or y_pred.size == 0:
            raise ValueError("y_pred 与 y_true 形状不一致或为空")
        scores = np.abs(y_true - y_pred)
        n = scores.size
        # 有限样本修正：保证 P(覆盖) ≥ 1−α 的保形分位点
        level = min(1.0, np.ceil((n + 1) * (1.0 - self.alpha)) / n)
        self.qhat = float(np.quantile(scores, level))
        return self

    def predict_interval(self, y_pred: np.ndarray) -> PredictionInterval:
        y_pred = np.asarray(y_pred, dtype=float)
        if self.qhat is None:
            raise RuntimeError("先 calibrate() 再 predict_interval()")
        return PredictionInterval(point=y_pred, lower=y_pred - self.qhat, upper=y_pred + self.qhat)

    def coverage(self, y_pred: np.ndarray, y_true: np.ndarray) -> float:
        return self.predict_interval(y_pred).coverage(y_true)

    @property
    def width(self) -> float:
        """区间宽度 = 2·q̂（固定宽度，随 α 减小而变宽）。"""
        if self.qhat is None:
            raise RuntimeError("先 calibrate() 再取 width")
        return 2.0 * float(self.qhat)


class ConformalUQ:
    """通用神经算子保形层：包裹 operator 的点预测，输出带覆盖保证的区间。"""

    def __init__(self, operator, alpha: float = 0.10) -> None:
        self.operator = operator  # callable: X -> point prediction
        self.conformal = SplitConformal(alpha)

    def calibrate(self, X_cal: np.ndarray, y_cal: np.ndarray) -> "ConformalUQ":
        pred = np.asarray(self.operator(X_cal), dtype=float)
        self.conformal.calibrate(pred, y_cal)
        return self

    def predict(self, X: np.ndarray) -> PredictionInterval:
        return self.conformal.predict_interval(np.asarray(self.operator(X), dtype=float))

    @property
    def width(self) -> float:
        return self.conformal.width


class MondrianConformal:
    """逐频点（Mondrian）保形：按列（频点）独立校准分位点，宽度自适应各频点噪声。

    频谱/信道预测场景各频点噪声水平差异大，逐点校准比全局单一 q̂ 更紧——**平均区间
    更窄仍满足覆盖率**，直接强化"区间宽度可控"。

    输入为 1D 时退化为 SplitConformal；2D（n 样本 × bins）时逐列取分位。
    """

    def __init__(self, alpha: float = 0.10) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha 需在 (0,1)，实际 {alpha}")
        self.alpha = float(alpha)
        self.qhat: np.ndarray | None = None  # 标量（1D）或 (bins,)（2D 逐列）

    def calibrate(self, y_pred: np.ndarray, y_true: np.ndarray) -> "MondrianConformal":
        y_pred = np.asarray(y_pred, dtype=float)
        y_true = np.asarray(y_true, dtype=float)
        if y_pred.shape != y_true.shape or y_pred.size == 0:
            raise ValueError("y_pred 与 y_true 形状不一致或为空")
        scores = np.abs(y_true - y_pred)
        n = scores.shape[0]
        level = min(1.0, np.ceil((n + 1) * (1.0 - self.alpha)) / n)
        self.qhat = np.quantile(scores, level, axis=0)  # 1D→标量；2D→逐列
        return self

    def predict_interval(self, y_pred: np.ndarray) -> PredictionInterval:
        y_pred = np.asarray(y_pred, dtype=float)
        if self.qhat is None:
            raise RuntimeError("先 calibrate() 再 predict_interval()")
        return PredictionInterval(point=y_pred, lower=y_pred - self.qhat, upper=y_pred + self.qhat)

    def coverage(self, y_pred: np.ndarray, y_true: np.ndarray) -> float:
        return self.predict_interval(y_pred).coverage(y_true)

    @property
    def mean_width(self) -> float:
        """平均区间宽度 = 2·mean(q̂)（逐点自适应）。"""
        if self.qhat is None:
            raise RuntimeError("先 calibrate() 再取 mean_width")
        return 2.0 * float(np.mean(self.qhat))


def linear_operator_fit(X: np.ndarray, Y: np.ndarray) -> callable:
    """最小二乘线性算子（含截距，神经算子的最简替身，测试/演示用）。

    返回 callable: X_new -> [X_new, 1] @ W。真机侧可替换为任意神经算子。
    """
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    Xb = np.hstack([X, np.ones((X.shape[0], 1))])  # 加截距列
    XtX = Xb.T @ Xb
    W = np.linalg.solve(XtX + 1e-6 * np.eye(XtX.shape[0]), Xb.T @ Y)
    return lambda Xn: np.hstack([np.asarray(Xn, dtype=float), np.ones((Xn.shape[0], 1))]) @ W
