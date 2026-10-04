"""材料模型推理 CLI（W-01）。

用法示例（验收）：
    python scripts/materials_model/predict.py --temp 600 --time 120

默认在样例数据上训练随机森林并输出结构化预测（含不确定区间）；可用
--data 指向真实 ELN 导出。预测结果可 --write-back 回写 ELN，--suggest 用
Ollama 生成实验建议（可选，失败降级）。

输出为 JSON，结构：
    {ok, input, predictions[{target,value,unit,interval}], model, honest_label}
结果均为「预测值」，honest_label 如实标注「样例数据」或「真实数据」。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 直接 `python scripts/materials_model/predict.py` 运行时，把仓库根加入 sys.path，
# 使 `scripts.materials_model` 可被绝对导入；pytest（cwd=仓库根）下为无副作用重复插入。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from scripts.materials_model import data as _data
from scripts.materials_model import sample_data as _sample
from scripts.materials_model import train as _train
from scripts.materials_model import writeback as _writeback

TARGET_UNITS = _writeback.TARGET_UNITS


def _rf_interval(model: Any, x_row: np.ndarray) -> dict[str, Any] | None:
    """随机森林：用各决策树的预测分布取 10%~90% 分位作为不确定区间。"""
    if hasattr(model, "estimators_"):
        preds = np.array([float(est.predict(x_row)[0]) for est in model.estimators_])
        lo, hi = np.percentile(preds, [10.0, 90.0])
        return {"low": round(float(lo), 3), "high": round(float(hi), 3), "method": "forest-10-90"}
    return None  # BP / numpy 基线不提供区间估计


def predict(
    inputs: dict[str, Any],
    *,
    data_path: str | None = None,
    model_type: str = "rf",
    sample_data: bool | None = None,
) -> dict[str, Any]:
    """训练（默认样例数据）→ 单点预测 → 结构化结果（含不确定区间）。

    Args:
        inputs: 特征 dict（temperature/time/heating_rate/precursor/koh_ratio）
        data_path: ELN 导出路径；None 用内置样例数据
        model_type: rf / bp
        sample_data: 是否样例数据；None 时按 data_path 是否为默认样例推断
    """
    data_path = data_path or str(_sample.DEFAULT_SAMPLE_PATH)
    if sample_data is None:
        sample_data = Path(data_path).resolve() == Path(_sample.DEFAULT_SAMPLE_PATH).resolve()

    records = _data.load_eln_records(data_path)
    mat = _data.build_feature_matrix(records)

    result = _train.train_all_targets(mat["X"], mat["y"], model_type=model_type, sample_data=sample_data)
    x_row = _data.encode_input(inputs, mat)

    predictions = []
    for target in _data.TARGETS:
        model = result["models"][target]
        value = float(model.predict(x_row)[0])
        interval = _rf_interval(model, x_row)
        predictions.append(
            {
                "target": target,
                "label": _writeback.TARGET_LABELS.get(target, target),
                "value": round(value, 3),
                "unit": TARGET_UNITS.get(target, ""),
                "interval": interval,
                "kind": "预测值",
            }
        )

    return {
        "ok": True,
        "input": inputs,
        "predictions": predictions,
        "model": model_type,
        "n_train_samples": mat["n_samples"],
        "honest_label": result["honest_label"],
        "degraded": result["degraded"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生物质碳化产物性质预测（材料模型 W-01）")
    parser.add_argument("--temp", "--temperature", dest="temperature", type=float, default=None, help="碳化温度 °C")
    parser.add_argument("--time", dest="time", type=float, default=None, help="保温时间 min")
    parser.add_argument("--rate", "--heating-rate", dest="heating_rate", type=float, default=None, help="升温速率 °C/min")
    parser.add_argument("--precursor", default=None, help="原料特性（如 木质素/秸秆/稻壳/纤维素）")
    parser.add_argument("--koh-ratio", dest="koh_ratio", type=float, default=None, help="KOH 活化比例")
    parser.add_argument("--data", default=None, help="ELN 导出 JSON 路径（默认内置样例数据）")
    parser.add_argument("--model", choices=_train.SUPPORTED_MODELS, default="rf", help="模型类型（rf/bp）")
    parser.add_argument("--write-back", dest="write_back", default=None, help="回写 ELN 的输出目录")
    parser.add_argument("--suggest", action="store_true", help="用 Ollama 生成实验建议（可选）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.temperature is None or args.time is None:
        print(
            json.dumps(
                {"ok": False, "error": "必须提供 --temp 与 --time（如 --temp 600 --time 120）"},
                ensure_ascii=False,
            )
        )
        return 2

    inputs = {
        "temperature": args.temperature,
        "time": args.time,
        "heating_rate": args.heating_rate,
        "precursor": args.precursor,
        "koh_ratio": args.koh_ratio,
    }
    try:
        result = predict(inputs, data_path=args.data, model_type=args.model)
    except _data.DataError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2

    if args.write_back:
        try:
            result["eln_path"] = _writeback.write_eln_record(result, args.write_back)
        except Exception as e:  # noqa: BLE001 - 回写失败不阻断预测输出
            result["eln_path"] = None
            result["write_back_error"] = f"{type(e).__name__}: {e}"

    if args.suggest:
        from scripts.materials_model import suggest as _suggest

        result["suggestion"] = _suggest.suggest_experiment(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
