"""SQLite 实验库（靶子 A 数据存储，零第三方依赖）。

表 experiments：每行代表论文中一个实验参数组合。
字段与靶子 B（biopred）的数据集 schema 对齐，便于直接喂给预测模型。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paper         TEXT NOT NULL,              -- 论文来源（文件名/标题）
    source_path   TEXT,                       -- 原始 PDF/Markdown 路径
    precursor     TEXT,                       -- 前驱体（如 木质素/秸秆）
    crosslinker   TEXT,                       -- 交联剂（如 戊二醛）
    koh_ratio     REAL,                       -- KOH 活化比例
    heating_rate  REAL,                       -- 升温速率 (°C/min)
    carbonization_temp REAL,                  -- 碳化温度 (°C)
    holding_time  REAL,                       -- 保温时间 (min)
    conductivity  REAL,                       -- 导电率 (S/cm)
    surface_area  REAL,                       -- 比表面积 (m²/g)
    porosity      REAL,                       -- 孔隙率 (%)
    yield_rate    REAL,                       -- 产率 (%)
    raw_json      TEXT,                       -- 原始提取 JSON（保真）
    extracted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_experiments_paper ON experiments(paper);
CREATE INDEX IF NOT EXISTS idx_experiments_temp ON experiments(carbonization_temp);
"""


class ExperimentDB:
    """pgit 实验库封装。"""

    def __init__(self, db_path: str | Path = "papers.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def insert_experiment(self, exp: dict[str, Any]) -> int:
        """插入一条实验记录，返回 id。"""
        now = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO experiments
                (paper, source_path, precursor, crosslinker, koh_ratio,
                 heating_rate, carbonization_temp, holding_time,
                 conductivity, surface_area, porosity, yield_rate,
                 raw_json, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exp.get("paper", ""),
                exp.get("source_path"),
                exp.get("precursor"),
                exp.get("crosslinker"),
                _num(exp.get("koh_ratio")),
                _num(exp.get("heating_rate")),
                _num(exp.get("carbonization_temp")),
                _num(exp.get("holding_time")),
                _num(exp.get("conductivity")),
                _num(exp.get("surface_area")),
                _num(exp.get("porosity")),
                _num(exp.get("yield_rate")),
                json.dumps(exp, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def query_experiments(
        self,
        *,
        precursor: str | None = None,
        min_temp: float | None = None,
        min_conductivity: float | None = None,
        min_modulus: float | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """按条件过滤实验记录（供陆墨自然语言查询后端）。"""
        clauses: list[str] = []
        params: list[Any] = []
        if precursor:
            clauses.append("precursor LIKE ?")
            params.append(f"%{precursor}%")
        if min_temp is not None:
            clauses.append("carbonization_temp >= ?")
            params.append(min_temp)
        if min_conductivity is not None:
            clauses.append("conductivity >= ?")
            params.append(min_conductivity)
        if min_modulus is not None:
            clauses.append("COALESCE(conductivity,0) >= ?")  # modulus 暂以 conductivity 近似
            params.append(min_modulus * 0.1)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM experiments{where} ORDER BY extracted_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0])


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def init_db(db_path: str | Path = "papers.db") -> ExperimentDB:
    """打开（必要时创建）实验库。"""
    return ExperimentDB(db_path)