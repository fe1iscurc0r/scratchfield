"""eln_analysis.py — 符号回归 ELN 分析模块（K08）。

把 material_science/symbolic 的符号回归封装成 ELN（电子实验记录）可调用的分析
模块：输入实验数据 → 输出经验方程 + 不确定度。

- 方程：symbolic.fit 产出的显式表达式（text + latex）
- 拟合质量：R² / RMSE
- 不确定度：
  1) 预测不确定度 σ_res（残差标准差；±2σ 约 95% 预测带）
  2) 重启不确定度：n_restarts 次 GP 拟合的 rmse 分布（符号回归随机性）

用法：
    from mcpserver.material_science.symbolic.eln_analysis import analyze_experiment
    result = analyze_experiment("data.csv", target="y", n_restarts=3)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from mcpserver.material_science.symbolic.fit import fit


def _read_table(csv_path: str) -> tuple[list[str], list[list[float]]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"CSV 为空: {csv_path}")
    cols = list(rows[0].keys())
    data = [[float(r[c]) for c in cols] for r in rows]
    return cols, data


def analyze_experiment(
    csv_path: str,
    target: str,
    n_restarts: int = 3,
    population_size: int = 300,
    generations: int = 40,
    max_depth: int = 4,
) -> dict[str, Any]:
    """实验数据 → 经验方程 + 不确定度。

    Args:
        csv_path: 实验数据 CSV（首行表头，含 target 列）
        target: 目标列名（y）
        n_restarts: 重启次数（估计符号回归随机性）
    """
    cols, data = _read_table(csv_path)
    if target not in cols:
        return {"ok": False, "error": f"目标列 {target} 不在 {cols}"}
    feats = [c for c in cols if c != target]
    M = np.array(data, dtype=float)
    X = M[:, [cols.index(c) for c in feats]]
    y = M[:, cols.index(target)]

    best = None
    rmse_list: list[float] = []
    eq_list: list[str] = []
    for _ in range(n_restarts):
        res = fit(
            X, y, feature_names=feats,
            population_size=population_size, generations=generations,
            max_depth=max_depth,
        )
        rmse_list.append(res.rmse)
        eq_list.append(res.expression.text)
        if best is None or res.rmse < best.rmse:
            best = res

    residual_sigma = float(best.rmse)  # 残差标准差（预测不确定度）
    return {
        "ok": True,
        "target": target,
        "features": feats,
        "n_samples": int(len(y)),
        "equation": {"text": best.expression.text, "latex": best.expression.to_latex()},
        "fit": {"r2": round(float(best.r2), 6), "rmse": round(float(best.rmse), 6)},
        "uncertainty": {
            "residual_sigma": round(residual_sigma, 6),
            "prediction_band_95": [round(-2 * residual_sigma, 6), round(2 * residual_sigma, 6)],
            "restart_rmse": [round(r, 6) for r in rmse_list],
            "restart_rmse_std": round(float(np.std(rmse_list)), 6),
        },
        "restart_equations": eq_list,
    }


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="符号回归 ELN 分析")
    ap.add_argument("csv_path", help="实验数据 CSV")
    ap.add_argument("--target", default="y", help="目标列名（默认 y）")
    ap.add_argument("--n-restarts", type=int, default=3)
    args = ap.parse_args(argv)
    result = analyze_experiment(args.csv_path, args.target, n_restarts=args.n_restarts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
