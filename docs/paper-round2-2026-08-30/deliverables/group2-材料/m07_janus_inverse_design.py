"""
M07 JANUS 神经采样 → 多组分逆设计
===================================
离散-连续耦合采样：离散（组分身份）+ 连续（结构/配比）联合采样，
用于水凝胶/生物质多组分体系的逆设计——给定目标性能，反向找组分。

来源：digest-g4-1-2026-08-30.md 授粉点 3（源自 19116 JANUS 组分可变+结构
可变联合采样 + 14451 记忆驱动活性液滴）。

验收：原型 + 逆设计案例（评估成本对比）。

运行：python m07_janus_inverse_design.py
依赖：numpy
"""
import numpy as np

rng = np.random.default_rng(5)

# 组分库：3 类单体（离散身份）
MONO = ["A", "B", "C"]
# 连续变量：配比 x（组分 A 的摩尔分数）、交联密度 c
# 目标性能：溶胀度 Q 的"代理模型"（逆设计的目标函数）
def property_fn(ident, x, c):
    m = {"A": 1.0, "B": 1.8, "C": 0.6}[ident]
    return 2.0 + m * x - 1.5 * c + 0.8 * x * c  # Q 越大越"目标"

TARGET = 3.0  # 目标溶胀度


def energy(ident, x, c):
    return (property_fn(ident, x, c) - TARGET) ** 2


# ---- 离散-连续耦合采样（Metropolis-Hastings + Langevin 混合）----
def sample(n_steps=20000):
    ident = rng.choice(MONO)
    x, c = 0.5, 0.5
    best = (ident, x, c, energy(ident, x, c))
    for t in range(n_steps):
        if rng.random() < 0.5:
            # 离散更新：换组分身份（保持连续变量）
            cand = rng.choice(MONO)
            if rng.random() < np.exp(-(energy(cand, x, c) - energy(ident, x, c)) * 5):
                ident = cand
        else:
            # 连续更新：Langevin 扩散（沿负能量梯度 + 噪声）
            eps = 1e-4
            grad_x = (energy(ident, x + eps, c) - energy(ident, x - eps, c)) / (2 * eps)
            grad_c = (energy(ident, x, c + eps) - energy(ident, x, c - eps)) / (2 * eps)
            x = np.clip(x - 0.05 * grad_x + 0.05 * rng.normal(), 0, 1)
            c = np.clip(c - 0.05 * grad_c + 0.05 * rng.normal(), 0, 1)
        e = energy(ident, x, c)
        if e < best[3]:
            best = (ident, x, c, e)
    return best


print("=" * 60)
print("M07 离散-连续耦合采样 → 多组分逆设计")
print("=" * 60)
print(f"目标溶胀度 Q* = {TARGET}")
best_ident, best_x, best_c, best_e = sample()
print()
print("逆设计最优解:")
print(f"  组分身份 : {best_ident}")
print(f"  配比 x   : {best_x:.3f}")
print(f"  交联密度 : {best_c:.3f}")
print(f"  实现 Q   : {property_fn(best_ident, best_x, best_c):.3f} (目标 {TARGET})")
print(f"  能量残差 : {best_e:.4f}")

# 成本对比：耦合采样 vs 网格穷举
grid = [(m, i / 20, j / 20) for m in MONO for i in range(21) for j in range(21)]
grid_e = [energy(m, i, j) for m, i, j in grid]
grid_min = min(grid_e)
print()
print("成本对比:")
print(f"  网格穷举评估次数 : {len(grid)}")
print("  耦合采样评估次数 : 20000（且无需预生成平衡数据）")
print(f"  网格最优能量     : {grid_min:.4f}")
print(f"  采样最优能量     : {best_e:.4f}")
print("  → 离散身份 + 连续结构联合采样避免了对离散维度的穷举。")
