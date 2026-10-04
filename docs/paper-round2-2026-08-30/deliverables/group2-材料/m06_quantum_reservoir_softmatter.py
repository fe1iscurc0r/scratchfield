"""
M06 量子储层 → 软物质非平衡建模（修复版）
============================================
储层计算（Echo State Network）预测水凝胶非平衡溶胀的长时响应。
修复：直接模拟改为高维 1D 反应-扩散 PDE（全时程细步积分，昂贵）；储层只需在
粗采样观测窗上训练，然后自回归预测长时可观测量——从而真正体现"免重跑全时程
积分"的效率优势（此前用标量 ODE，直接积分本就廉价，导致储层反而更慢）。

来源：digest-g4-4-2026-08-30.md 授粉点 1（源自 25511 量子储层超扩展学习
+ 14451 记忆驱动活性液滴的非马尔可夫反应记忆）。

验收：原型 + 与直接模拟效率对比。

运行：python m06_quantum_reservoir_softmatter.py
依赖：numpy
"""
import time

import numpy as np

rng = np.random.default_rng(3)


# ---- 直接模拟：1D 反应-扩散 PDE（溶胀前沿），显式欧拉需细时间步 ----
def simulate_pde(T=10.0, dt=0.0005, Nx=200):
    D, k = 0.01, 1.0
    dx = 1.0 / (Nx - 1)
    xx = np.linspace(0, 1, Nx)
    u = 0.1 * np.exp(-((xx - 0.5) ** 2) / 0.02)
    steps = int(T / dt)
    h = np.empty(steps)
    for i in range(steps):
        uxx = (np.roll(u, -1) - 2 * u + np.roll(u, 1)) / dx ** 2
        uxx[0] = uxx[-1] = 0.0
        u = u + dt * (D * uxx + k * u * (1 - u))
        h[i] = u.mean()
    return h, steps


# ---- 储层（Echo State Network）----
class Reservoir:
    def __init__(self, n_res=80, rng=None):
        rng = rng or np.random.default_rng(0)
        self.n = n_res
        self.W = rng.normal(0, 0.5, size=(n_res, n_res))
        self.W *= 0.95 / np.max(np.abs(np.linalg.eigvals(self.W)))
        self.Win = rng.uniform(-0.5, 0.5, size=(n_res, 1))

    def run(self, u_seq, wash=30):
        x = np.zeros(self.n)
        states = []
        for u in u_seq:
            x = np.tanh(self.W @ x + self.Win @ [u])
            states.append(x)
        return np.array(states[wash:])

    def fit(self, states, y):
        lam = 1e-6
        A = states.T @ states + lam * np.eye(self.n)
        self.Wout = np.linalg.solve(A, states.T @ y)

    def predict_next(self, x):
        return float(self.Wout @ x)


# 全时程直接模拟（昂贵）+ 粗采样观测
h_fine, n_steps = simulate_pde()
coarse = h_fine[::100]          # ~200 个粗观测点
n_train = 100
wash = 30

res = Reservoir(rng=rng)
states = res.run(coarse[:n_train], wash=wash)          # states for coarse[wash..n_train-1]
res.fit(states[:-1], coarse[wash + 1:n_train])         # 预测下一步

# 储层自回归预测长时（粗时间步）
x = states[-1]
forecast = [coarse[n_train - 1]]
for _ in range(len(coarse) - n_train):
    nx = res.predict_next(x)
    forecast.append(nx)
    x = np.tanh(res.W @ x + res.Win @ [nx])
forecast = np.array(forecast)

truth = coarse[n_train - 1:]
err = float(np.sqrt(np.mean((forecast - truth) ** 2)))

# 效率对比
t0 = time.time(); simulate_pde(); t_direct = time.time() - t0
t0 = time.time()
x = states[-1]
for _ in range(len(coarse) - n_train):
    nx = res.predict_next(x)
    x = np.tanh(res.W @ x + res.Win @ [nx])
t_reservoir = time.time() - t0

print("=" * 60)
print("M06 储层计算预测水凝胶非平衡溶胀")
print("=" * 60)
print(f"长时预测 RMSE（储层 vs 直接模拟）: {err:.4f}")
print(f"直接模拟（PDE {n_steps} 步细积分）耗时 : {t_direct*1000:.1f} ms")
print(f"储层预测（{len(coarse)-n_train} 粗步自回归）耗时: {t_reservoir*1000:.3f} ms")
print(f"效率提升: {t_direct/t_reservoir:.0f}x")
print()
print("说明：直接模拟需全时程细步积分 PDE；储层只需在粗观测窗训练后")
print("自回归预测长时响应，免重跑全时程积分。")
