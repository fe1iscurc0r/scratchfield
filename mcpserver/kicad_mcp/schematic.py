"""`.kicad_sch` 原理图读取（工单245）。

目标：给 agent 线一个**不看 KiCAD UI 也能读懂原理图**的结构化视图 ——
引用号/值/封装属性/网络标签/层次页 —— 因为「AI 辅助布局布线」的第一步
是知道**原理图声明了什么**，才能和 PCB 实际布局对账（见 `design_check.py`）。

口径
----
- 纯读取，不改写（写原理图会牵扯 UUID/实例路径，不在本 PoC 边界内）。
- 数值一律保留 KiCAD 原文（由 `sexpr.atom_float` 按需转）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .sexpr import SExpr

#: 放置的符号（`(symbol …)` 里带 `lib_id` 的那些）；`lib_symbols` 里的是**库定义**，不算放置
_PLACED_TAGS = ("symbol",)


@dataclass
class PlacedSymbol:
    """原理图上**放置**的一个符号（对应一个实物器件）。"""

    reference: str          # R1 / C3 / U2 …
    value: str
    lib_id: str             # 如 "Device:C"
    footprint: str          # 如 "Resistor_SMD:R_0805_2012Metric"，未指定时为空
    unit: int
    at: tuple[float, float, float] | None

    @property
    def has_footprint(self) -> bool:
        """是否已指定封装 —— 没指定的器件在 PCB 上根本不存在，是布局前的硬缺口。"""
        return bool(self.footprint.strip())

    def as_dict(self) -> dict:
        return {
            "reference": self.reference,
            "value": self.value,
            "lib_id": self.lib_id,
            "footprint": self.footprint,
            "unit": self.unit,
            "at": list(self.at) if self.at else None,
            "has_footprint": self.has_footprint,
        }


@dataclass
class Schematic:
    """解析后的原理图。"""

    path: str
    version: str = ""
    generator: str = ""
    paper: str = ""
    uuid: str = ""
    symbols: list[PlacedSymbol] = field(default_factory=list)
    lib_symbol_ids: list[str] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    sheets: list[dict] = field(default_factory=list)

    # ---------------------------------------------------------------- 构造
    @classmethod
    def parse(cls, path: str | Path) -> Schematic:
        p = Path(path)
        root = sexpr.parse_one(p.read_text(encoding="utf-8"))
        if sexpr.tag(root) != "kicad_sch":
            raise sexpr.SExprError(f"{p.name} 顶层不是 kicad_sch（实为 {sexpr.tag(root)!r}）")
        sch = cls(path=str(p))
        sch.version = sexpr.child_value(root, "version") or ""
        sch.generator = sexpr.child_value(root, "generator") or ""
        sch.paper = sexpr.child_value(root, "paper") or ""
        sch.uuid = sexpr.child_value(root, "uuid") or ""
        sch.symbols = _placed_symbols(root)
        sch.lib_symbol_ids = [
            v for v in (sexpr.atom(s[1]) for s in sexpr.find_all(sexpr.find_child(root, "lib_symbols"), "symbol")
                        if len(s) > 1)
            if v
        ] if sexpr.find_child(root, "lib_symbols") is not None else []
        sch.labels = _label_counts(root)
        sch.sheets = [_sheet_summary(s) for s in sexpr.find_all(root, "sheet")]
        return sch

    # ---------------------------------------------------------------- 查询
    def by_reference(self) -> dict[str, PlacedSymbol]:
        return {s.reference: s for s in self.symbols}

    def missing_footprints(self) -> list[PlacedSymbol]:
        """已指定封装为空的器件（PCB 上不会有它们）。"""
        return [s for s in self.symbols if not s.has_footprint]

    @property
    def references(self) -> set[str]:
        return {s.reference for s in self.symbols}

    def summary(self) -> dict:
        return {
            "path": self.path,
            "version": self.version,
            "generator": self.generator,
            "paper": self.paper,
            "symbol_count": len(self.symbols),
            "lib_symbol_count": len(self.lib_symbol_ids),
            "labels": dict(self.labels),
            "sheet_count": len(self.sheets),
            "missing_footprint_count": len(self.missing_footprints()),
            "missing_footprints": [s.reference for s in self.missing_footprints()],
        }


def _placed_symbols(root: SExpr) -> list[PlacedSymbol]:
    """收集放置的符号。

    ⚠️ 不能用 `find_all(root, "symbol")`：`lib_symbols` 下的**库定义**也长成 `(symbol "Device:C" …)`，
    和放置实例同 tag。区分点 = **放置实例带 `lib_id`**，库定义不带（实测自上游 canonical 夹具）。
    """
    out: list[PlacedSymbol] = []
    for node in sexpr.find_all(root, "symbol"):
        lib_id = sexpr.child_value(node, "lib_id")
        if not lib_id:                      # 库定义，跳过
            continue
        at_node = sexpr.find_child(node, "at")
        at = None
        if at_node and len(at_node) >= 3:
            vals = [sexpr.atom_float(x, 0.0) for x in at_node[1:4]]
            at = (vals[0] or 0.0, vals[1] or 0.0, vals[2] if len(vals) > 2 and vals[2] is not None else 0.0)
        out.append(PlacedSymbol(
            reference=sexpr.property_value(node, "Reference") or "?",
            value=sexpr.property_value(node, "Value") or "",
            lib_id=lib_id,
            footprint=sexpr.property_value(node, "Footprint") or "",
            unit=int(sexpr.child_value(node, "unit") or 1),
            at=at,
        ))
    return out


def _label_counts(root: SExpr) -> dict[str, int]:
    """各种标签数量（网络意图的信号）。"""
    out: dict[str, int] = {}
    for key in ("label", "global_label", "hierarchical_label", "netclass_flag", "no_connect"):
        n = len(sexpr.find_all(root, key))
        if n:
            out[key] = n
    if sexpr.find_all(root, "wire"):
        out["wire"] = len(sexpr.find_all(root, "wire"))
    return out


def _sheet_summary(node: SExpr) -> dict:
    """层次页摘要（`(sheet (property "Sheetname" …) (property "Sheetfile" …))`）。"""
    return {
        "name": sexpr.property_value(node, "Sheetname") or "",
        "file": sexpr.property_value(node, "Sheetfile") or "",
    }
