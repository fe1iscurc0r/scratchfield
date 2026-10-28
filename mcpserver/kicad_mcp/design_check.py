"""原理图 ↔ PCB 交叉对账（工单245）。

为什么这一步最值钱
------------------
「AI 辅助布局布线」的**前置条件**是知道两侧是否还对齐：原理图改了、PCB 没同步
（或反过来）时，任何自动布线/改板都是在**错误的前提**上做。KiCAD 自己的
"Update PCB from Schematic" 做的就是这个差集；本模块把它做成**可编程的只读检查**，
让 agent 在动手前先拿到差异清单。

本模块**只读**：不 Import、不 Netlist、不写文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board
from .schematic import Schematic


@dataclass
class CrossCheckResult:
    """对账结果。"""

    matched: list[str] = field(default_factory=list)
    only_in_schematic: list[str] = field(default_factory=list)
    only_on_board: list[str] = field(default_factory=list)
    value_mismatches: list[dict] = field(default_factory=list)
    footprint_mismatches: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """两侧完全对齐（引用号集合相同 + 无值/封装不一致）。"""
        return not (self.only_in_schematic or self.only_on_board
                    or self.value_mismatches or self.footprint_mismatches)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "matched_count": len(self.matched),
            "only_in_schematic": self.only_in_schematic,
            "only_on_board": self.only_on_board,
            "value_mismatches": self.value_mismatches,
            "footprint_mismatches": self.footprint_mismatches,
        }


def cross_check(sch: Schematic, pcb: Board, *, compare_lib_name_only: bool = True) -> CrossCheckResult:
    """对账原理图与 PCB 的器件。

    :param compare_lib_name_only: 封装名只比 ``Name`` 部分（``Lib:Name`` 的 ``Name``）。
        ⚠️ 默认 **True**：同一个库文件在不同机器/版本上库前缀会不同
        （``Capacitor_SMD:C_0603_1608Metric`` vs ``C_0603_1608Metric``），
        比全串会把「同一封装」误报成不一致。要严格比全串就显式传 False。
    """
    res = CrossCheckResult()
    sch_by_ref = sch.by_reference()
    pcb_by_ref = pcb.by_reference()

    res.only_in_schematic = sorted(set(sch_by_ref) - set(pcb_by_ref))
    res.only_on_board = sorted(set(pcb_by_ref) - set(sch_by_ref))
    res.matched = sorted(set(sch_by_ref) & set(pcb_by_ref))

    for ref in res.matched:
        s, b = sch_by_ref[ref], pcb_by_ref[ref]
        if s.value.strip() and b.value.strip() and s.value.strip() != b.value.strip():
            res.value_mismatches.append({"reference": ref, "schematic": s.value, "board": b.value})
        sf, bf = s.footprint.strip(), b.lib.strip()
        if sf and bf:
            left = sf.rsplit(":", 1)[-1] if compare_lib_name_only else sf
            right = bf.rsplit(":", 1)[-1] if compare_lib_name_only else bf
            if left != right:
                res.footprint_mismatches.append({"reference": ref, "schematic": sf, "board": bf})
    return res


def placement_report(pcb: Board) -> dict:
    """布局状况快照：谁还没摆（或摆在板框外）、谁在底层。"""
    size = pcb.board_size_mm()
    bbox = pcb.edge_bbox
    outside: list[str] = []
    on_back: list[str] = []
    if bbox and size:
        x0, y0, x1, y1 = bbox
        for f in pcb.footprints:
            if f.at and not (x0 <= f.at[0] <= x1 and y0 <= f.at[1] <= y1):
                outside.append(f.reference)
            if f.layer.startswith("B."):
                on_back.append(f.reference)
    unplaced = [f.reference for f in pcb.footprints if f.at is None]
    return {
        "footprint_count": len(pcb.footprints),
        "outside_board": sorted(outside),
        "on_back_layer": sorted(on_back),
        "unplaced": sorted(unplaced),
        "board_size_mm": list(size) if size else None,
    }
