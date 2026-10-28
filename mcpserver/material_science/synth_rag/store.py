"""合成路线入库/更新/查询（I-02，SQLite 标准库）。

RouteStore 封装 sqlite3：add_route / update_route / get_route / list_routes / delete_route。
数据库默认 %APPDATA%/Lumo/synth_rag/routes.db（LUMO_SYNTHRAG_DB 可覆盖），测试可传临时路径
或 ":memory:"。只做旁路，不触碰 graphrag 主流程。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .schema import SCHEMA_SQL, InspirationItem, Route


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


# ---------- 灵感素材库（工单 237 任务一：索引层，非工单库） ----------

# 语料落点（工单 237 §3）：物料已由 PR #326 落入本仓，随 synth_rag 包一起分发
INSPIRATION_POOL_ROOT = Path(__file__).resolve().parent / "corpus" / "inspiration_pool_2026-10-11"

# theme → 语料子目录（目录名沿用素材源，不统一改名）
THEME_DIRS: dict[str, str] = {
    "biomass": "biomass_synth_rag_corpus",
    "sdr": "sdr_rag_test_corpus",
    "agent": "agent_inspiration_doc",
    "esp32": "esp32_inspiration_doc",
    "other": "other_inspiration_doc",
}


def inspiration_theme_path(theme: str, root: str | Path | None = None) -> Path:
    """返回某主题的语料目录（内含 index.json）。未知主题抛 KeyError。"""
    base = Path(root) if root is not None else INSPIRATION_POOL_ROOT
    if theme not in THEME_DIRS:
        raise KeyError(f"未知主题 {theme!r}，可选：{sorted(THEME_DIRS)}")
    return base / THEME_DIRS[theme]


def load_inspiration_pool(corpus_path: str | Path) -> list[InspirationItem]:
    """加载一个主题的灵感素材池（读 ``<corpus_path>/index.json``）。

    - 入参可为目录（自动拼 ``index.json``）或 ``index.json`` 路径本身
    - 校验 ``meta.count == len(items)``（工单 237 §0 实测定为不变量）与 pid 唯一性
    - 校验失败抛 ``ValueError``；索引文件缺失抛 ``FileNotFoundError``
    - 纯标准库（json），不引向量 DB、不触碰 graphrag 主流程（旁路硬约束）
    """
    p = Path(corpus_path)
    index_file = p if p.suffix == ".json" else p / "index.json"
    if not index_file.is_file():
        raise FileNotFoundError(f"灵感素材库索引不存在: {index_file}")

    with index_file.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"索引格式非法（应为 JSON 对象）: {index_file}")

    meta = data.get("meta") or {}
    theme = str(meta.get("theme") or "").strip()
    items_raw = data.get("items")
    if not isinstance(items_raw, list):
        raise ValueError(f"items 字段应为列表: {index_file}")

    declared = meta.get("count")
    if declared is not None and int(declared) != len(items_raw):
        raise ValueError(
            f"meta.count({declared}) 与 items 实际条数({len(items_raw)}) 不一致: {index_file}")

    items: list[InspirationItem] = []
    seen: set[str] = set()
    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {idx} 条 item 非对象: {index_file}")
        item = InspirationItem.from_dict(raw, theme=theme)
        if not item.pid:
            raise ValueError(f"第 {idx} 条缺 pid: {index_file}")
        if item.pid in seen:
            raise ValueError(f"pid 重复: {item.pid!r}（第 {idx} 条）: {index_file}")
        seen.add(item.pid)
        items.append(item)
    return items
