"""样例数据（W-01）：20~50 条合成碳化实验记录，明确标注「样例数据」。

数据是确定性合成的、物理上大致合理的关系（碳化温度/时间/升温速率/KOH 比例
→ 产率/比表面积/热值），用于跑通训练与预测管线。**非真实实验数据**，
所有产物均带 honest_label 标注，不得当作实测结果。

真实数据由用户提供后，用 data.load_eln_records 直接替换本样例即可。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from scripts.materials_model.data import SAMPLE_LABEL, load_eln_records

DEFAULT_SAMPLE_PATH = Path(__file__).resolve().parent / "sample_data" / "eln_export_samples.json"

_PRECURSORS = ("木质素", "秸秆", "稻壳", "纤维素")


def generate_sample_records(n: int = 30, seed: int = 42) -> list[dict[str, Any]]:
    """确定性生成 n 条合成碳化实验记录（含少量缺失，供缺失处理验证）。"""
    rng = np.random.RandomState(seed)
    records: list[dict[str, Any]] = []
    for i in range(n):
        precursor = _PRECURSORS[int(rng.randint(0, len(_PRECURSORS)))]
        temperature = float(rng.uniform(400.0, 900.0))
        time = float(rng.uniform(30.0, 180.0))
        heating_rate = float(rng.uniform(2.0, 20.0))
        koh_ratio = float(rng.uniform(0.0, 4.0))

        # 物理上大致合理：产率随温度升高略降、比表面随温度/KOH 升高、热值随碳化程度升高
        yield_rate = 62.0 - 0.02 * (temperature - 400.0) - 0.02 * (time - 60.0) + rng.normal(0, 1.5)
        surface_area = 150.0 + 0.75 * (temperature - 400.0) + 55.0 * koh_ratio + rng.normal(0, 30.0)
        calorific_value = 16.0 + 0.006 * (temperature - 400.0) - 0.008 * (time - 60.0) + rng.normal(0, 0.5)

        record: dict[str, Any] = {
            "date": "2026-08-20",
            "topic": "生物质碳化实验（样例）",
            "purpose": "碳化条件对产物性质的影响（样例数据）",
            "precursor": precursor,
            "temperature": round(temperature, 1),
            "time": round(time, 1),
            "heating_rate": round(heating_rate, 1),
            "koh_ratio": round(koh_ratio, 2),
            "yield_rate": round(max(0.0, yield_rate), 1),
            "surface_area": round(max(0.0, surface_area), 1),
            "calorific_value": round(calorific_value, 2),
        }
        # 制造少量缺失：每 8 条丢一次 koh_ratio（原料特性可选字段）；每 15 条丢一个标签
        if i % 8 == 3:
            record["koh_ratio"] = None
        if i % 15 == 7:
            record.pop("calorific_value", None)
        records.append(record)
    return records


def sample_payload(n: int = 30, seed: int = 42) -> dict[str, Any]:
    """返回带 _meta 的样例数据 payload（诚实标注「样例数据」）。"""
    return {
        "_meta": {
            "sample": True,
            "note": SAMPLE_LABEL,
            "generated_by": "scripts/materials_model/sample_data.py",
            "n": n,
            "seed": seed,
        },
        "records": generate_sample_records(n, seed),
    }


def write_sample_file(path: str | Path = DEFAULT_SAMPLE_PATH, n: int = 30, seed: int = 42) -> Path:
    """把样例数据写入 JSON 文件（含诚实标注），返回路径。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sample_payload(n, seed), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_sample_records(path: str | Path = DEFAULT_SAMPLE_PATH) -> list[dict[str, Any]]:
    """从样例数据 JSON 加载记录（load_eln_records 会自动剥离 _meta 取 records）。"""
    return load_eln_records(str(path))


def main(argv: list[str] | None = None) -> int:
    """生成样例数据文件 CLI：`python -m scripts.materials_model.sample_data`。"""
    import argparse

    parser = argparse.ArgumentParser(description="生成材料模型样例数据（明确标注「样例数据」）")
    parser.add_argument("--out", default=str(DEFAULT_SAMPLE_PATH), help="输出 JSON 路径")
    parser.add_argument("--n", type=int, default=30, help="记录条数（20~50）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args(argv)

    if not 20 <= args.n <= 50:
        parser.error("--n 应在 20~50 之间")
    out = write_sample_file(args.out, args.n, args.seed)
    print(f"已生成样例数据（{args.n} 条，标注「样例数据」）: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
