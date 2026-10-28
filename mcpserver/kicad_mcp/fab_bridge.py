"""嘉立创（JLCPCB）制造前预检（工单245）。

工单 §0 的原话是「KiCAD PCB 设计 MCP（**与 Lumo 嘉立创 EDA AI 试验直接相关**）」——
上游那条产品线里最贴本仓的正是它的 **JLCPCB 元件库/工艺整合**（`src/tools/jlcpcb-api.ts`、
根目录 `download_jlcpcb.py`）。本模块把其中**不需要联网、不需要 KiCAD** 的那一半做实：
**从板子自身推出工艺下限，再和一套工艺能力阈值比对**，产出「这块板能不能直接下单」的报告。

⚠️ 阈值的出处（**必须如实**）
----------------------------
下面的预设值是**保守的经验值**（PoC 用），**不是**从嘉立创官方规格页抓取的数值。
理由：官方能力随**层数/铜厚/表面处理/期**变化，硬编码一份「官方数字」等于伪造权威。
因此本模块把阈值做成**显式可覆盖的 ruleset**，并在报告里回传 `ruleset_source`，
让使用者一眼看出「这是本仓预设，不是官方规格」。要对接真实能力，请用
:func:`RuleSet.from_dict` 注入当期货期参数。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .board import Board

#: 预设的出处说明（会原样回传给调用方，防止被误当成官方规格）
DEFAULT_RULESET_SOURCE = (
    "本仓保守预设（PoC 用），非嘉立创官方规格抓取；官方能力随 层数/铜厚/表面处理/期 变化，"
    "下单前请以当期货期页为准，或用 RuleSet.from_dict 注入真实参数。"
)


@dataclass
class RuleSet:
    """一套工艺能力阈值（长度单位 mm）。"""

    name: str = "jlc-standard-4layer(保守预设)"
    min_trace_mm: float = 0.127          # 最小线宽
    min_via_drill_mm: float = 0.30       # 最小过孔孔径
    min_via_ring_mm: float = 0.13        # 最小过孔环宽
    min_pad_drill_mm: float = 0.30       # 最小通孔焊盘孔径
    max_layers: int = 6                  # 常规工艺的最大层数（超出需询价）
    max_board_mm: float = 500.0          # 单板最大边
    allowed_thickness_mm: tuple[float, ...] = (0.8, 1.0, 1.2, 1.6, 2.0)
    source: str = DEFAULT_RULESET_SOURCE

    @classmethod
    def from_dict(cls, data: dict) -> RuleSet:
        """按当期货期参数覆盖（未给的字段保持默认）。"""
        known = {f for f in cls.__dataclass_fields__}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"未知规则字段：{unknown}（可用：{sorted(known)}）")
        allowed = data.get("allowed_thickness_mm")
        kw = {k: v for k, v in data.items() if k != "allowed_thickness_mm"}
        if allowed is not None:
            kw["allowed_thickness_mm"] = tuple(float(x) for x in allowed)
        kw.setdefault("source", "调用方注入的工艺参数")
        return cls(**kw)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["allowed_thickness_mm"] = list(self.allowed_thickness_mm)
        return d


@dataclass
class Violation:
    """一条不达标项。"""

    code: str
    message: str
    actual: float | int | None
    limit: float | int | None
    severity: str = "fail"          # fail / warn

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class FabPrecheck:
    """预检结果。"""

    ruleset: dict
    facts: dict
    violations: list[Violation] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if any(v.severity == "fail" for v in self.violations):
            return "fail"
        if self.violations:
            return "warn"
        return "pass"

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "ruleset": self.ruleset,
            "facts": self.facts,
            "violations": [v.as_dict() for v in self.violations],
        }


def board_facts(board: Board) -> dict:
    """从板子推出的**工艺事实**（不含任何阈值判断）。"""
    routing = board.routing_stats()
    vias = board.via_stats()
    pads = board.pad_drill_stats()
    drills = [d for d in (vias["min_drill_mm"], pads["min_drill_mm"]) if d is not None]
    return {
        "board_size_mm": list(board.board_size_mm()) if board.board_size_mm() else None,
        "copper_layer_count": len(board.copper_layers()),
        "thickness_mm": board.thickness_mm,
        "min_trace_mm": routing["min_width_mm"],
        "min_via_drill_mm": vias["min_drill_mm"],
        "min_via_ring_mm": vias["min_annular_ring_mm"],
        "min_pad_drill_mm": pads["min_drill_mm"],
        "min_drill_mm": min(drills) if drills else None,
        "track_count": routing["track_count"],
        "via_count": vias["via_count"],
        "footprint_count": len(board.footprints),
    }


def precheck(board: Board, rules: RuleSet | None = None) -> FabPrecheck:
    """跑制造前预检。

    检查项（每项都必须有**实测值来源**，缺数据时跳过而不是猜）：
    最小线宽 / 最小过孔孔径 / 最小过孔环宽 / 最小通孔焊盘孔径 /
    层数 / 单板尺寸 / 板厚。
    """
    r = rules or RuleSet()
    facts = board_facts(board)
    vs: list[Violation] = []

    def below(key: str, limit: float, code: str, label: str) -> None:
        actual = facts.get(key)
        if actual is None:
            return
        if actual < limit:
            vs.append(Violation(code, f"{label} {actual} mm 低于工艺下限 {limit} mm",
                                actual=actual, limit=limit))

    below("min_trace_mm", r.min_trace_mm, "MIN_TRACE", "最小线宽")
    below("min_via_drill_mm", r.min_via_drill_mm, "MIN_VIA_DRILL", "最小过孔孔径")
    below("min_via_ring_mm", r.min_via_ring_mm, "MIN_VIA_RING", "最小过孔环宽")
    below("min_pad_drill_mm", r.min_pad_drill_mm, "MIN_PAD_DRILL", "最小通孔焊盘孔径")

    layers = facts["copper_layer_count"]
    if layers > r.max_layers:
        vs.append(Violation("LAYER_COUNT", f"铜层数 {layers} 超出常规工艺上限 {r.max_layers}",
                            actual=layers, limit=r.max_layers))

    size = facts["board_size_mm"]
    if size and max(size) > r.max_board_mm:
        vs.append(Violation("BOARD_SIZE", f"板边 {max(size)} mm 超过单板上限 {r.max_board_mm} mm",
                            actual=max(size), limit=r.max_board_mm))

    th = facts["thickness_mm"]
    if th is not None and round(th, 3) not in {round(x, 3) for x in r.allowed_thickness_mm}:
        vs.append(Violation("THICKNESS", f"板厚 {th} mm 不在常备厚度 {list(r.allowed_thickness_mm)} 内",
                            actual=th, limit=None, severity="warn"))

    return FabPrecheck(ruleset=r.as_dict(), facts=facts, violations=vs)


def fabrication_summary(board: Board) -> dict:
    """下单摘要（人工/接口下单时直接抄的那些字段）。"""
    wh = board.board_size_mm()
    return {
        "size_mm": f"{wh[0]} x {wh[1]}" if wh else None,
        "copper_layers": len(board.copper_layers()),
        "thickness_mm": board.thickness_mm,
        "min_trace_mm": board.routing_stats()["min_width_mm"],
        "min_drill_mm": board_facts(board)["min_drill_mm"],
        "component_count": len(board.footprints),
        "track_count": len(board.segments),
        "via_count": len(board.vias),
        "unrouted_nets": [n["name"] for n in board.unrouted_nets()],
    }
