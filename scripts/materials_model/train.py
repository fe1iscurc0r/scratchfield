"""材料模型训练：随机森林 + BP 基线（W-01）。

随机森林（RandomForestRegressor）为主模型，BP 网络（MLPRegressor）作基线对比。
train/test 切分后报告 R²/MAE/RMSE。

依赖策略：scikit-learn 可用时用其回归器；不可用时降级为 numpy 均值基线
（最朴素基线），并如实标注 degraded=True——保证「不引重依赖」也能跑通与出报告。
"""
from __future__ import annotations

import numpy as np

from scripts.materials_model.data import SAMPLE_LABEL, TARGETS, DataError

try:  # scikit-learn 可选：缺失时降级（不引重依赖的兜底路径）
    from sklearn.ensemble import RandomForestRegressor  # noqa: F401
    from sklearn.neural_network import MLPRegressor  # noqa: F401

    _SKLEARN = True
except ImportError:  # pragma: no cover - 依赖缺失时的降级分支
    _SKLEARN = False

SUPPORTED_MODELS = ("rf", "bp")


class _NumpyBaseline:
    """sklearn 缺失时的降级基线：预测训练集标签均值。"""

    def __init__(self) -> None:
        self.mean_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_NumpyBaseline":
        self.mean_ = float(np.nanmean(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self.mean_)


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _split(X: np.ndarray, y: np.ndarray, test_size: float, random_state: int):
    """train/test 切分（sklearn 可用则用，否则 numpy 确定性切分）。"""
    if _SKLEARN:
        from sklearn.model_selection import train_test_split

        return train_test_split(X, y, test_size=test_size, random_state=random_state)
    rng = np.random.RandomState(random_state)
    idx = rng.permutation(len(y))
    n_test = max(1, int(round(len(y) * test_size)))
    te, tr = idx[:n_test], idx[n_test:]
    return X[tr], X[te], y[tr], y[te]


def make_model(model_type: str = "rf", random_state: int = 42):
    """构造未训练的模型（rf / bp）。sklearn 缺失时返回 numpy 均值基线。"""
    if model_type not in SUPPORTED_MODELS:
        raise ValueError(f"model_type 应为 {SUPPORTED_MODELS} 之一（当前 {model_type!r}）")
    if not _SKLEARN:
        return _NumpyBaseline()
    if model_type == "rf":
        return RandomForestRegressor(n_estimators=100, random_state=random_state, n_jobs=-1)
    return MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=2000, random_state=random_state)


def train_and_report(
    X: np.ndarray,
    y: dict,
    target: str = "yield_rate",
    *,
    model_type: str = "rf",
    test_size: float = 0.2,
    random_state: int = 42,
    sample_data: bool = False,
) -> dict:
    """在单个标签上训练并报告 R²/MAE/RMSE。

    Args:
        X: 特征矩阵（build_feature_matrix 产物）
        y: 标签向量 dict（build_feature_matrix 产物）
        target: 标签名（TARGETS 之一）
        sample_data: 是否样例数据（影响 honest_label 诚实标注）
    """
    if target not in y:
        raise ValueError(f"未知标签 {target!r}，可用: {sorted(y)}")
    yv = np.asarray(y[target], dtype=float)
    mask = ~np.isnan(yv)
    if int(mask.sum()) < 2:
        raise DataError(f"标签 {target!r} 有效样本不足（<2），无法训练")
    X_ok, y_ok = X[mask], yv[mask]

    X_tr, X_te, y_tr, y_te = _split(X_ok, y_ok, test_size, random_state)
    model = make_model(model_type, random_state)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)

    return {
        "target": target,
        "model_type": model_type,
        "n_samples": int(len(y_ok)),
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "r2": round(_r2(y_te, pred), 4),
        "mae": round(_mae(y_te, pred), 4),
        "rmse": round(_rmse(y_te, pred), 4),
        "degraded": not _SKLEARN,
        "note": "sklearn 未安装，已降级为均值基线" if not _SKLEARN else "",
        "honest_label": SAMPLE_LABEL if sample_data else "真实数据",
        "model": model,
    }


def train_all_targets(X: np.ndarray, y: dict, *, model_type: str = "rf", sample_data: bool = False) -> dict:
    """在全部标签上训练，返回各标签报告 + 已拟合模型（供预测复用）。"""
    reports = {}
    models = {}
    for target in TARGETS:
        r = train_and_report(X, y, target, model_type=model_type, sample_data=sample_data)
        models[target] = r.pop("model")
        reports[target] = r
    return {
        "ok": True,
        "model_type": model_type,
        "honest_label": SAMPLE_LABEL if sample_data else "真实数据",
        "degraded": not _SKLEARN,
        "reports": reports,
        "models": models,
    }


def main(argv: list[str] | None = None) -> int:
    """训练报告 CLI：`python -m scripts.materials_model.train [--data ...] [--model rf|bp]`。"""
    import argparse
    import json

    from scripts.materials_model import data as _data
    from scripts.materials_model import sample_data as _sample

    parser = argparse.ArgumentParser(description="材料模型训练报告（随机森林 + BP 基线）")
    parser.add_argument("--data", default=str(_sample.DEFAULT_SAMPLE_PATH), help="ELN 导出 JSON 路径")
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default="rf", help="模型类型（rf/bp）")
    parser.add_argument("--sample", action="store_true", help="标记为样例数据（诚实标注）")
    args = parser.parse_args(argv)

    try:
        records = _data.load_eln_records(args.data)
    except DataError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    mat = _data.build_feature_matrix(records)
    result = train_all_targets(mat["X"], mat["y"], model_type=args.model, sample_data=args.sample)
    result["n_samples"] = mat["n_samples"]
    result["imputed"] = mat["imputed"]
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
