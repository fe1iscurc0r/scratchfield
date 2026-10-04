"""R26 · 信道模型偏差检测原型（因果干预分析）

灵感：digest-g1-3 授粉点③ · 论文 2608.24303（对时序基础模型施加因果干预，识别
对 trend/harmonic/regime switch 的依赖偏差）。

思想：信道状态 y = trend（慢漂移）+ harmonic（周期分量）+ noise。一个「只学趋势」
的偏差模型在含 harmonic 的数据上残差大，暴露其偏差；用因果干预（do 操作，如
移除 harmonic）可以定位偏差来源——干预后偏差模型残差骤降，证明它此前的高误差
正源于「无视 harmonic」而非正确建模。

原型：
  - fit_trend_only  偏差模型（只看 trend，忽略 harmonic）
  - fit_full        完整模型（trend + harmonic）
  - 残差对比 + 干预（移除某分量后残差变化）定位偏差

运行：python -m mcpserver.rf_brain.prototypes.channel_bias_detect
"""
from __future__ import annotations

import numpy as np


def synthesize(n: int, *, beta: float = 0.05, amp: float = 2.0, omega: float = 0.1,
               noise: float = 0.3, seed: int = 0) -> dict:
    """合成信道序列 y = trend + harmonic + noise，返回各分量。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    trend = beta * t
    harmonic = amp * np.sin(omega * t)
    y = trend + harmonic + noise * rng.standard_normal(n)
    return {"t": t, "y": y, "trend": trend, "harmonic": harmonic, "omega": omega}


def _lstsq_predict(X: np.ndarray, y: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    return X_te @ w


def fit_trend_only(d: dict) -> np.ndarray:
    """偏差模型：只用 [1, t] 拟合（忽略 harmonic）。"""
    X = np.column_stack([np.ones_like(d["t"]), d["t"]])
    return _lstsq_predict(X, d["y"], X)


def fit_full(d: dict) -> np.ndarray:
    """完整模型：用 [1, t, sin(ωt), cos(ωt)] 拟合。"""
    t, om = d["t"], d["omega"]
    X = np.column_stack([np.ones_like(t), t, np.sin(om * t), np.cos(om * t)])
    return _lstsq_predict(X, d["y"], X)


def residual(y: np.ndarray, y_hat: np.ndarray) -> float:
    return float(np.mean((y - y_hat) ** 2))


def intervene_remove_harmonic(d: dict) -> dict:
    """因果干预 do(harmonic=0)：从观测中移除 harmonic 分量。"""
    d2 = dict(d)
    d2["y"] = d["y"] - d["harmonic"]
    d2["harmonic"] = np.zeros_like(d["harmonic"])
    return d2


def main() -> None:
    d = synthesize(400, seed=0)
    r_trend = residual(d["y"], fit_trend_only(d))
    r_full = residual(d["y"], fit_full(d))
    d_no_harm = intervene_remove_harmonic(d)
    r_trend_no_harm = residual(d_no_harm["y"], fit_trend_only(d_no_harm))
    r_full_no_harm = residual(d_no_harm["y"], fit_full(d_no_harm))
    print(f"含 harmonic：偏差模型残差 = {r_trend:.3f}   完整模型残差 = {r_full:.3f}")
    print(f"移除 harmonic 后：偏差模型残差 = {r_trend_no_harm:.3f}   完整模型 = {r_full_no_harm:.3f}")
    print(f"偏差定位：偏差模型残差下降 {(1 - r_trend_no_harm/r_trend)*100:.0f}%（说明其误差源于无视 harmonic）")


if __name__ == "__main__":
    main()
