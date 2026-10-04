"""
M03 主动学习 + MLIP → 电化学性能预测
=========================================
SMBO + 高斯过程 surrogate 迭代选实验点，预测木质素/纤维素衍生物的电化学性能
（电荷存储容量）。目标：4 次主动学习迭代内预测误差减半。

修复：surrogate 由随机森林（树间方差作不确定性，噪声大、收敛慢）改为高斯过程
（predictive variance 是可靠的不确定性），从而真正实现"4 次迭代误差减半"。
（digest 授粉点原文为"SMBO+随机森林 surrogate"；此处用 GP 作为更稳健的 SMBO
surrogate，方法框架一致。）

来源：digest-g4-1-2026-08-30.md 授粉点 2（源自 17742 SMBO 4 次迭代误差减半
+ 14153 EPhEct 基准）。

验收：原型 + 迭代误差曲线。

运行：python m03_active_learning_mlip.py
依赖：numpy, scikit-learn
"""
import warnings

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.metrics import mean_squared_error

warnings.filterwarnings("ignore")   # GP 超参边界 warning，与结果无关

rng = np.random.default_rng(7)


def ground_truth(X):
    """真实电化学性能：电荷存储容量。"""
    ph, ionic, cross, ratio = X.T
    return (80.0 + 12.0 * ratio - 8.0 * (ph - 7) ** 2
            + 15.0 * np.log1p(ionic) - 6.0 * cross
            + 4.0 * ratio * ph - 5.0 * cross ** 2)


bounds = np.array([[3, 12], [0, 1.0], [0.1, 1.0], [0.0, 1.0]])

n_pool = 2000
X_pool = rng.uniform(bounds[:, 0], bounds[:, 1], size=(n_pool, 4))
y_pool = ground_truth(X_pool) + rng.normal(0, 2.0, size=n_pool)

n_test = 500
X_test = rng.uniform(bounds[:, 0], bounds[:, 1], size=(n_test, 4))
y_test = ground_truth(X_test) + rng.normal(0, 2.0, size=n_test)

kernel = (ConstantKernel(1.0) * RBF(length_scale=[1.0, 1.0, 1.0, 1.0],
                                     length_scale_bounds=(1e-2, 1e2))
          + WhiteKernel(noise_level=4.0, noise_level_bounds=(1e-2, 1e2)))
gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=0)

n_init = 20
idx_init = rng.choice(n_pool, n_init, replace=False)
X_cur, y_cur = X_pool[idx_init], y_pool[idx_init]
rest = np.setdiff1d(np.arange(n_pool), idx_init)


def rmse(model, X, y):
    return float(np.sqrt(mean_squared_error(y, model.predict(X))))


gp.fit(X_cur, y_cur)
history = [rmse(gp, X_test, y_test)]
print("=" * 60)
print("M03 主动学习闭环（SMBO + 高斯过程 surrogate）")
print("=" * 60)
print(f"初始 (n={n_init:>3d}) RMSE = {history[0]:.2f}")

N_ITER = 4
for it in range(N_ITER):
    _, std = gp.predict(X_pool[rest], return_std=True)   # 采集函数 = 预测方差
    k = 10
    top = rest[np.argsort(std)[::-1][:k]]
    X_cur = np.vstack([X_cur, X_pool[top]])
    y_cur = np.hstack([y_cur, y_pool[top]])
    rest = np.setdiff1d(rest, top)
    gp.fit(X_cur, y_cur)
    history.append(rmse(gp, X_test, y_test))
    print(f"迭代 {it + 1} (n={len(X_cur):>3d}) RMSE = {history[-1]:.2f}")

print()
print("迭代误差曲线 (RMSE):")
print("  " + " -> ".join(f"{h:.2f}" for h in history))
target = history[0] / 2
print(f"误差减半目标: 初始 {history[0]:.2f} -> 目标 {target:.2f}")
print(f"实际: {history[-1]:.2f}  达成: {'是' if history[-1] <= target else '否'}")
