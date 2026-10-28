"""hit/miss 数据拟合 POD 曲线（解析式，scipy 最小二乘）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

DEFAULT_K = 2.0


@dataclass
class PODCurve:
    """POD 曲线：`pod(a) = 1 - exp(-((a / a90) ** k))`。

    该形式保证 `pod(a90) = 1 - e^-1 ≈ 0.632` **不是** 0.9 —— 注意 `a90` 在此参数化里
    是**尺度参数**（特征尺寸），真正的 POD=0.9 点由 `a90(curve)` 反解给出。这一点在
    报告里写清，避免把尺度参数误读成 90% 检出尺寸。
    """

    a90_scale: float
    k: float
    a_min: float
    a_max: float
    hit_rate: float
    cov: Any = field(default=None, repr=False)

    def pod(self, a: float) -> float:
        import math

        if a <= 0:
            return 0.0
        return 1.0 - math.exp(-((a / self.a90_scale) ** self.k))

    def __call__(self, a: float) -> float:
        return self.pod(a)

    @property
    def a_for_pod_09(self) -> float:
        """POD = 0.9 对应的缺陷尺寸：解 `1 - exp(-((a/A)**k)) = 0.9`。"""
        import math

        return self.a90_scale * (math.log(10.0) ** (1.0 / self.k))


def _fit(a_vals: Sequence[float], outcomes: Sequence[bool]) -> tuple[float, float, Any]:
    """用 curve_fit 拟合（a90_scale, k）。失败时退回稳健初值。"""
    import numpy as np
    from scipy.optimize import curve_fit

    def model(a, a90_scale, k):
        return 1.0 - np.exp(-((np.asarray(a, dtype=float) / a90_scale) ** k))

    xs = np.asarray(a_vals, dtype=float)
    ys = np.asarray([1.0 if o else 0.0 for o in outcomes], dtype=float)
    guess_a = float(np.median(xs)) or 1.0
    try:
        popt, cov = curve_fit(
            model, xs, ys, p0=[guess_a, DEFAULT_K],
            bounds=([1e-9, 0.05], [np.inf, 50.0]), maxfev=20000,
        )
        return float(popt[0]), float(popt[1]), cov
    except (RuntimeError, ValueError):  # 点数太少/全同值时 curve_fit 会失败
        return guess_a, DEFAULT_K, None


def pod_curve(a_values: Iterable[float], hit_miss: Sequence[tuple[float, bool]]) -> PODCurve:
    """由 hit/miss 数据拟合 POD 曲线。

    Args:
        a_values: 关心的尺寸网格（用于记录样本区间，不参与拟合）
        hit_miss: `[(a, 是否检出), ...]`

    Raises:
        ValueError: 样本为空，或缺失全部为 True/False（无法识别 S 形）。
    """
    data = [(float(a), bool(hit)) for a, hit in hit_miss]
    if not data:
        raise ValueError("hit_miss 不能为空")
    outcomes = [hit for _, hit in data]
    if all(outcomes) or not any(outcomes):
        raise ValueError("hit/miss 全为同一类，无法拟合 POD 曲线（需要既有检出又有漏检）")

    a_vals = [a for a, _ in data]
    scale, k, cov = _fit(a_vals, outcomes)
    grid = [float(a) for a in a_values] or a_vals
    return PODCurve(
        a90_scale=scale,
        k=k,
        a_min=min(a_vals),
        a_max=max(a_vals),
        hit_rate=sum(outcomes) / len(outcomes),
        cov=cov,
    )


def a90(curve: PODCurve) -> float:
    """POD = 0.9 对应的缺陷尺寸（落在样本区间内，区间外按边界截断）。"""
    value = curve.a_for_pod_09
    return max(curve.a_min, min(curve.a_max, value))
