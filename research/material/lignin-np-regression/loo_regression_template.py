#!/usr/bin/env python3
"""小数据 LOO 回归模板（n ≤ 50）—— 木质素纳米粒子性能预测最小可用版。

来源：工单 206 任务三（2610.07547 的 37 样本 LOO R²=0.77 方法论）。
用法（本科生照单操作，详见同目录 README.md）：

    # 常规：CSV 路径，特征列在前、最后一列是目标
    python loo_regression_template.py data.csv

    # 自测：合成数据验证管线
    python loo_regression_template.py --selftest

输出：LOO R²（集成 + 各模型）+ 各特征重要性。
依赖：numpy + scikit-learn（刻意不引重型框架）。
"""
from __future__ import annotations

import argparse
import csv
import sys

try:
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge, RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
except ImportError as e:  # pragma: no cover
    print(f"缺依赖: {e}\n安装: pip install numpy scikit-learn")
    raise SystemExit(2) from e


def build_models() -> dict[str, object]:
    """集成成员：全部是简单、小数据友好的模型（2610.07547 的核心思路）。"""
    return {
        "Ridge": make_pipeline(StandardScaler(), RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])),
        "SVR": make_pipeline(StandardScaler(), SVR(kernel="rbf", C=10.0, epsilon=0.1)),
        "RandomForest": RandomForestRegressor(n_estimators=300, max_depth=4, random_state=7,
                                              min_samples_leaf=2),
    }


def loo_r2(model_factory: dict[str, object], X: np.ndarray, y: np.ndarray) -> tuple[float, dict[str, float]]:
    """Leave-one-out：每个点轮流当测试集，其余训练；返回集成与各模型的 R²。"""
    n = len(y)
    preds = {name: np.zeros(n) for name in model_factory}
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        Xtr, ytr = X[mask], y[mask]
        for name, proto in model_factory.items():
            from sklearn.base import clone

            m = clone(proto)
            m.fit(Xtr, ytr)
            preds[name][i] = m.predict(X[i:i + 1])[0]

    def r2(p: np.ndarray) -> float:
        ss_res = float(np.sum((y - p) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    per_model = {name: r2(p) for name, p in preds.items()}
    ensemble_p = np.mean(np.stack(list(preds.values())), axis=0)
    return r2(ensemble_p), per_model


def feature_importance(model_factory: dict[str, object], X: np.ndarray, y: np.ndarray,
                       names: list[str]) -> dict[str, float]:
    """Ridge |coef| 与 RF importance 归一后取均值（两个视角更稳）。"""
    from sklearn.base import clone

    ridge = clone(model_factory["Ridge"]).fit(X, y)
    rf = clone(model_factory["RandomForest"]).fit(X, y)
    w1 = np.abs(ridge[-1].coef_)
    w1 = w1 / w1.sum() if w1.sum() > 0 else w1
    w2 = rf.feature_importances_
    w2 = w2 / w2.sum() if w2.sum() > 0 else w2
    w = (w1 + w2) / 2.0
    return {n: round(float(v), 3) for n, v in sorted(zip(names, w), key=lambda t: -t[1])}


def load_csv(path: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    if len(rows) < 3:
        raise SystemExit(f"数据行太少（{len(rows) - 1} 行，至少需要 3）")
    header = [h.strip() for h in rows[0]]
    data, dropped = [], 0
    for r in rows[1:]:
        try:
            vals = [float(c) for c in r[: len(header)]]
        except ValueError:
            dropped += 1
            continue
        if any(v != v for v in vals):  # NaN 检查（NA 已在 float() 处被剔除，这里兜底）
            dropped += 1
            continue
        data.append(vals)
    if dropped:
        print(f"（剔除 {dropped} 行含非数值/缺失的数据）")
    arr = np.array(data)
    if arr.shape[1] < 2:
        raise SystemExit("至少需要 1 个特征列 + 1 个目标列")
    return arr[:, :-1], arr[:, -1], header[:-1]


def run(X: np.ndarray, y: np.ndarray, names: list[str], quiet: bool = False) -> float:
    models = build_models()
    ens, per = loo_r2(models, X, y)
    imp = feature_importance(models, X, y, names)
    if not quiet:
        print(f"样本 n={len(y)}  特征 k={X.shape[1]}")
        print(f"LOO R²(Ensemble) = {ens:.3f}")
        for name, r in sorted(per.items(), key=lambda t: -t[1]):
            print(f"  {name:<14} R²={r:.3f}")
        print("特征重要性（Ridge+RF 均值）:")
        for n, v in imp.items():
            print(f"  {n:<28} {v:.3f}")
    return ens


def selftest() -> int:
    """合成数据（真实系数 + 噪声）验证管线。"""
    rng = np.random.default_rng(7)
    n = 30
    X = rng.uniform(0.5, 5.0, size=(n, 3))
    y = (2.0 * X[:, 0] - 1.2 * X[:, 1] + 0.8 * X[:, 2]
         + rng.normal(0, 0.3, n))  # 信噪比明确
    print("== 自测：合成数据（y = 2.0*x0 - 1.2*x1 + 0.8*x2 + 噪声）==")
    ens = run(X, y, ["lignin_conc", "sonication_min", "temp_c"])
    print(f"\n自测判定：LOO R² = {ens:.3f}（合成信号明确，应 > 0.6）")
    ok = ens > 0.6
    print("自测:", "✓ PASS" if ok else "✗ FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="小数据 LOO 回归模板（木质素 NPs 性能预测）")
    ap.add_argument("csv", nargs="?", help="CSV 路径（特征列在前，最后一列 = 目标）")
    ap.add_argument("--selftest", action="store_true", help="合成数据自测")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.csv:
        ap.print_help()
        return 2
    X, y, names = load_csv(args.csv)
    run(X, y, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
