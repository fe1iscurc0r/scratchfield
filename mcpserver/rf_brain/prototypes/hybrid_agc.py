"""R36 · LQG/积分器混合 AGC 原型（无线电增益控制）

低阶 LQG（标量卡尔曼滤波）+ 积分器高阶混合，用于无线电 AGC/锁相。核心收益：
LQG 部分用卡尔曼滤波**滤除测量噪声**，积分器在其滤波后的估计上做增益调整，
从而比「纯积分器直接对噪声测量积分」抖动更小、跟踪更稳。

模型（dB 域）：
  信号电平 s[k] 缓慢随机游走（漂移）；AGC 输出 o[k] = g[k] + s[k]；
  测量 m[k] = o[k] + n[k]（含高斯测量噪声）；目标 T。

  - 纯积分器：g[k+1] = g[k] + μ·(T - m[k])            （对噪声直接反应）
  - 混合 LQG：先卡尔曼估计 ŝ[k]（滤噪声），再 g[k+1] = g[k] + μ·(T - g[k] - ŝ[k])

对比：输出误差方差（越接近目标越稳）+ 增益抖动。

运行：python -m mcpserver.rf_brain.prototypes.hybrid_agc
"""
from __future__ import annotations

import numpy as np


def synthesize(n: int, *, drift_std: float = 0.05, noise_std: float = 0.5, seed: int = 0) -> dict:
    """合成信号电平（随机游走）+ 测量噪声。"""
    rng = np.random.default_rng(seed)
    s = np.zeros(n)
    for i in range(1, n):
        s[i] = s[i - 1] + drift_std * rng.standard_normal()
    n = noise_std * rng.standard_normal(n)
    return {"s": s, "noise": n}


def pure_integrator(s: np.ndarray, noise: np.ndarray, *, target: float = 0.0,
                    mu: float = 0.1) -> np.ndarray:
    """纯积分器 AGC：g[k+1] = g[k] + μ(T - (g[k]+s[k]+n[k]))。返回输出误差序列。"""
    g = 0.0
    errs = []
    for k in range(s.size):
        m = g + s[k] + noise[k]
        errs.append(target - m)
        g += mu * (target - m)
    return np.array(errs)


def hybrid_lqg(s: np.ndarray, noise: np.ndarray, *, target: float = 0.0,
               mu: float = 0.1, q: float = 0.01, r: float = 0.25) -> np.ndarray:
    """混合 LQG+积分器：卡尔曼滤波估计 s，再积分。返回输出误差序列。"""
    g = 0.0
    s_hat = 0.0
    P = 1.0
    errs = []
    for k in range(s.size):
        # 卡尔曼滤波：观测 z = m - g = s + n
        z = (g + s[k] + noise[k]) - g
        # 预测
        P_pred = P + q
        # 更新
        K = P_pred / (P_pred + r)
        s_hat = s_hat + K * (z - s_hat)
        P = (1 - K) * P_pred
        # 控制：在滤波估计上积分
        err = target - (g + s_hat)
        errs.append(err)
        g += mu * err
    return np.array(errs)


def main() -> None:
    d = synthesize(2000, seed=0)
    e_pure = pure_integrator(d["s"], d["noise"])
    e_hyb = hybrid_lqg(d["s"], d["noise"])
    print(f"纯积分器  输出误差方差 = {np.var(e_pure):.4f}")
    print(f"混合 LQG   输出误差方差 = {np.var(e_hyb):.4f}")
    print(f"方差降低 = {(1 - np.var(e_hyb)/np.var(e_pure))*100:.1f}%")


if __name__ == "__main__":
    main()
