"""禁止飞行区几何原语（卷171-A：DroneDetour 纯 Python 重写）。

上游 xumeng367/DroneDetour（MIT）用 JTS + jgrapht（Kotlin/Java）实现
「多边形禁飞区 → 可视线图 → 最短绕行路径」；本模块**纯 Python 重写核心层**，
不引上游运行时依赖、不引第三方几何库（stdlib only）。

坐标约定：平面笛卡尔 (x, y)，单位与调用方一致（度或米皆可——本模块的距离
计算为欧氏；球面距离用 haversine()）。与上游 (lat, lon) 用法同构。

落点映射（对齐授粉报告）：禁飞区多边形 ≙ 频谱占用的时空块，
绕行路径 ≙ 动态频率避让——与态势感知同构。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# 上游 KeyPointExtractor 常量：1 米 ≈ 0.00000899322 度（纬向近似）
ONE_METER_OFFSET = 0.00000899322
# 上游默认安全缓冲（米）——绕行时禁飞区外扩量
SAFETY_DISTANCE_METERS = 30.0

Point = tuple[float, float]


@dataclass(frozen=True)
class Polygon:
    """简单多边形（顶点顺序闭合，不重复首点）。"""

    vertices: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError(f"多边形至少 3 个顶点，收到 {len(self.vertices)}")

    def edges(self):
        """遍历边 (a, b)。"""
        n = len(self.vertices)
        for i in range(n):
            yield self.vertices[i], self.vertices[(i + 1) % n]

    def center(self) -> Point:
        xs = [p[0] for p in self.vertices]
        ys = [p[1] for p in self.vertices]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def radius(self) -> float:
        """外接圆半径（质心到最远顶点）——圆近似用。"""
        cx, cy = self.center()
        return max(math.hypot(x - cx, y - cy) for x, y in self.vertices)

    def contains(self, pt: Point) -> bool:
        return point_in_polygon(pt, self.vertices)


def point_in_polygon(pt: Point, vertices) -> bool:
    """射线法（ray casting）：向右发射射线数交点数，奇数在内。

    边界上的点行为与上游 JTS `contains` 不同——**射线法对边界点判定不保证**，
    故额外做边上的点在段上判定（视为在内，保守）。
    """
    x, y = pt
    n = len(vertices)
    inside = False
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        # 边界判定（点在边上 → 视为在内，保守）
        if _point_on_segment(pt, (x1, y1), (x2, y2)):
            return True
        if (y1 > y) != (y2 > y):
            x_at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at:
                inside = not inside
    return inside


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _point_on_segment(pt: Point, a: Point, b: Point, eps: float = 1e-12) -> bool:
    if abs(_cross(a, b, pt)) > eps:
        return False
    return (min(a[0], b[0]) - eps <= pt[0] <= max(a[0], b[0]) + eps
            and min(a[1], b[1]) - eps <= pt[1] <= max(a[1], b[1]) + eps)


def segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """线段相交判定（含共线重叠；端点接触视为相交）。"""
    d1 = _cross(b1, b2, a1)
    d2 = _cross(b1, b2, a2)
    d3 = _cross(a1, a2, b1)
    d4 = _cross(a1, a2, b2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    # 共线/端点接触
    for pt, s, e in ((a1, b1, b2), (a2, b1, b2), (b1, a1, a2), (b2, a1, a2)):
        if _point_on_segment(pt, s, e):
            return True
    return False


def segment_intersects_polygon(a: Point, b: Point, poly: Polygon) -> bool:
    """航段 a→b 是否与多边形相交（穿边 或 任一端点在内）。"""
    if poly.contains(a) or poly.contains(b):
        return True
    return any(segments_intersect(a, b, e1, e2) for e1, e2 in poly.edges())


def path_intersects_no_fly(waypoints, zones) -> bool:
    """整条航路是否穿过任一禁飞区（对齐上游 intersectsNoFlyZone(List)）。"""
    for i in range(len(waypoints) - 1):
        for zone in zones:
            if segment_intersects_polygon(waypoints[i], waypoints[i + 1], zone):
                return True
    return False


def buffer_polygon(poly: Polygon, meters: float) -> Polygon:
    """禁飞区外扩（安全距离缓冲，对齐上游 JTS polygon.buffer）。

    实现：各顶点沿「质心 → 顶点」方向外移 meters×ONE_METER_OFFSET。
    凸多边形上与逐边外扩等价；凹多边形为近似——绕障场景禁飞区通常为凸区，
    docstring 明示这一近似边界。
    """
    if meters == 0:
        return poly
    cx, cy = poly.center()
    deg = meters * ONE_METER_OFFSET
    out = []
    for x, y in poly.vertices:
        dx, dy = x - cx, y - cy
        norm = math.hypot(dx, dy) or 1.0
        out.append((x + dx / norm * deg, y + dy / norm * deg))
    return Polygon(tuple(out))


def circle_to_polygon(center: Point, radius_meters: float, segments: int = 32) -> Polygon:
    """圆形禁飞区近似为多边形（对齐上游圆形禁飞区支持）。"""
    cx, cy = center
    deg = radius_meters * ONE_METER_OFFSET
    pts = []
    for i in range(segments):
        theta = 2 * math.pi * i / segments
        pts.append((cx + deg * math.cos(theta), cy + deg * math.sin(theta)))
    return Polygon(tuple(pts))


def euclidean(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def path_length(waypoints) -> float:
    return sum(euclidean(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1))


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """球面距离（米）——对齐上游 GeoUtils.haversine。"""
    r = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
