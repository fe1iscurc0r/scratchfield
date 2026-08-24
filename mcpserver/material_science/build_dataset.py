"""构建靶子 B 的训练数据集：carbonization.db。

数据源：
- papers.db（靶子 A / paper_miner 的 experiments 表）—— 文献提取的碳化实验参数
- 可选 CSV —— 自己的实验记录（前驱体/KOH比/升温速率/碳化温度/保温时间 → 导电率/比表面积/孔隙率/产率）

输出：carbonization.db 的 experiments 表，schema 与 biopred._load_dataset 完全对齐
（碳化温度 + 导电率 均非空，作为训练特征/标签）。

用法：
    python -m mcpserver.material_science.build_dataset \
        --source papers.db --out carbonization.db [--csv my_records.csv] [--min-rows 50]

纯 stdlib（sqlite3 + csv），零第三方依赖。
"""
from __future__ import annotations

import argparse
import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paper         TEXT NOT NULL,
    source_path   TEXT,
    precursor     TEXT,
    crosslinker   TEXT,
    koh_ratio     REAL,
    heating_rate  REAL,
    carbonization_temp REAL NOT NULL,
    holding_time  REAL,
    conductivity  REAL NOT NULL,
    surface_area  REAL,
    porosity      REAL,
    yield_rate    REAL,
    raw_json      TEXT,
    extracted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_train_temp ON experiments(carbonization_temp);
"""

# 目标字段 → (papers.db 列, 类型转换)
_FIELDS = [
    ("paper", "paper", str),
    ("source_path", "source_path", str),
    ("precursor", "precursor", str),
    ("crosslinker", "crosslinker", str),
    ("koh_ratio", "koh_ratio", float),
    ("heating_rate", "heating_rate", float),
    ("carbonization_temp", "carbonization_temp", float),
    ("holding_time", "holding_time", float),
    ("conductivity", "conductivity", float),
    ("surface_area", "surface_area", float),
    ("porosity", "porosity", float),
    ("yield_rate", "yield_rate", float),
]


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_from_papers_db(source_db: str) -> list[dict[str, Any]]:
    """从 paper_miner 的 papers.db 读取含温度+导电率的实验记录。"""
    p = Path(source_db)
    if not p.is_file():
        raise FileNotFoundError(f"源数据库不存在: {source_db}")
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM experiments "
            "WHERE carbonization_temp IS NOT NULL AND conductivity IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _read_from_csv(csv_path: str) -> list[dict[str, Any]]:
    """读自己的实验记录 CSV。列名=目标字段名（小写、下划线）。"""
    p = Path(csv_path)
    if not p.is_file():
        raise FileNotFoundError(f"CSV 不存在: {csv_path}")
    records: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV 无表头: {csv_path}")
        for row in reader:
            # CSV 列名可能是目标字段名或 papers.db 列名，两者都尝试
            records.append({target: (row[target] if target in row else row.get(src))
                            for target, src, _conv in _FIELDS if target in row or src in row})
    return records


def _normalize(records: list[dict[str, Any]], tag: str) -> list[dict[str, Any]]:
    """字段名归一化 + 数值转换 + 过滤缺失温度/导电率。"""
    out: list[dict[str, Any]] = []
    for rec in records:
        r: dict[str, Any] = {}
        for target, src, conv in _FIELDS:
            raw = rec.get(src, rec.get(target))
            if conv is float:
                r[target] = _num(raw)
            else:
                r[target] = raw if raw not in (None, "") else None
        # 训练必需：温度与导电率非空
        if r.get("carbonization_temp") is None or r.get("conductivity") is None:
            continue
        # paper 可能已被置为 None（CSV 无此列），显式兜底为来源标签
        if not r.get("paper"):
            r["paper"] = tag
        out.append(r)
    return out


def _write(out_db: str, records: list[dict[str, Any]]) -> int:
    """写入 carbonization.db，schema 与 biopred._load_dataset 对齐。"""
    p = Path(out_db)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    try:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM experiments")  # 可重复构建
        cols = [t for t, _, _ in _FIELDS]
        ph = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO experiments ({', '.join(cols)}) VALUES ({ph})"
        for rec in records:
            conn.execute(sql, [rec.get(c) for c in cols])
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        return int(count)
    finally:
        conn.close()


def build_dataset(
    source_db: str = "papers.db",
    csv_path: str | None = None,
    out_db: str = "carbonization.db",
    min_rows: int = 50,
) -> dict[str, Any]:
    """构建训练集。返回统计摘要。"""
    records: list[dict[str, Any]] = []
    source_lines: list[str] = []
    try:
        lit = _read_from_papers_db(source_db)
        records.extend(_normalize(lit, "literature"))
        source_lines.append(f"papers.db: {len(lit)} 条（含温度+导电率）")
    except FileNotFoundError as e:
        source_lines.append(f"papers.db: 跳过（{e}）")
    if csv_path:
        try:
            own = _read_from_csv(csv_path)
            records.extend(_normalize(own, "own-record"))
            source_lines.append(f"CSV({csv_path}): {len(own)} 条")
        except FileNotFoundError as e:
            source_lines.append(f"CSV: 跳过（{e}）")

    valid = [r for r in records if r.get("carbonization_temp") is not None and r.get("conductivity") is not None]
    written = _write(out_db, valid) if valid else 0

    summary: dict[str, Any] = {
        "ok": True,
        "sources": source_lines,
        "valid_rows": len(valid),
        "written_to": out_db,
        "written_rows": written,
        "min_rows_required": min_rows,
        "ready_to_train": written >= min_rows,
    }
    if written < min_rows:
        summary["warning"] = (
            f"数据集 {written} 条 < 建议下限 {min_rows} 条。"
            "biopred_predict 在 <5 条时无法训练，suggest 在 <3 条时无法建议。"
            "请补充文献提取（靶子 A）或实验记录 CSV。"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="构建靶子 B 训练数据集 carbonization.db")
    parser.add_argument("--source", default="papers.db", help="paper_miner 源库（默认 papers.db）")
    parser.add_argument("--csv", default=None, help="自己的实验记录 CSV（可选）")
    parser.add_argument("--out", default="carbonization.db", help="输出库（默认 carbonization.db）")
    parser.add_argument("--min-rows", type=int, default=50, help="建议最少行数（默认 50）")
    args = parser.parse_args()

    summary = build_dataset(
        source_db=args.source, csv_path=args.csv, out_db=args.out, min_rows=args.min_rows
    )
    for line in summary["sources"]:
        print(line)
    print(f"有效实验记录: {summary['valid_rows']} 条")
    print(f"写入 {summary['written_rows']} 条 → {summary['written_to']}")
    print(f"达到训练下限: {summary['ready_to_train']}")
    if summary.get("warning"):
        print(f"⚠ {summary['warning']}")
    return 0 if summary["written_rows"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())