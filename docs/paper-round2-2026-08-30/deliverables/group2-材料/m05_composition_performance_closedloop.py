"""
M05 化学语言模型 + 不确定量化 → 组分-性能闭环
=================================================
组分直接预测性能（DOSSIER 类：无需晶体结构）+ EPhEct 物理一致性检验，
预测木质素/纤维素衍生物的离子电导，并给出不确定性驱动的采样闭环。

来源：digest-g4-4-2026-08-30.md 授粉点 2（源自 24513 组分直接预测电子态密度
+ 14153 EPhEct 电化学静电基准）。

验收：原型 + 物理合理性检验用例。

运行：python m05_composition_performance_closedloop.py
依赖：numpy, scikit-learn
"""
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.metrics import mean_squared_error

rng = np.random.default_rng(11)


def conductivity_true(X):
    """离子电导（S/cm 量级）：随磺酸基密度/介电常数上升；离子浓度过高时因
    离子对形成而回落（物理非单调）。"""
    lig, cell, so3, ion, eps = X.T
    base = 0.5 + 2.0 * so3 + 3.0 * (eps / 80.0) + 6.0 * ion / (1.0 + 2.0 * ion ** 2)
    return base + 0.3 * lig + 0.1 * cell


# 组分编码（化学语言模型风格：组分 token 直接嵌入为向量，无晶体结构）
# 特征：[木质素占比, 纤维素占比, 磺酸基密度, 离子浓度, 溶剂介电常数]
n = 400
X = rng.uniform([0, 0, 0, 0, 20], [1, 1, 1, 1, 100], size=(n, 5))
y = conductivity_true(X) + rng.normal(0, 0.08, size=n)

# 高斯过程 surrogate：自带不确定性
kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + ConstantKernel(0.05)
gp = GaussianProcessRegressor(kernel=kernel, alpha=1e-3, random_state=0)
gp.fit(X, y)
pred, std = gp.predict(X, return_std=True)
rmse = float(np.sqrt(mean_squared_error(y, pred)))

print("=" * 60)
print("M05 组分-性能闭环 + EPhEct 物理一致性检验")
print("=" * 60)
print(f"GP 模型 RMSE = {rmse:.3f} S/cm")

# ---- EPhEct 物理合理性检验用例 ----
# 物理约束 1：介电常数 ↑ → 电导 ↑（单调）
eps_grid = np.linspace(20, 100, 5)
x1 = np.tile([0.5, 0.5, 0.3, 0.5, 0.0], (5, 1))
x1[:, 4] = eps_grid
p1 = gp.predict(x1)
mono_eps = bool(np.all(np.diff(p1) > -1e-3))

# 物理约束 2：离子浓度 → 电导先升后降（离子对效应，非单调且非负）
ion_grid = np.linspace(0, 1, 21)
x2 = np.tile([0.5, 0.5, 0.3, 0.0, 80.0], (21, 1))
x2[:, 3] = ion_grid
p2 = gp.predict(x2)
has_peak = bool(np.argmax(p2) not in (0, len(p2) - 1))
nonneg = bool(np.all(p2 > 0))

print()
print("EPhEct 物理一致性检验:")
print(f"  ① 介电常数↑→电导↑（单调）      : {'通过' if mono_eps else '失败'}")
print(f"  ② 离子浓度→电导非单调有峰（离子对）: {'通过' if has_peak else '失败'}")
print(f"  ③ 电导始终非负                  : {'通过' if nonneg else '失败'}")
print(f"  物理合理性总评: {'通过' if (mono_eps and has_peak and nonneg) else '需修正'}")

# ---- 不确定性驱动的采样闭环：选预测方差最大的点做下一轮"实验" ----
pool = rng.uniform([0, 0, 0, 0, 20], [1, 1, 1, 1, 100], size=(2000, 5))
_, pool_std = gp.predict(pool, return_std=True)
next_exp = pool[int(np.argmax(pool_std))]
print()
print("闭环建议下一实验点（预测最不确定）:")
print(f"  木质素={next_exp[0]:.2f} 纤维素={next_exp[1]:.2f} 磺酸基={next_exp[2]:.2f} "
      f"离子浓度={next_exp[3]:.2f} 介电常数={next_exp[4]:.1f}")
