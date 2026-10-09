#!/usr/bin/env python3
"""本科实验数据快通道 · CSV 入库脚本（工单213 任务二）。

用法：
    python quick_import.py lignin_np_2026-10.csv            # 按文件名前缀识别表类型
    python quick_import.py data.csv --table lignin_np       # 显式指定表类型
    python quick_import.py data.csv --demo                   # 用内置合成示例跑一遍

行为：
  1. 校验列名（对照 data_schema.md 的表定义；缺列/多列给出警告，必填列缺失则拒绝该行）
  2. 数值校验（数值列必须可转 float；NA 允许）
  3. 写 SQLite（research/material/bachelor-lab/lab_data.db，幂等：同 sample_id+date 覆盖）
  4. 追加 JSONL（同目录 records.jsonl，完整保留原始行）
  5. 生成"回归就绪"CSV（features_<table>.csv：数值特征 + 分类哑变量 + 目标列，
     缺失任一必填数值的行剔除）——直接喂 ../lignin-np-regression/loo_regression_template.py

依赖：纯 stdlib（csv/sqlite3/json/argparse）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "lab_data.db"
JSONL = HERE / "records.jsonl"

# 表定义：列名 → (中文含义, 是否数值, 是否必填)
TABLES: dict[str, dict[str, tuple[str, bool, bool]]] = {
    "lignin_np": {
        "sample_id": ("样品编号", False, True),
        "date": ("实验日期", False, True),
        "operator": ("实验员", False, True),
        "lignin_type": ("木质素类型", False, True),
        "lignin_conc_mg_ml": ("木质素浓度 mg/mL", True, True),
        "solvent_ratio": ("溶剂比", True, True),
        "temp_c": ("沉淀温度 °C", True, True),
        "sonication_min": ("超声时间 min", True, False),
        "stir_rpm": ("搅拌 rpm", True, False),
        "notes": ("备注", False, False),
        "diameter_nm": ("粒径 nm", True, True),
        "pdi": ("PDI", True, True),
        "zeta_mv": ("Zeta mV", True, False),
    },
    "hydrogel": {
        "sample_id": ("样品编号", False, True),
        "date": ("实验日期", False, True),
        "operator": ("实验员", False, True),
        "np_loading_wt": ("NPs 掺量 wt%", True, True),
        "crosslinker_wt": ("交联剂 wt%", True, True),
        "swelling_ratio": ("溶胀率", True, True),
        "compressive_modulus_kpa": ("压缩模量 kPa", True, True),
        "water_content_pct": ("含水率 %", True, False),
    },
    "deep_eutectic": {
        "sample_id": ("样品编号", False, True),
        "date": ("实验日期", False, True),
        "operator": ("实验员", False, True),
        "hba": ("氢键受体", False, True),
        "hbd": ("氢键供体", False, True),
        "molar_ratio": ("摩尔比", True, True),
        "t_peak_c": ("相变温度 °C", True, True),
        "dh_j_g": ("相变焓 J/g", True, True),
        "cp_j_gk": ("热容 J/(g·K)", True, False),
    },
}

# 回归目标列（生成 features CSV 时放最后）
TARGETS = {
    "lignin_np": ["diameter_nm", "pdi", "zeta_mv"],
    "hydrogel": ["swelling_ratio", "compressive_modulus_kpa"],
    "deep_eutectic": ["t_peak_c", "dh_j_g"],
}


def is_na(v: str) -> bool:
    return v.strip().upper() in ("NA", "N/A", "")


def ensure_db(conn: sqlite3.Connection, table: str, cols: dict[str, tuple[str, bool, bool]]) -> None:
    """幂等建表（所有列 TEXT 存原值，校验在导入层做——保持 schema 与 CSV 对齐简单）。"""
    defs = ["rowid_pk INTEGER PRIMARY KEY AUTOINCREMENT"]
    for c in cols:
        defs.append(f'"{c}" TEXT')
    defs.append("_imported_at TEXT")
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(defs)})')


def import_csv(path: str, table: str, target: str | None = None) -> int:
    cols = TABLES[table]
    src = Path(path)
    if not src.exists():
        raise SystemExit(f"文件不存在: {src}")
    with src.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if not rows:
        raise SystemExit("CSV 无数据行")

    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in cols if c not in header]
    extra = [h for h in header if h not in cols]
    if missing:
        print(f"⚠️ 缺列 {len(missing)}: {missing}（对应数据将记 NA）")
    if extra:
        print(f"⚠️ 多余列 {len(extra)}: {extra}（仍会入库，但不参与校验）")

    today = date.today().isoformat()
    ok_rows: list[dict] = []
    n_bad = 0
    for i, r in enumerate(rows, 2):  # 2 = 数据起始行号（含表头）
        rec = {c: (r.get(c, "") or "").strip() for c in cols}
        errs = []
        for c, (_desc, is_num, required) in cols.items():
            v = rec[c]
            if required and is_na(v):
                errs.append(f"{c} 必填但为空")
            elif is_num and not is_na(v):
                try:
                    float(v)
                except ValueError:
                    errs.append(f"{c}={v!r} 不是数值")
        if rec.get("date") and not is_na(rec["date"]):
            try:
                date.fromisoformat(rec["date"])
            except ValueError:
                errs.append(f"date={rec['date']!r} 应为 YYYY-MM-DD")
        if errs:
            n_bad += 1
            print(f"  ⚠ 第 {i} 行拒绝: {'; '.join(errs[:3])}")
            continue
        rec["_imported_at"] = today
        ok_rows.append(rec)

    conn = sqlite3.connect(DB)
    ensure_db(conn, table, cols)
    # 幂等：同 sample_id+date 先删后插
    cur = conn.cursor()
    for rec in ok_rows:
        cur.execute(f'SELECT rowid_pk FROM "{table}" WHERE sample_id=? AND date=?',
                    (rec.get("sample_id"), rec.get("date")))
        old = cur.fetchone()
        keys = [c for c in cols] + ["_imported_at"]
        vals = [rec.get(c) for c in keys]
        if old:
            cur.execute(f'DELETE FROM "{table}" WHERE rowid_pk=?', (old[0],))
        ph = ",".join("?" * len(keys))
        q = ",".join(f'"{k}"' for k in keys)
        cur.execute(f'INSERT INTO "{table}" ({q}) VALUES ({ph})', vals)
    conn.commit()

    with JSONL.open("a", encoding="utf-8") as fh:
        for rec in ok_rows:
            fh.write(json.dumps({"table": table, **rec}, ensure_ascii=False) + "\n")

    print(f"\n入库: {len(ok_rows)} 行 → {DB.name}（表 {table}）+ {JSONL.name}；拒绝 {n_bad} 行")
    write_features_csv(conn, table, target)
    conn.close()
    return len(ok_rows)


def write_features_csv(conn: sqlite3.Connection, table: str, target: str | None) -> None:
    """导出「回归就绪」CSV：数值特征 + 分类哑变量，最后一个目标列。"""
    cols = TABLES[table]
    targets = [target] if target else TARGETS[table]
    t = next((x for x in targets if x in cols), None)
    if t is None:
        print("（无可导出的目标列，跳过 features CSV）")
        return
    num_feats = [c for c, (_d, is_num, _r) in cols.items()
                 if is_num and c != t and c not in ("stir_rpm",)]  # stir_rpm 等可留
    num_feats = [c for c in num_feats if c != t]
    cat_cols = [c for c, (_d, is_num, _r) in cols.items()
                if not is_num and c not in ("sample_id", "date", "operator", "notes")]

    rows = conn.execute(
        f'SELECT {", ".join(chr(34)+c+chr(34) for c in set(num_feats + cat_cols + [t]))} FROM "{table}"'
    ).fetchall()
    sel = num_feats + cat_cols + [t]
    q = f'SELECT {", ".join(chr(34)+c+chr(34) for c in sel)} FROM "{table}"'
    cur = conn.execute(q)
    colnames = [d[0] for d in cur.description]   # 列名与行来自同一查询，杜绝错位
    rows = [dict(zip(colnames, r)) for r in cur.fetchall()]

    # 分类哑变量
    cat_vals: dict[str, list[str]] = {}
    for c in cat_cols:
        vs = sorted({str(r[c]) for r in rows if r[c]})
        cat_vals[c] = vs[:-1] or vs  # k-1 哑变量（单值时保留 1 个）
    out_cols = num_feats + [f"{c}_{v}" for c in cat_cols for v in cat_vals[c]] + [t]
    out_rows = []
    dropped = 0
    def cell(v) -> float | None:
        """None/空/NA → None；可转 float → float；否则抛 ValueError（该行剔除）。"""
        if v is None:
            return None
        s = str(v).strip()
        if s.upper() in ("NA", "N/A", ""):
            return None
        return float(s)  # 不合法值抛 ValueError，由调用行剔除

    for r in rows:
        try:
            vals = [cell(r[c]) for c in num_feats]
        except (TypeError, ValueError):
            dropped += 1
            continue
        if any(v is None for v in vals):
            dropped += 1
            continue
        tgt = cell(r[t])
        if tgt is None:
            dropped += 1
            continue
        for c in cat_cols:
            for v in cat_vals[c]:
                vals.append(1.0 if str(r[c]) == v else 0.0)
        vals.append(tgt)
        out_rows.append(vals)

    out = HERE / f"features_{table}.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(out_cols)
        w.writerows(out_rows)
    print(f"回归就绪 CSV: {out.name}（{len(out_rows)} 行 × {len(out_cols)} 列，目标={t}；剔除 {dropped} 行含缺失）")
    print(f"  下一步: python ../lignin-np-regression/loo_regression_template.py {out.name}")


DEMO_CSV = """sample_id,date,operator,lignin_type,lignin_conc_mg_ml,solvent_ratio,temp_c,sonication_min,stir_rpm,notes,diameter_nm,pdi,zeta_mv
LN-001,2026-10-01,张三,alkali,1.0,3.0,25,10,600,pH=9,182,0.21,-31
LN-002,2026-10-01,张三,alkali,2.0,3.0,25,10,600,pH=9,146,0.18,-33
LN-003,2026-10-02,张三,alkali,3.0,3.0,25,10,600,pH=9,121,0.16,-36
LN-004,2026-10-02,李四,organosolv,1.0,4.0,40,20,800,,205,0.27,-24
LN-005,2026-10-03,李四,organosolv,2.0,4.0,40,20,800,,163,0.22,-27
LN-006,2026-10-03,李四,organosolv,3.0,4.0,40,20,800,,134,0.19,-29
LN-007,2026-10-04,张三,kraft,1.5,3.5,30,15,700,,158,0.20,-30
LN-008,2026-10-04,张三,kraft,2.5,3.5,30,15,700,,129,0.17,-34
LN-009,2026-10-05,张三,alkali,2.0,5.0,25,30,600,超声加长,112,0.14,-38
LN-010,2026-10-05,张三,alkali,2.0,2.0,25,5,600,溶剂比降,171,0.24,-28
LN-011,2026-10-06,李四,alkali,NA,3.0,25,10,600,浓度漏记,150,0.19,-32
LN-012,2026-10-06,李四,alkali,2.0,3.0,25,10,600,粒径非数值,abc,0.18,-33
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="本科实验数据入库（工单213 快通道）")
    ap.add_argument("csv", nargs="?", help="CSV 文件路径")
    ap.add_argument("--table", choices=sorted(TABLES), help="表类型（默认按文件名前缀猜）")
    ap.add_argument("--target", help="回归目标列（默认按表定义依次导出）")
    ap.add_argument("--demo", action="store_true", help="用内置合成示例跑一遍（自动清理）")
    args = ap.parse_args()

    if args.demo:
        demo = HERE / "_demo_input.csv"
        demo.write_text(DEMO_CSV, encoding="utf-8")
        try:
            n = import_csv(str(demo), "lignin_np", args.target)
            return 0 if n > 0 else 1
        finally:
            demo.unlink(missing_ok=True)
    if not args.csv:
        ap.print_help()
        return 2
    table = args.table
    if not table:
        stem = Path(args.csv).stem.lower()
        for t in TABLES:
            if stem.startswith(t) or t in stem:
                table = t
                break
    if not table:
        raise SystemExit(f"无法从文件名猜表类型，请 --table 指定（可选：{sorted(TABLES)}）")
    import_csv(args.csv, table, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
