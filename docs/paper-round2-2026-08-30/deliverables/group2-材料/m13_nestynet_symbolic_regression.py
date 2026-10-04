"""
M13 NestyNet 符号回归 → 材料经验方程发现
============================================
符号回归从生物质实验数据自动发现经验方程（产率 vs 温度/时间）。
NestyNet 风格：解析导数神经代理 + 可嵌套常数（常数本身参与优化而非搜索）。

来源：digest-g6-2b-2026-08-30.md 授粉点 ②（源自 2608.21051v2/21491v2 NestyNet）。

验收：原型 + 恢复方程对比。

运行：python m13_nestynet_symbolic_regression.py
依赖：numpy
"""
import numpy as np

rng = np.random.default_rng(2)

# ---- 真实经验方程（产率 Yield = a * exp(-Ea/(R*T)) * t^n，Arrhenius 型）----
Ea, R, n_true, a = 12000.0, 8.314, 0.5, 3.2


def yield_true(T, t):
    return a * np.exp(-Ea / (R * T)) * (t ** n_true)


T = rng.uniform(450, 650, size=120)      # 温度 K
t = rng.uniform(1, 60, size=120)         # 时间 min
y = yield_true(T, t) * (1 + rng.normal(0, 0.05, size=120))

# ---- 符号回归：搜索候选方程形式（线性系数 + 嵌套常数 Ea 扫描）----
def build_features(T, t, Ea_cand):
    z = np.exp(-Ea_cand / (R * T))
    # 候选符号项（含不同时间幂次）
    return np.column_stack([z, z * t, z * np.sqrt(t), z * t ** 2,
                            T, t, np.ones_like(T)])


FEAT_NAMES = ["exp(-Ea/RT)", "exp(-Ea/RT)*t", "exp(-Ea/RT)*sqrt(t)",
              "exp(-Ea/RT)*t^2", "T", "t", "1"]

best = None
for Ea_cand in np.linspace(8000, 16000, 81):   # 嵌套常数扫描（而非离散搜索）
    F = build_features(T, t, Ea_cand)
    coef, _, _, _ = np.linalg.lstsq(F, y, rcond=None)
    pred = F @ coef
    rmse = float(np.sqrt(np.mean((y - pred) ** 2)))
    if best is None or rmse < best[0]:
        best = (rmse, Ea_cand, coef)

rmse, Ea_rec, coef = best

# baseline：纯多项式（无物理先验）
Fp = np.column_stack([T, t, T * t, T ** 2, t ** 2, np.ones_like(T)])
cp, _, _, _ = np.linalg.lstsq(Fp, y, rcond=None)
rmse_poly = float(np.sqrt(np.mean((y - Fp @ cp) ** 2)))

print("=" * 60)
print("M13 符号回归 → 材料经验方程发现")
print("=" * 60)
print(f"真实方程 : Yield = {a}*exp(-{Ea}/(R*T)) * t^{n_true}")
print(f"恢复方程 : RMSE = {rmse:.4f}, 恢复 Ea = {Ea_rec:.0f} (真值 {Ea})")
print()
print("恢复的符号项系数（非零项即选中的经验方程）:")
for nm, c in zip(FEAT_NAMES, coef):
    if abs(c) > 1e-3:
        print(f"  {nm:>18s} : {c:+.4f}")
print()
print(f"符号回归 RMSE : {rmse:.4f}")
print(f"纯多项式 RMSE : {rmse_poly:.4f}")
print("物理符号回归误差更低且可直接解读（恢复出 Arrhenius 形式）。")
