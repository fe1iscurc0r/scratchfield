"""可视线图构建（卷171-A）。

对齐上游 DroneDetour 的 KeyPointExtractor + KeyPointGraphBuilder 语义：
  顶点集 = 起终点 + **只对与起终直线相交的禁飞区**取「缓冲后边界点」
  边     = 顶点两两之间「线段不穿任何禁飞区（且不相交围栏外）」的可见对
  权重   = 欧氏距离
"""
from __future__ import annotations

from .no_fly import (
    Point,
    Polygon,
    buffer_polygon,
    euclidean,
    segment_intersects_polygon,
    segments_intersect,
)


def extract_key_points(start: Point, end: Point, zones, buffer_meters: float) -> list[Point]:
    """关键点提取（对齐上游 extractKeyPoints）。

    只对「与起终直线相交」的禁飞区取其缓冲边界点——不相关禁飞区不进图，
    控制顶点规模。buffer_meters 为安全缓冲（米）。
    """
    points: list[Point] = [start, end]
    for zone in zones:
        if segment_intersects_polygon(start, end, zone):
            expanded = buffer_polygon(zone, buffer_meters)
            for v in expanded.vertices:
                if v not in points:
                    points.append(v)
    return points


def is_visible(a: Point, b: Point, zones, fence: Polygon | None = None) -> bool:
    """a→b 是否可见：不穿任何禁飞区；给了 fence 则整段须在围栏内。"""
    for zone in zones:
        if segment_intersects_polygon(a, b, zone):
            return False
    if fence is not None and not path_within_polygon([a, b], fence):
        return False
    return True


def path_within_polygon(waypoints, polygon: Polygon) -> bool:
    """整条航路是否完全落在多边形内（对齐上游 isPathWithinSafeZone）。

    注意：上游该函数的 List 版本存在「返回首个段结果即返回」的实现差异
    （Java 版在循环内 return false/true 语义不统一）；本重写取**严格语义**：
    所有段都在内才算在内——并在测试里钉住。
    """
    return all(polygon.contains(w) for w in waypoints) and not any(
        segments_intersect(waypoints[i], waypoints[i + 1], e1, e2)
        for i in range(len(waypoints) - 1)
        for e1, e2 in polygon.edges()
    )


def build_visibility_graph(
    points: list[Point], zones, fence: Polygon | None = None
) -> dict[int, list[tuple[int, float]]]:
    """构建可视线图邻接表：{i: [(j, weight), ...]}，权重=欧氏距离。

    边索引对应 points 列表下标；无向图（双向写入）。
    """
    adj: dict[int, list[tuple[int, float]]] = {i: [] for i in range(len(points))}
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            p1, p2 = points[i], points[j]
            if p1 == p2:
                continue
            if not is_visible(p1, p2, zones, fence):
                continue
            w = euclidean(p1, p2)
            adj[i].append((j, w))
            adj[j].append((i, w))
    return adj
