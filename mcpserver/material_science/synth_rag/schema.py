"""合成路线结构化 schema（PIRAG SSKB 范式落地，I-02）。

只做旁路：SQLite 表结构定义 + 路线实体 dataclass，纯标准库 sqlite3，不引向量 DB，
不触碰 graphrag 主流程。字段维度对齐 SSKB：反应物 / 产物 / 条件 / 产率 / 物性 / 溯源。

数据来源诚实标注：内置示例路线 is_example=1，source 标注「示例数据·待真机采集」；
真实合成路线数据留真机导入，本模块不伪造。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# 路线实体：条件拆成数值区间，便于范围过滤与物理校验（而非自由文本）
@dataclass
class Conditions:
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    pressure_bar: float | None = None
    time_h: float | None = None
    atmosphere: str = ""


@dataclass
class Reactant:
    name: str
    amount: float | None = None
    unit: str = ""
    role: str = ""


@dataclass
class Property:
    name: str
    value: float | None = None
    unit: str = ""


@dataclass
class Route:
    """一条合成路线（SSKB 主实体）。"""
    name: str
    product: str
    method: str = ""
    yield_min: float | None = None
    yield_max: float | None = None
    source: str = ""
    is_example: bool = False
    description: str = ""
    reactants: list[Reactant] = field(default_factory=list)
    conditions: Conditions = field(default_factory=Conditions)
    properties: list[Property] = field(default_factory=list)
    id: int | None = None

    def __post_init__(self) -> None:
        """宽容归一化：reactants/conditions/properties 接受 dict 或 dataclass 两种入参。"""
        self.reactants = [
            r if isinstance(r, Reactant) else Reactant(**(r or {}))
            for r in (self.reactants or [])
        ]
        if not isinstance(self.conditions, Conditions):
            self.conditions = Conditions(**(self.conditions or {}))
        self.properties = [
            p if isinstance(p, Property) else Property(**(p or {}))
            for p in (self.properties or [])
        ]

    def to_dict(self) -> dict[str, Any]:
        """转为扁平 dict（store 层入库用）。"""
        d = asdict(self)
        # 移除 id（新增时由 store 生成），保留布尔 → 0/1
        if d.get("id") is None:
            d.pop("id", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Route":
        """从 dict 还原（store 层出库用），对缺省/未知字段宽容。"""
        d = dict(d)
        reactants = [Reactant(**(r or {})) for r in d.pop("reactants", []) or []]
        cond = Conditions(**(d.pop("conditions", {}) or {}))
        props = [Property(**(p or {})) for p in d.pop("properties", []) or []]
        route = cls(**d)
        route.reactants = reactants
        route.conditions = cond
        route.properties = props
        return route


@dataclass
class InspirationItem:
    """灵感素材条目（工单 237，索引层）。

    来源：`research/inspiration_pool_rag/2026-10-11` 的 RESCORE-V3 高分入选集
    （composite ≥ 70），落点 `corpus/inspiration_pool_2026-10-11/<theme>/index.json`。
    meta.note 明确标注「灵感素材 - 非工单库」。

    ⚠️ 诚实标注（工单 237 §1/§6）：`target` 句是 GLM **从 abstract 联想**出来的应用
    场景，**不是论文真实研究方向**（biomass 前 5 篇实测 4/5 不符）。本类只做索引承载，
    检索给候选、agent 拿 abstract 自查，**不做真伪判定**（留工单 238）。
    """
    pid: str
    target: str = ""
    abstract: str = ""
    arxiv_url: str = ""
    composite: float = 0.0
    match: str = ""
    theme: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any], theme: str = "") -> "InspirationItem":
        """从 index.json 的一条 item 还原；theme 缺省时回填传入值。"""
        return cls(
            pid=str(d.get("pid") or ""),
            target=str(d.get("target") or ""),
            abstract=str(d.get("abstract") or ""),
            arxiv_url=str(d.get("arxiv_url") or ""),
            composite=float(d.get("composite") or 0.0),
            match=str(d.get("match") or ""),
            theme=theme or str(d.get("theme") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# SQLite DDL：外键 ON DELETE CASCADE，删除路线时子表联动清空
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS routes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    product     TEXT NOT NULL,
    method      TEXT DEFAULT '',
    yield_min   REAL,
    yield_max   REAL,
    source      TEXT DEFAULT '',
    is_example  INTEGER DEFAULT 0,
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reactants (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    amount   REAL,
    unit     TEXT DEFAULT '',
    role     TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS conditions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id    INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    temp_min_c  REAL,
    temp_max_c  REAL,
    pressure_bar REAL,
    time_h      REAL,
    atmosphere  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS properties (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    value    REAL,
    unit     TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_reactants_route ON reactants(route_id);
CREATE INDEX IF NOT EXISTS idx_conditions_route ON conditions(route_id);
CREATE INDEX IF NOT EXISTS idx_properties_route ON properties(route_id);
"""
