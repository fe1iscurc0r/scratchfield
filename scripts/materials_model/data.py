"""材料模型数据层：ELN 导出 → 特征矩阵 / 标签（W-01）。

定义 V-01 ELN 导出契约，并把 ELN 记录（碳化条件 × 原料特性 → 产物性质）
转成 scikit-learn 可消费的特征矩阵 X 与逐标签向量 y。

ELN 导出契约（V-01 产物约定，JSON 数组或 {"records": [...]} 或单条对象）：
  每条记录一个 dict，字段：
    元信息   date / topic / purpose / status（可选，训练不参与）
    特征     temperature(°C) / time(min) / heating_rate(°C/min) /
             koh_ratio(可选) / precursor(原料特性)
    标签     yield_rate(%) / surface_area(m²/g) / calorific_value(MJ/kg)

缺失处理：
  - 数值特征缺失 → 用该特征中位数填补，imputed 计数如实记录
  - precursor 缺失 → 归入 "unknown"
  - 标签缺失 → 保留 NaN，训练时逐标签丢弃缺失行

坏数据：非数值特征在 strict=True 时抛 DataError（含字段名与行号）；
strict=False 时按缺失处理（降级填补），保证管线不崩。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

# 数值特征（碳化条件 × 原料特性中的数值部分）
NUMERIC_FEATURES: tuple[str, ...] = ("temperature", "time", "heating_rate", "koh_ratio")
# 类别特征（原料特性）
CATEGORICAL_FEATURES: tuple[str, ...] = ("precursor",)
# 标签（产物性质）
TARGETS: tuple[str, ...] = ("yield_rate", "surface_area", "calorific_value")

_UNKNOWN_PRECURSOR = "unknown"

SAMPLE_LABEL = "样例数据（合成，非真实实验）"


class DataError(ValueError):
    """ELN 数据不合契约（坏数据 / 格式错误）。"""


def _num(value: Any, field: str, idx: int, *, strict: bool) -> float:
    """把单个字段值转 float；缺失→NaN，坏数据在 strict 下抛 DataError。"""
    if value is None or value == "":
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        if strict:
            raise DataError(f"第 {idx + 1} 条记录的字段 {field!r} 不是数值: {value!r}")
        return float("nan")


def _validate_records(data: Any, origin: str = "<records>") -> list[dict]:
    """把任意输入规范化为非空 dict 列表；坏结构抛 DataError。"""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise DataError(f"ELN 导出需为非空记录列表（{origin}）")
    for i, r in enumerate(data):
        if not isinstance(r, dict):
            raise DataError(f"ELN 导出第 {i + 1} 条不是对象: {type(r).__name__}（{origin}）")
    return data


def parse_eln_json(text: str, origin: str = "<json>") -> list[dict]:
    """把 JSON 文本解析为 ELN 记录列表（兼容数组 / {records:[...]} / 单对象）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DataError(f"ELN 导出 JSON 解析失败（{origin}）: {e}") from e
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    return _validate_records(data, origin)


def load_eln_records(source: Any) -> list[dict]:
    """从 ELN 导出加载记录。

    source 可为：
      - 文件路径（str/Path，.json 或已存在的文件）→ 读文件解析
      - JSON 文本（str，非路径）→ 直接解析
      - 记录列表 / 含 records 键的 dict / 单条记录 dict → 直接使用
    """
    if isinstance(source, os.PathLike):
        return parse_eln_json(Path(source).read_text(encoding="utf-8"), origin=str(source))
    if isinstance(source, list):
        return _validate_records(source)
    if isinstance(source, dict):
        return _validate_records(source.get("records", source))
    if isinstance(source, str):
        p = Path(source)
        if p.exists() or source.lower().rstrip().endswith(".json"):
            return parse_eln_json(p.read_text(encoding="utf-8"), origin=str(p))
        return parse_eln_json(source)
    raise DataError(f"无法识别的 ELN 导出类型: {type(source).__name__}")


