"""`.kicad_pcb` 读取与结构统计（工单245）。

给 agent 线一个**不看 KiCAD UI 也能读懂板子**的视图：板框尺寸、铜层、元件/焊盘、
网络表、走线/过孔统计、以及从文件里能推出的工艺下限（最小线宽 / 最小孔径 / 环宽）。
`fab_bridge.py` 拿这些数去对嘉立创的工艺能力做**制造前预检**。

坐标口径
--------
KiCAD 6+ 的 `.kicad_pcb` **以毫米为单位存文本**（`(at 100 50)` = 100mm, 50mm）。
本模块按 mm 解释，并对 `version < 20210000` 的旧文件给出告警字段
（老版本可能不是这套口径，本 PoC **不猜**，只标注）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .sexpr import SExpr

#: 铜层判断：KiCAD 层名以 `.Cu` 结尾（F.Cu / B.Cu / In1.Cu …）
_CU_SUFFIX = ".Cu"
#: 板框层
_EDGE_LAYER = "Edge.Cuts"


@dataclass
class Pad:
    """焊盘。"""

    number: str
    type: str                    # smd / thru_hole / np_thru_hole / connect
    shape: str = ""
    at: tuple[float, float] | None = None
    size: tuple[float, float] | None = None
    drill: float | None = None
    net: int | None = None
    net_name: str = ""

    @property
    def is_through(self) -> bool:
        """通孔类焊盘（会打孔 —— 影响最小孔径统计）。"""
        return self.type in ("thru_hole", "np_thru_hole")


@dataclass
class Footprint:
    """板上的一个封装（一个实物器件）。"""

    lib: str
    reference: str
    value: str
    layer: str
    at: tuple[float, float, float] | None
    pads: list[Pad] = field(default_factory=list)

    @property
    def pad_count(self) -> int:
        return len(self.pads)

    def as_dict(self) -> dict:
        return {
            "reference": self.reference,
            "value": self.value,
            "lib": self.lib,
            "layer": self.layer,
            "at": list(self.at) if self.at else None,
            "pad_count": self.pad_count,
            "nets": sorted({p.net_name for p in self.pads if p.net_name}),
        }


@dataclass
class Segment:
    """一段走线。"""

    layer: str
    width: float
    start: tuple[float, float]
    end: tuple[float, float]
    net: int | None = None

    @property
    def length_mm(self) -> float:
        return math.dist(self.start, self.end)


@dataclass
class Via:
    """一个过孔。"""

    at: tuple[float, float] | None
    size: float | None
    drill: float | None
    layers: tuple[str, str] | None
    net: int | None = None

    @property
    def annular_ring_mm(self) -> float | None:
        """环宽 = (外径 − 孔径) / 2 —— 嘉立创的最小环宽是硬门槛。"""
        if self.size is None or self.drill is None:
            return None
        return (self.size - self.drill) / 2.0


@dataclass
class Board:
    """解析后的 PCB。"""

    path: str
    version: str = ""
    generator: str = ""
    thickness_mm: float | None = None
    layers: list[str] = field(default_factory=list)            # 全部层名（含非铜层）
    nets: dict[int, str] = field(default_factory=dict)
    footprints: list[Footprint] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    edge_bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)

    # ---------------------------------------------------------------- 构造
    @classmethod
    def parse(cls, path: str | Path) -> Board:
        p = Path(path)
        root = sexpr.parse_one(p.read_text(encoding="utf-8"))
        if sexpr.tag(root) != "kicad_pcb":
            raise sexpr.SExprError(f"{p.name} 顶层不是 kicad_pcb（实为 {sexpr.tag(root)!r}）")
        b = cls(path=str(p))
        b.version = sexpr.child_value(root, "version") or ""
        b.generator = sexpr.child_value(root, "generator") or ""
        gen = sexpr.find_child(root, "general")
        if gen is not None:
            b.thickness_mm = sexpr.atom_float(sexpr.child_value(gen, "thickness"))
        b.layers = _layer_names(root)
        b.nets = _net_table(root)
        b.footprints = _footprints(root, b.nets)
        b.segments = _segments(root)
        b.vias = _vias(root)
        b.edge_bbox = _edge_bbox(root)
        return b

    # ---------------------------------------------------------------- 查询
    @property
    def is_legacy_coords(self) -> bool:
        """版本早于 20210000 ⇒ 坐标口径未在本 PoC 验证范围（只标注，不猜）。"""
        try:
            return int(self.version) < 20210000
        except (TypeError, ValueError):
            return True

    def copper_layers(self) -> list[str]:
        return [x for x in self.layers if x.endswith(_CU_SUFFIX)]

    def board_size_mm(self) -> tuple[float, float] | None:
        """板框宽高（Edge.Cuts 包围盒）。"""
        if not self.edge_bbox:
            return None
        x0, y0, x1, y1 = self.edge_bbox
        return (round(x1 - x0, 4), round(y1 - y0, 4))

    def board_area_mm2(self) -> float | None:
        wh = self.board_size_mm()
        return round(wh[0] * wh[1], 4) if wh else None

    def by_reference(self) -> dict[str, Footprint]:
        return {f.reference: f for f in self.footprints}

    def routing_stats(self) -> dict:
        """走线统计：总数/总长/按层/最小线宽 + 线宽直方图。"""
        by_layer: dict[str, dict] = {}
        widths: dict[float, int] = {}
        total_len = 0.0
        for s in self.segments:
            d = by_layer.setdefault(s.layer, {"tracks": 0, "length_mm": 0.0, "min_width_mm": None})
            d["tracks"] += 1
            d["length_mm"] = round(d["length_mm"] + s.length_mm, 4)
            if d["min_width_mm"] is None or s.width < d["min_width_mm"]:
                d["min_width_mm"] = s.width
            widths[s.width] = widths.get(s.width, 0) + 1
            total_len += s.length_mm
        return {
            "track_count": len(self.segments),
            "total_length_mm": round(total_len, 4),
            "min_width_mm": min(widths) if widths else None,
            "by_layer": by_layer,
            "width_histogram": {str(k): v for k, v in sorted(widths.items())},
        }

    def via_stats(self) -> dict:
        """过孔统计：数量 / 最小孔径 / 最小外径 / **最小环宽**。"""
        drills = [v.drill for v in self.vias if v.drill is not None]
        sizes = [v.size for v in self.vias if v.size is not None]
        rings = [r for r in (v.annular_ring_mm for v in self.vias) if r is not None]
        return {
            "via_count": len(self.vias),
            "min_drill_mm": min(drills) if drills else None,
            "min_size_mm": min(sizes) if sizes else None,
            "min_annular_ring_mm": round(min(rings), 4) if rings else None,
        }

    def pad_drill_stats(self) -> dict:
        """通孔焊盘的孔径统计（和过孔一起决定「最小孔径」）。"""
        drills = [p.drill for f in self.footprints for p in f.pads
                  if p.is_through and p.drill is not None]
        return {"through_pad_count": len(drills), "min_drill_mm": min(drills) if drills else None}

    def nets_with_pads(self) -> dict[int, str]:
        """被焊盘引用到的网络（= 真实需要连线的网络）。"""
        used = {p.net for f in self.footprints for p in f.pads if p.net}
        return {n: self.nets.get(n, "") for n in sorted(used)}

    def unrouted_nets(self) -> list[dict]:
        """有焊盘但**没有任何走线/过孔**的网络 —— 布局布线进度的直接指标。"""
        routed = {s.net for s in self.segments} | {v.net for v in self.vias}
        return [{"net": n, "name": name}
                for n, name in self.nets_with_pads().items() if n not in routed]

    def summary(self) -> dict:
        wh = self.board_size_mm()
        return {
            "path": self.path,
            "version": self.version,
            "generator": self.generator,
            "legacy_coords_warning": self.is_legacy_coords,
            "thickness_mm": self.thickness_mm,
            "copper_layers": self.copper_layers(),
            "copper_layer_count": len(self.copper_layers()),
            "footprint_count": len(self.footprints),
            "pad_count": sum(f.pad_count for f in self.footprints),
            "net_count": len(self.nets_with_pads()),
            "board_size_mm": list(wh) if wh else None,
            "routing": self.routing_stats(),
            "vias": self.via_stats(),
            "through_pad_drills": self.pad_drill_stats(),
            "unrouted_net_count": len(self.unrouted_nets()),
        }


# --------------------------------------------------------------------------- 内部


def _net_table(root: SExpr) -> dict[int, str]:
    """网络表：**只认顶层直接子节点** `(net <id> "<name>")`。

    ⚠️ 不能用 `find_all(root, "net")`：`(segment … (net 1))` 与 `(via … (net 1))` 里
    也有 `net` 块，但**只有 id 没有名字**，递归收集会让它们把真名**覆盖成空串**
    （实测踩过：8 个网络里 7 个名字消失，只剩最后一个碰巧带名的 DIO0）。
    KiCAD 的网络表本来就只声明在顶层 —— 按语义取直接子节点即可。
    """
    out: dict[int, str] = {}
    for n in sexpr.children(root):
        if sexpr.tag(n) != "net" or len(n) < 2:
            continue
        raw = sexpr.atom(n[1])
        if raw is None or not raw.lstrip("-").isdigit():
            continue
        out[int(raw)] = sexpr.atom(n[2]) or "" if len(n) > 2 else ""
    return out


def _layer_names(root: SExpr) -> list[str]:
    layers = sexpr.find_child(root, "layers")
    if layers is None:
        return []
    out = []
    for entry in sexpr.children(layers):
        # (0 "F.Cu" signal) —— 索引 + 名 + 类型
        if isinstance(entry, list) and len(entry) >= 2:
            name = sexpr.atom(entry[1])
            if name:
                out.append(name)
    return out


def _xy(node: SExpr | None) -> tuple[float, float] | None:
    if node is None or len(node) < 3:
        return None
    x, y = sexpr.atom_float(node[1]), sexpr.atom_float(node[2])
    return (x, y) if x is not None and y is not None else None


def _footprints(root: SExpr, nets: dict[int, str]) -> list[Footprint]:
    out: list[Footprint] = []
    for fp in sexpr.find_all(root, "footprint"):
        lib = sexpr.atom(fp[1]) if len(fp) > 1 else ""
        at_node = sexpr.find_child(fp, "at")
        at = None
        if at_node and len(at_node) >= 3:
            x, y = sexpr.atom_float(at_node[1]), sexpr.atom_float(at_node[2])
            rot = sexpr.atom_float(at_node[3]) if len(at_node) > 3 else 0.0
            if x is not None and y is not None:
                at = (x, y, rot or 0.0)
        pads: list[Pad] = []
        for pd in sexpr.find_all(fp, "pad"):
            if len(pd) < 3:
                continue
            size_node = sexpr.find_child(pd, "size")
            size = None
            if size_node and len(size_node) >= 3:
                sx, sy = sexpr.atom_float(size_node[1]), sexpr.atom_float(size_node[2])
                if sx is not None and sy is not None:
                    size = (sx, sy)
            drill_node = sexpr.find_child(pd, "drill")
            drill = sexpr.atom_float(drill_node[1]) if drill_node and len(drill_node) > 1 else None
            net_node = sexpr.find_child(pd, "net")
            net = None
            if net_node and len(net_node) > 1 and sexpr.atom(net_node[1]) is not None:
                try:
                    net = int(sexpr.atom(net_node[1]) or 0)
                except ValueError:
                    net = None
            pads.append(Pad(
                number=sexpr.atom(pd[1]) or "",
                type=sexpr.atom(pd[2]) or "",
                shape=sexpr.atom(pd[3]) if len(pd) > 3 else "",
                at=_xy(sexpr.find_child(pd, "at")),
                size=size,
                drill=drill,
                net=net,
                net_name=nets.get(net, "") if net is not None else "",
            ))
        out.append(Footprint(
            lib=lib or "",
            reference=sexpr.property_value(fp, "Reference") or "?",
            value=sexpr.property_value(fp, "Value") or "",
            layer=sexpr.child_value(fp, "layer") or "",
            at=at,
            pads=pads,
        ))
    return out


def _segments(root: SExpr) -> list[Segment]:
    out: list[Segment] = []
    for s in sexpr.find_all(root, "segment"):
        start, end = _xy(sexpr.find_child(s, "start")), _xy(sexpr.find_child(s, "end"))
        if start is None or end is None:
            continue
        width = sexpr.atom_float(sexpr.child_value(s, "width")) or 0.0
        net_node = sexpr.find_child(s, "net")
        net = None
        if net_node and len(net_node) > 1:
            try:
                net = int(sexpr.atom(net_node[1]) or 0)
            except ValueError:
                net = None
        out.append(Segment(layer=sexpr.child_value(s, "layer") or "", width=width,
                           start=start, end=end, net=net))
    return out


def _vias(root: SExpr) -> list[Via]:
    out: list[Via] = []
    for v in sexpr.find_all(root, "via"):
        layers_node = sexpr.find_child(v, "layers")
        layers = None
        if layers_node and len(layers_node) >= 3:
            layers = (sexpr.atom(layers_node[1]) or "", sexpr.atom(layers_node[2]) or "")
        net_node = sexpr.find_child(v, "net")
        net = None
        if net_node and len(net_node) > 1:
            try:
                net = int(sexpr.atom(net_node[1]) or 0)
            except ValueError:
                net = None
        out.append(Via(
            at=_xy(sexpr.find_child(v, "at")),
            size=sexpr.atom_float(sexpr.child_value(v, "size")),
            drill=sexpr.atom_float(sexpr.child_value(v, "drill")),
            layers=layers,
            net=net,
        ))
    return out


def _edge_bbox(root: SExpr) -> tuple[float, float, float, float] | None:
    """Edge.Cuts 上所有图形的包围盒（板框尺寸的来源）。

    支持 line / rect / arc / circle / poly —— 够覆盖常规板框；
    不支持的图形类型**不静默跳过**而是记进 `unsupported`（由调用方决定要不要报）。
    """
    xs: list[float] = []
    ys: list[float] = []
    for shape in ("gr_line", "gr_rect", "gr_arc", "gr_circle", "gr_poly", "gr_curve", "gr_bbox"):
        for node in sexpr.find_all(root, shape):
            if sexpr.child_value(node, "layer") != _EDGE_LAYER:
                continue
            for key in ("start", "end", "mid", "center"):
                xy = _xy(sexpr.find_child(node, key))
                if xy:
                    xs.append(xy[0])
                    ys.append(xy[1])
            pts = sexpr.find_child(node, "pts")
            if pts is not None:
                for p in sexpr.find_all(pts, "xy"):
                    xy = _xy(p)
                    if xy:
                        xs.append(xy[0])
                        ys.append(xy[1])
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
