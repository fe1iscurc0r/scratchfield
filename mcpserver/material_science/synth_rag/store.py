"""合成路线入库/更新/查询（I-02，SQLite 标准库）。

RouteStore 封装 sqlite3：add_route / update_route / get_route / list_routes / delete_route。
数据库默认 %APPDATA%/Lumo/synth_rag/routes.db（LUMO_SYNTHRAG_DB 可覆盖），测试可传临时路径
或 ":memory:"。只做旁路，不触碰 graphrag 主流程。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .schema import SCHEMA_SQL, Route


def default_db_path() -> str:
    """默认数据库路径（环境变量 LUMO_SYNTHRAG_DB 可覆盖）。"""
    override = os.environ.get("LUMO_SYNTHRAG_DB")
    if override:
        return override
    base = Path(os.environ.get("APPDATA", str(Path.home()))) / "Lumo" / "synth_rag"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "routes.db")


class RouteStore:
    """合成路线 SQLite 存储。连接由调用方关闭（close()），或作上下文管理器使用。"""

    def __init__(self, db_path: str | Path | None = None):
        # ":memory:" 表示测试用内存库；否则落盘
        self.db_path = str(db_path) if db_path is not None else default_db_path()
        self._memory = self.db_path == ":memory:"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def __enter__(self) -> "RouteStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # ---------- 写入 ----------

    def add_route(self, route: Route | dict[str, Any]) -> int:
        """入库一条路线，返回 route_id。非法输入抛 ValueError（坏输入用例覆盖）。"""
        r = route if isinstance(route, Route) else Route.from_dict(route)
        if not r.name or not r.name.strip():
            raise ValueError("路线名称 name 不能为空")
        if not r.product or not r.product.strip():
            raise ValueError("产物 product 不能为空")

        cur = self.conn.execute(
            "INSERT INTO routes (name, product, method, yield_min, yield_max, "
            "source, is_example, description) VALUES (?,?,?,?,?,?,?,?)",
            (r.name, r.product, r.method, r.yield_min, r.yield_max,
             r.source, int(bool(r.is_example)), r.description),
        )
        route_id = int(cur.lastrowid)
        for rx in r.reactants:
            self.conn.execute(
                "INSERT INTO reactants (route_id, name, amount, unit, role) "
                "VALUES (?,?,?,?,?)",
                (route_id, rx.name, rx.amount, rx.unit, rx.role))
        c = r.conditions
        self.conn.execute(
            "INSERT INTO conditions (route_id, temp_min_c, temp_max_c, pressure_bar, "
            "time_h, atmosphere) VALUES (?,?,?,?,?,?)",
            (route_id, c.temp_min_c, c.temp_max_c, c.pressure_bar, c.time_h, c.atmosphere))
        for p in r.properties:
            self.conn.execute(
                "INSERT INTO properties (route_id, name, value, unit) VALUES (?,?,?,?)",
                (route_id, p.name, p.value, p.unit))
        self.conn.commit()
        return route_id

    def update_route(self, route_id: int, fields: dict[str, Any]) -> bool:
        """按列更新 routes 主表字段（白名单列），子表改动请走 add/delete 重建。"""
        allowed = {"name", "product", "method", "yield_min", "yield_max",
                   "source", "is_example", "description"}
        cols = {k: v for k, v in fields.items() if k in allowed}
        if not cols:
            return False
        if "is_example" in cols:
            cols["is_example"] = int(bool(cols["is_example"]))
        set_clause = ", ".join(f"{k} = ?" for k in cols)
        cur = self.conn.execute(
            f"UPDATE routes SET {set_clause} WHERE id = ?",
            (*cols.values(), route_id))
        self.conn.commit()
        return cur.rowcount > 0

    def delete_route(self, route_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---------- 读取 ----------

    def get_route(self, route_id: int) -> Route | None:
        """按 id 取完整路线（含反应物/条件/物性）；不存在返回 None。"""
        row = self.conn.execute("SELECT * FROM routes WHERE id = ?", (route_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["is_example"] = bool(d["is_example"])
        d["reactants"] = [dict(r) for r in self.conn.execute(
            "SELECT name, amount, unit, role FROM reactants WHERE route_id = ?",
            (route_id,)).fetchall()]
        c = self.conn.execute(
            "SELECT temp_min_c, temp_max_c, pressure_bar, time_h, atmosphere "
            "FROM conditions WHERE route_id = ?", (route_id,)).fetchone()
        d["conditions"] = dict(c) if c else {}
        d["properties"] = [dict(p) for p in self.conn.execute(
            "SELECT name, value, unit FROM properties WHERE route_id = ?",
            (route_id,)).fetchall()]
        return Route.from_dict(d)

    def list_routes(self) -> list[Route]:
        """全部路线（按 id 升序），仅返回主表概要，子表按需 get_route 展开。"""
        rows = self.conn.execute("SELECT id FROM routes ORDER BY id").fetchall()
        return [self.get_route(r["id"]) for r in rows]  # type: ignore[misc]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM routes").fetchone()
        return int(row["n"])


def init_db(db_path: str | Path | None = None) -> RouteStore:
    """便捷入口：建库并返回 store（与 graphrag 的 default_graph_dir 风格对齐）。"""
    return RouteStore(db_path)
