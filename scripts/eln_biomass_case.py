#!/usr/bin/env python3
"""K08 生物质数据案例：符号回归 → 经验方程 + 不确定度。

合成生物质热稳定性数据（M01 场景：char yield % ≈ f(木质素含量, 热解温度/100)），
用 ELN 分析模块拟合并输出经验方程 + 不确定度。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from mcpserver.material_science.symbolic.eln_analysis import analyze_experiment

rng = np.random.default_rng(42)
n = 60
lignin = rng.uniform(0.1, 0.5, n)        # 木质素含量（质量分数）
temp = rng.uniform(4.0, 8.0, n)          # 热解温度 / 100 ℃
# 真实规律：y = 12*lignin + 0.6*temp^2 - 5 + 噪声（char yield %）
y = 12.0 * lignin + 0.6 * temp**2 - 5.0 + rng.normal(0, 0.5, n)

csv_path = Path("docs/paper-round2-2026-08-30/eln-biomass-case.csv")
with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["lignin", "temp", "char_yield"])
    for a, b, c in zip(lignin, temp, y):
        w.writerow([round(a, 4), round(b, 4), round(c, 4)])

result = analyze_experiment(str(csv_path), target="char_yield", n_restarts=3)
print("=== K08 生物质案例结果 ===")
print("方程(text) :", result["equation"]["text"])
print("方程(latex):", result["equation"]["latex"])
print("R²         :", result["fit"]["r2"], " RMSE:", result["fit"]["rmse"])
print("残差 σ     :", result["uncertainty"]["residual_sigma"],
      " 95% 预测带:", result["uncertainty"]["prediction_band_95"])
print("重启 RMSE  :", result["uncertainty"]["restart_rmse"],
      " std:", result["uncertainty"]["restart_rmse_std"])
print("重启方程   :", result["restart_equations"])
