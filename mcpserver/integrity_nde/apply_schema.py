"""幂等建表：`inspections`（工单 262 任务 B）。

只碰 `inspections` 一张表；`CREATE TABLE IF NOT EXISTS` 可反复执行。
验收（云服无 sqlite3 CLI，一律走 Python）：

    python3 mcpserver/integrity_nde/apply_schema.py --db /tmp/devices-probe.db
    python3 -c "import sqlite3;c=sqlite3.connect('/tmp/devices-probe.db');\
s=c.execute('select sql from sqlite_master where name=\"inspections\"').fetchone()[0];\
print(s);assert 'pod' in s and 'coverage' in s"
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

DDL = """
CREATE TABLE IF NOT EXISTS inspections (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id    TEXT NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('UT','RT','AE','EC','VT')),
  ts          TEXT NOT NULL,              -- ISO8601
  setup_ref   TEXT,                       -- 检验工艺/程序编号
  result      TEXT,                       -- pass / fail / marginal / inconclusive
  sizing      REAL,                       -- 缺陷尺寸 mm（RT/UT）
  pod         REAL,                       -- 检出概率
  coverage    REAL CHECK (coverage BETWEEN 0 AND 1),
  FOREIGN KEY (asset_id) REFERENCES assets(id)
);
CREATE INDEX IF NOT EXISTS idx_inspections_asset_ts ON inspections(asset_id, ts);
"""


def apply_schema(db_path: str) -> str:
    """建表并返回 inspections 的实际 DDL（用于验收断言）。"""
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(DDL)
        con.commit()
        row = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='inspections'"
        ).fetchone()
        if row is None:
            raise RuntimeError("inspections 建表失败：sqlite_master 里查不到")
        return row[0]
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="幂等建 inspections 表")
    ap.add_argument("--db", required=True, help="目标 sqlite 文件（不存在则创建）")
    args = ap.parse_args(argv)

    ddl = apply_schema(args.db)
    cols = [ln.strip() for ln in ddl.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    print(f"[apply_schema] {args.db}")
    print(f"[apply_schema] inspections 已就绪（{len(cols)} 行定义）")
    print(ddl)
    for required in ("asset_id", "method", "ts", "sizing", "pod", "coverage"):
        if required not in ddl:
            print(f"[apply_schema] 缺少必需列: {required}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
