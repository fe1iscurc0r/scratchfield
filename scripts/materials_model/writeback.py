"""预测结果回写 ELN（W-01 · V-01 格式）。

把材料模型预测结果按 V-01 ELN 记录约定（Obsidian frontmatter + Markdown 正文）
生成一条记录：目的=模型预测，条件=输入特征，结果=预测值，并标注「模型预测待验证」。
结果字段明确标注「预测值」，绝不与实测数据混用。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

# 预测值后缀：结果字段明确标注「预测值」
_PREDICT_SUFFIX = "（预测值）"
_VERIFY_TAG = "模型预测待验证"

# 结果单位（与 data.TARGETS 顺序一致）
TARGET_UNITS = {
    "yield_rate": "%",
    "surface_area": "m²/g",
    "calorific_value": "MJ/kg",
}

TARGET_LABELS = {
    "yield_rate": "产率",
    "surface_area": "比表面积",
    "calorific_value": "热值",
}


def _yaml_scalar(value: Any) -> str:
    """把值序列化为单行 YAML 标量（frontmatter 用，最小实现不依赖 pyyaml）。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_yaml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_yaml_scalar(v)}" for k, v in value.items()) + "}"
    s = str(value)
    # 含特殊字符时加引号，避免破坏 frontmatter 解析
    if any(ch in s for ch in (":", "#", "[", "]", "{", "}", "\n", "'", '"')):
        return "'" + s.replace("'", "''") + "'"
    return s


def build_eln_record(prediction_result: dict[str, Any]) -> dict[str, Any]:
    """把 predict 结果组装为 V-01 ELN 记录 dict。

    prediction_result 需含 input（特征）与 predictions（逐标签预测）字段。
    """
    inputs = prediction_result.get("input", {})
    predictions = prediction_result.get("predictions", [])

    conditions = {
        "temperature": inputs.get("temperature"),
        "time": inputs.get("time"),
        "heating_rate": inputs.get("heating_rate"),
        "koh_ratio": inputs.get("koh_ratio"),
    }
    conditions = {k: v for k, v in conditions.items() if v is not None}

    results = {}
    for p in predictions:
        target = p.get("target", "")
        results[target] = p.get("value")

    frontmatter = {
        "date": date.today().isoformat(),
        "topic": "材料模型预测",
        "purpose": "模型预测",
        "status": _VERIFY_TAG,
        "precursor": inputs.get("precursor"),
        "conditions": conditions,
        "results": {f"{k}{_PREDICT_SUFFIX}": v for k, v in results.items()},
        "model": prediction_result.get("model"),
        "honest_label": prediction_result.get("honest_label", ""),
        "linked_experiments": prediction_result.get("linked_experiments", []),
    }

    return {"frontmatter": frontmatter, "title": "# 材料模型预测（待验证）"}


def render_eln_markdown(record: dict[str, Any]) -> str:
    """把 ELN 记录 dict 渲染为 Obsidian 兼容的 Markdown（frontmatter + 正文）。"""
    fm = record.get("frontmatter", {})
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {_yaml_scalar(v)}")
    lines.append("---")
    lines.append("")
    lines.append(record.get("title", "# 材料模型预测（待验证）"))
    lines.append("")
    lines.append(
        f"> ⚠️ 本记录由材料模型生成，结果字段均为**预测值**，标注「{_VERIFY_TAG}」。"
        "未经验证不得与实测数据混用。"
    )
    lines.append("")
    lines.append("## 输入条件")
    lines.append("")
    conditions = fm.get("conditions") or {}
    for k, v in conditions.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## 预测结果")
    lines.append("")
    results = fm.get("results") or {}
    for k, v in results.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_eln_record(prediction_result: dict[str, Any], out_dir: str | Path) -> str:
    """把预测结果回写为 .md 文件，返回写入路径（文件名含日期与模型名）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = build_eln_record(prediction_result)
    model = prediction_result.get("model", "rf")
    stamp = date.today().isoformat()
    path = out_dir / f"模型预测_{model}_{stamp}.md"
    path.write_text(render_eln_markdown(record), encoding="utf-8")
    return str(path)