def build_feature_matrix(records: Any, *, strict: bool = True) -> dict[str, Any]:
    """ELN 记录 → 特征矩阵 X + 逐标签向量 y（含缺失处理与 one-hot 前驱体）。

    Returns:
        dict: {
          "X":                  (n, n_features) 数值特征 + one-hot 前驱体
          "y":                  {target: (n,) 标签向量，缺失为 NaN}
          "feature_names":      [str] 与 X 列一一对应
          "target_names":       [str] 标签顺序
          "precursor_categories":[str] one-hot 类别（含 "unknown"）
          "numeric_medians":    {feature: median} 填补用中位数（供新输入编码复用）
          "imputed":            {feature: 填补条数}
          "n_samples":          int
        }
    """
    records = _validate_records(records)

    numeric_cols: dict[str, list[float]] = {f: [] for f in NUMERIC_FEATURES}
    categories: set[str] = set()
    target_cols: dict[str, list[float]] = {t: [] for t in TARGETS}

    for i, r in enumerate(records):
        for f in NUMERIC_FEATURES:
            numeric_cols[f].append(_num(r.get(f), f, i, strict=strict))
        categories.add(str(r.get("precursor") or _UNKNOWN_PRECURSOR))
        for t in TARGETS:
            target_cols[t].append(_num(r.get(t), t, i, strict=False))

    # 数值特征 → 中位数填补（含全缺失兜底 0）
    numeric_medians: dict[str, float] = {}
    imputed: dict[str, int] = {}
    x_parts: list[np.ndarray] = []
    feature_names: list[str] = list(NUMERIC_FEATURES)
    for f in NUMERIC_FEATURES:
        col = np.array(numeric_cols[f], dtype=float)
        nan_mask = np.isnan(col)
        imputed[f] = int(nan_mask.sum())
        valid = col[~nan_mask]
        median = float(np.median(valid)) if valid.size else 0.0
        if nan_mask.any():
            col = np.where(nan_mask, median, col)
        numeric_medians[f] = median
        x_parts.append(col)
    x_num = np.column_stack(x_parts) if x_parts else np.empty((len(records), 0))

    # 前驱体 one-hot（类别稳定排序，含 "unknown"）
    cat_list = sorted(categories)
    cat_index = {c: i for i, c in enumerate(cat_list)}
    onehot = np.zeros((len(records), len(cat_list)), dtype=float)
    for i, r in enumerate(records):
        c = str(r.get("precursor") or _UNKNOWN_PRECURSOR)
        onehot[i, cat_index[c]] = 1.0
    for c in cat_list:
        feature_names.append(f"precursor={c}")

    X = np.hstack([x_num, onehot]) if onehot.shape[1] else x_num
    y = {t: np.array(target_cols[t], dtype=float) for t in TARGETS}

    return {
        "X": X,
        "y": y,
        "feature_names": feature_names,
        "target_names": list(TARGETS),
        "precursor_categories": cat_list,
        "numeric_medians": numeric_medians,
        "imputed": imputed,
        "n_samples": len(records),
    }


def encode_input(features: dict[str, Any], meta: dict[str, Any]) -> np.ndarray:
    """把单条输入特征 dict 编码为与训练一致的特征向量（(1, n_features)）。

    未知前驱体类别不臆造 one-hot（该列全 0），缺失数值用训练中位数填补。
    """
    numeric = np.empty(len(NUMERIC_FEATURES), dtype=float)
    medians = meta.get("numeric_medians", {})
    for j, f in enumerate(NUMERIC_FEATURES):
        v = _num(features.get(f), f, 0, strict=False)
        numeric[j] = medians.get(f, 0.0) if np.isnan(v) else v

    cats = meta.get("precursor_categories", [])
    cat_index = {c: i for i, c in enumerate(cats)}
    onehot = np.zeros(len(cats), dtype=float)
    p = str(features.get("precursor") or _UNKNOWN_PRECURSOR)
    if p in cat_index:
        onehot[cat_index[p]] = 1.0

    return np.concatenate([numeric, onehot]).reshape(1, -1)
