#!/usr/bin/env python3
"""I06 尾敏感条件独立检验（GFCM 风格 numpy 原型）。

参考 digest-g9 授粉点 ②（2608.15332v1 GFCM）：
- Neyman 正交化残差（OLS 去条件集 Z）
- 特征集 = centered moments + 条件分位数指示（尾特征）
- 广义特征协方差测度（GCM 模板）+ 置换检验 p 值

用于材料/生物数据的混合类型因果发现：X ⊥ Y | Z 的原假设检验。
`python scripts/gfcm_tail_test.py` 跑基准（null vs 尾依赖 alternative）。
"""
from __future__ import annotations

import numpy as np


def residualize(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """OLS 残差：去掉 Z 对 x 的线性影响（Neyman 正交化的一阶近似）。"""
    x = np.asarray(x, dtype=float).ravel()
    z = np.asarray(z, dtype=float)
    if z.ndim == 1:
        z = z.reshape(-1, 1)
    Z = np.column_stack([np.ones(len(x)), z])
    beta, *_ = np.linalg.lstsq(Z, x, rcond=None)
    return x - Z @ beta


def feature_map(x: np.ndarray) -> np.ndarray:
    """残差特征集：中心矩 + 分位数尾指示（尾敏感的关键）。"""
    x = np.asarray(x, dtype=float).ravel()
    xc = x - x.mean()
    q90, q10 = np.quantile(xc, 0.9), np.quantile(xc, 0.1)
    feats = np.column_stack([
        xc,                      # 均值（协方差）
        xc ** 2 - (xc ** 2).mean(),  # 尺度
        (xc > q90).astype(float),     # 上尾指示
        (xc < q10).astype(float),     # 下尾指示
    ])
    return feats


def gcm_stat(rx: np.ndarray, ry: np.ndarray) -> float:
    """广义特征协方差测度：残差 rx 与 ry 的广义特征间最大 |相关|。"""
    fx, fy = feature_map(rx), feature_map(ry)
    stat = 0.0
    for i in range(fx.shape[1]):
        for j in range(fy.shape[1]):
            corr = np.corrcoef(fx[:, i], fy[:, j])[0, 1]
            stat = max(stat, abs(corr))
    return float(stat)


def gfcm_test(x, y, z, n_perm: int = 200, seed: int = 0) -> dict:
    """X ⊥ Y | Z 的尾敏感条件独立检验。返回 {stat, p_value, n_perm}。"""
    rng = np.random.default_rng(seed)
    rx = residualize(np.asarray(x, dtype=float).ravel(), z)
    ry = residualize(np.asarray(y, dtype=float).ravel(), z)
    obs = gcm_stat(rx, ry)
    cnt = 0
    for _ in range(n_perm):
        rx_p = rng.permutation(rx)
        if gcm_stat(rx_p, ry) >= obs:
            cnt += 1
    return {"stat": round(obs, 4), "p_value": round((cnt + 1) / (n_perm + 1), 4), "n_perm": n_perm}


def benchmark() -> None:
    rng = np.random.default_rng(1)
    n = 400
    z = rng.normal(0, 1, n)

    # null：X、Y 独立给定 Z
    x_null = z + rng.normal(0, 1, n)
    y_null = z + rng.normal(0, 1, n)
    r_null = gfcm_test(x_null, y_null, z)
    print("null (X⊥Y|Z):", r_null)

    # alternative：尾依赖（Y 上尾由 X 上尾驱动）
    x_alt = z + rng.normal(0, 1, n)
    y_alt = z + rng.normal(0, 1, n) + 3.0 * (x_alt > np.quantile(x_alt, 0.9))
    r_alt = gfcm_test(x_alt, y_alt, z)
    print("tail-dependent alternative:", r_alt)


if __name__ == "__main__":
    benchmark()
