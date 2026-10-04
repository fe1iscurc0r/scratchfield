"""R37 · OT 正则频谱去卷积原型（对比 TV/L1 保时序性）

灵感：weekly_pollination 8-30 轮授粉点 1（OT 正则动态重建）。

问题：频谱序列 X(f,t)（freq × time）经多径卷积模糊 + 噪声 → Y。去卷积恢复 X，
正则项选择决定「时序连贯性」：
  - L1 正则：逐元素稀疏，无时序结构（各时间片独立稀疏）
  - TV 正则：相邻时间片一阶差 L1（时序平滑）
  - OT 正则：相邻时间片能量分布的 Wasserstein-1 距离（按累积能量剖面，
    运输式时序连贯）——对「谱能量随时间的移动/重排」更鲁棒

用 scipy.optimize 对同一数据项 + 不同正则项分别求解，以重建 MSE 与时序相关系数
对比三者。

运行：python -m mcpserver.rf_brain.prototypes.ot_deconvolution
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def synthesize(nf: int, nt: int, *, kernel: np.ndarray = np.array([0.05, 0.2, 0.5, 0.2, 0.05]),
               noise: float = 0.2, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """合成时序连贯频谱序列 X + 模糊观测 Y。"""
    rng = np.random.default_rng(seed)
    f = np.arange(nf) / nf
    t = np.arange(nt)
    # 时序连贯：几个谱峰随时间缓慢移动
    X = np.zeros((nf, nt))
    for i, center0 in enumerate((0.3, 0.6)):
        center = center0 + 0.1 * np.sin(0.3 * t)
        X += np.exp(-((f[:, None] - center[None, :]) / 0.1) ** 2)
    Y = np.array([np.convolve(X[:, t], kernel, mode="same") for t in range(nt)]).T
    Y = Y + noise * rng.standard_normal((nf, nt))
    return X, Y


def _blur(X: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    nt = X.shape[1]
    return np.array([np.convolve(X[:, t], kernel, mode="same") for t in range(nt)]).T


def _l1_reg(X: np.ndarray) -> float:
    return float(np.abs(X).sum())


def _tv_reg(X: np.ndarray) -> float:
    return float(np.abs(np.diff(X, axis=1)).sum())


def _ot_reg(X: np.ndarray) -> float:
    """相邻时间片累积能量剖面的 W1 距离之和（1D 最优传输）。"""
    C = np.cumsum(np.abs(X), axis=0)          # 每列累积能量剖面
    return float(np.abs(np.diff(C, axis=1)).sum())


_REG = {"l1": _l1_reg, "tv": _tv_reg, "ot": _ot_reg}


def deconvolve(Y: np.ndarray, kernel: np.ndarray, reg: str, lam: float) -> np.ndarray:
    """用指定正则项做去卷积，返回重建 X_hat。"""
    nf, nt = Y.shape
    x0 = Y.ravel().copy()

    def obj(v):
        X = v.reshape(nf, nt)
        data = np.sum((_blur(X, kernel) - Y) ** 2)
        return data + lam * _REG[reg](X)

    res = minimize(obj, x0, method="L-BFGS-B", options={"maxiter": 300})
    return res.x.reshape(nf, nt)


def metrics(X_hat: np.ndarray, X_truth: np.ndarray) -> dict:
    """重建 MSE 与时序相关系数（保时序性指标）。"""
    mse = float(np.mean((X_hat - X_truth) ** 2))
    # 时序相关系数：对每个频点的时间序列求相关系数后平均
    corrs = [np.corrcoef(X_hat[f], X_truth[f])[0, 1] for f in range(X_truth.shape[0])]
    return {"mse": mse, "temporal_corr": float(np.mean(corrs))}


def main() -> None:
    kernel = np.array([0.05, 0.2, 0.5, 0.2, 0.05])
    X, Y = synthesize(32, 20, kernel=kernel, seed=0)
    print(f"观测（无去卷积）MSE = {metrics(Y, X)['mse']:.3f}")
    print(f"{'正则':<6}{'MSE':>10}{'时序相关':>10}")
    for reg in ("l1", "tv", "ot"):
        Xh = deconvolve(Y, kernel, reg, lam=1.0)
        m = metrics(Xh, X)
        print(f"{reg:<6}{m['mse']:>10.3f}{m['temporal_corr']:>10.3f}")


if __name__ == "__main__":
    main()
