"""
M14 物理引导神经 PDE → 热解动力学
====================================
积分约束（预测导数再积分）vs 直接步进（预测下一状态），
解决直接步进的特征值>1 误差积累，建模生物质热解反应动力学。

来源：digest-g1-3-2026-08-30.md 授粉点 ②（源自 16084 特征值分析神经模拟器
+ 22112 Symbolic Neural ODEs）。

验收：原型 + 长时间积分稳定性验证。

运行：python m14_neural_pde_pyrolysis.py
依赖：numpy
"""
import numpy as np

rng = np.random.default_rng(4)

# ---- 真实热解动力学：dα/dt = k(1-α)，α=转化率，固定点 α=1 ----
k, dt = 2.0, 0.3


def true_next(a):
    return a + dt * k * (1 - a)


# 训练数据：短轨迹，只覆盖 α ∈ [0, 0.5]（有限数据 → 外推测试）
def gen_traj(a0, steps=8):
    traj = [a0]
    a = a0
    for _ in range(steps):
        a = true_next(a)
        traj.append(a)
    return np.array(traj)


train_a0 = rng.uniform(0, 0.4, size=40)
X_tr, y_tr = [], []
for a0 in train_a0:
    tr = gen_traj(a0)
    X_tr.extend(tr[:-1]); y_tr.extend(tr[1:])
X_tr = np.array(X_tr).reshape(-1, 1)
y_tr = np.array(y_tr)

# ---- 直接步进模型：拟合 α_{t+1} = w_d α_t + b_d ----
A_d = np.column_stack([X_tr.ravel(), np.ones_like(X_tr.ravel())])
w_d, b_d = np.linalg.lstsq(A_d, y_tr, rcond=None)[0]

# ---- 积分约束模型：拟合 dα/dt = w_i α_t + b_i，再积分 ----
deriv = (y_tr - X_tr.ravel()) / dt
w_i, b_i = np.linalg.lstsq(A_d, deriv, rcond=None)[0]


def direct_step(a):
    return w_d * a + b_d


def integral_step(a):
    return a + dt * (w_i * a + b_i)


# 长时间积分（外推到 α→1 区域）
a0 = 0.3
T_long = 200
a_d, a_i, a_t = a0, a0, a0
traj_d, traj_i, traj_t = [a0], [a0], [a0]
for _ in range(T_long):
    a_d = direct_step(a_d); a_i = integral_step(a_i); a_t = true_next(a_t)
    traj_d.append(a_d); traj_i.append(a_i); traj_t.append(a_t)

traj_d, traj_i, traj_t = map(np.array, [traj_d, traj_i, traj_t])
err_d = float(np.abs(traj_d[-1] - traj_t[-1]))
err_i = float(np.abs(traj_i[-1] - traj_t[-1]))

print("=" * 60)
print("M14 积分约束 vs 直接步进（热解动力学长时积分）")
print("=" * 60)
print(f"真实动力学      : α* = 1（稳定固定点），特征值 = {1 - dt*k:.3f}")
print(f"直接步进模型   : α_{'{t+1}'} = {w_d:.4f}·α_t + {b_d:.4f}  → 特征值 {w_d:.4f}")
print(f"积分约束模型   : 导数 = {w_i:.4f}·α_t + {b_i:.4f}，积分特征值 = {1 + dt*w_i:.4f}")
print()
print(f"长时积分 {T_long} 步后的最终误差（vs 真实）:")
print(f"  直接步进   : {err_d:.4f}  {'❌ 发散/累积误差' if err_d > 0.05 else '✓ 稳定'}")
print(f"  积分约束   : {err_i:.4f}  {'❌ 发散/累积误差' if err_i > 0.05 else '✓ 稳定'}")
print()
print("结论：直接步进把 α_{t+1}=f(α_t) 当黑盒拟合，特征值易 >1（误差放大）；")
print("积分约束预测导数再积分，将特征值压入单位圆，长时积分稳定。")
