"""
M01 物理引导符号回归（RUPF）→ 生物质热稳定性
=================================================
用 RUPF 风格几何描述符（刚性单元堆积分数 φ、网络刚度 κ）替代组分比例，
物理引导符号回归 + 不确定性量化，预测纤维素/木质素混合物热解温度。

修复：改用 Lasso（L1 稀疏）做符号选择 + 对选中项 OLS 去偏，避免无正则线性
回归导致的过拟合（此前 log 项系数爆炸到 ±1000）。

来源：digest-g4-2-2026-08-30.md 授粉点 1（源自 2608.14853：物理引导符号回归
推导碱硼酸盐玻璃 Tg 可解释闭式表达式，RUPF 优于传统 APF）。

验收：numpy/sklearn 原型 + RMSE 对比简单组分模型 + 结构敏感区标注。

运行：python m01_rupf_symbolic_regression.py
依赖：numpy, scikit-learn
"""
import numpy as np
from sklearn.linear_model import LassoCV, LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

rng = np.random.default_rng(42)

# ---- 1. 合成数据：三组分（纤维素/木质素/半纤维素）质量分数 ----
n = 300
comp = rng.dirichlet(np.ones(3), size=n)
cell, lig, hemi = comp.T

# ---- 2. RUPF 风格几何描述符（物理量，非组分比例） ----
phi = 0.45 * cell + 0.30 * hemi + 0.20 * lig          # 刚性单元堆积分数
kappa = 1.0 * lig + 0.4 * cell + 0.2 * hemi           # 网络刚度

T_true = 240.0 + 120.0 * phi + 60.0 * (kappa ** 2) - 40.0 * phi * kappa
T = T_true + rng.normal(0, 6.0, size=n)

FEAT_NAMES = ["phi", "kappa", "phi^2", "kappa^2", "phi*kappa",
              "log1p(phi)", "log1p(kappa)"]


def feats(X):
    phi, kappa = X[:, 0], X[:, 1]
    return np.column_stack([phi, kappa, phi ** 2, kappa ** 2, phi * kappa,
                            np.log1p(phi), np.log1p(kappa)])


def select_terms(X, y):
    """Lasso 稀疏选择符号项（稀疏性即"物理约束/简约性"）。"""
    F = feats(X)
    scaler = StandardScaler().fit(F)
    lasso = LassoCV(cv=5, random_state=0, max_iter=200000).fit(scaler.transform(F), y)
    idx = np.where(np.abs(lasso.coef_) > 1e-6)[0]
    return idx, scaler


def fit_on_selected(X, y, idx):
    """对 Lasso 选中的项做 OLS（原始空间），得到可解释系数。"""
    return LinearRegression().fit(feats(X)[:, idx], y)


def cv_rmse(X, y, k=5):
    kf = KFold(k, shuffle=True, random_state=0)
    errs = []
    for tr, te in kf.split(X):
        idx, _ = select_terms(X[tr], y[tr])
        m = fit_on_selected(X[tr], y[tr], idx)
        errs.append(mean_squared_error(y[te], m.predict(feats(X[te])[:, idx])))
    return float(np.sqrt(np.mean(errs)))


def cv_rmse_comp(comp, y, k=5):
    kf = KFold(k, shuffle=True, random_state=0)
    errs = []
    for tr, te in kf.split(comp):
        m = LinearRegression().fit(comp[tr], y[tr])
        errs.append(mean_squared_error(y[te], m.predict(comp[te])))
    return float(np.sqrt(np.mean(errs)))


X_rupf = np.column_stack([phi, kappa])
rmse_rupf = cv_rmse(X_rupf, T)
rmse_comp = cv_rmse_comp(comp, T)

# 最终模型（全数据）+ bootstrap 不确定性
idx, _ = select_terms(X_rupf, T)
m_final = fit_on_selected(X_rupf, T, idx)
F_sel = feats(X_rupf)[:, idx]

preds = []
for _ in range(200):
    b = rng.choice(n, n, replace=True)
    mb = fit_on_selected(X_rupf[b], T[b], idx)
    preds.append(mb.predict(F_sel))
pred_std = np.array(preds).std(0)
sens = int(np.argmax(pred_std))

print("=" * 60)
print("M01 RUPF 符号回归 vs 简单组分模型")
print("=" * 60)
print(f"RUPF 符号模型 CV RMSE : {rmse_rupf:.2f} K")
print(f"简单组分模型 CV RMSE : {rmse_comp:.2f} K")
print(f"误差降低             : {(1 - rmse_rupf / rmse_comp) * 100:.1f}%")
print()
print("Lasso 选中的可解释项（OLS 系数，原始空间）:")
for jj, j in enumerate(idx):
    print(f"  {FEAT_NAMES[j]:>10s} : {m_final.coef_[jj]:+8.3f}")
print(f"  {'截距':>10s} : {m_final.intercept_:+8.2f}")
print()
print(f"结构敏感区样本 #{sens}:")
print(f"  phi={phi[sens]:.3f}  kappa={kappa[sens]:.3f}  预测标准差={pred_std[sens]:.2f} K")
print("  → 预测方差最大的区域，建议优先补充实验。")
