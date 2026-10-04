"""绕障最短路（卷171-A）。

对齐上游 DroneDetour 的 GraphUtils.findMultiSegmentPath + DetourPathManager：
  1. 直连短路：起终直线无冲突 → 直接返回 [start, end]（不建图）
  2. 建可视线图 → Dijkstra 最短路（stdlib heapq，替代上游 jgrapht 算法族）
  3. 多段航路：逐段判断，直连段原样拼接、冲突段绕行后拼接（去除重复接点）
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .no_fly import (
    SAFETY_DISTANCE_METERS,
    Point,
    Polygon,
    euclidean,
    path_length,
    segment_intersects_polygon,
)
from .visibility import build_visibility_graph, extract_key_points


@dataclass
class DetourResult:
    """绕行结果：路径 + 元信息（供 CLI 绘图与报告引用）。"""

    path: list[Point]
    direct_distance: float
    detoured_distance: float
    detoured: bool
    key_points: list[Point] = field(default_factory=list)

    @property
    def overhead_ratio(self) -> float:
        """绕行代价比（绕行距离 / 直线距离）；直线场景为 1.0。"""
        if self.direct_distance == 0:
            return 1.0
        return self.detoured_distance / self.direct_distance


def dijkstra(adj: dict[int, list[tuple[int, float]]], src: int, dst: int) -> list[int] | None:
    """Dijkstra 最短路（heapq）；不可达返回 None。"""
    if src == dst:
        return [src]
    dist = {src: 0.0}
    prev: dict[int, int] = {}
    heap: list[tuple[float, int]] = [(0.0, src)]
    visited: set[int] = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == dst:
            break
        for v, w in adj.get(u, []):
            if v in visited:
                continue
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if dst not in dist:
        return None
    chain = [dst]
    while chain[-1] != src:
        chain.append(prev[chain[-1]])
    return list(reversed(chain))


def shortest_path(
    start: Point,
    end: Point,
    zones,
    buffer_meters: float = SAFETY_DISTANCE_METERS,
    fence: Polygon | None = None,
) -> list[Point] | None:
    """单段绕障最短路：直连短路优先，否则可视线图 + Dijkstra。"""
    if start == end:
        return [start]
    # 直连短路（对齐上游：无冲突段不进图）
    if all(not segment_intersects_polygon(start, end, z) for z in zones):
        return [start, end]
    points = extract_key_points(start, end, zones, buffer_meters)
    adj = build_visibility_graph(points, zones, fence)
    idx = dijkstra(adj, 0, 1)  # 0=start, 1=end（extract_key_points 保证顺序）
    if idx is None:
        return None
    return [points[i] for i in idx]


def find_multi_segment_path(
    waypoints: list[Point],
    zones,
    buffer_meters: float = SAFETY_DISTANCE_METERS,
    fence: Polygon | None = None,
) -> list[Point] | None:
    """多段航路绕障（对齐上游 findMultiSegmentPath）。

    逐段：无冲突 → 直连拼接；有冲突 → shortest_path 绕行后拼接（去重接点）。
    任一段不可达 → None。
    """
    full: list[Point] = []
    for i in range(len(waypoints) - 1):
        seg_start, seg_end = waypoints[i], waypoints[i + 1]
        if all(not segment_intersects_polygon(seg_start, seg_end, z) for z in zones):
            if not full:
                full.extend([seg_start, seg_end])
            else:
                if full[-1] != seg_start:
                    full.append(seg_start)
                full.append(seg_end)
            continue
        seg_path = shortest_path(seg_start, seg_end, zones, buffer_meters, fence)
        if seg_path is None:
            return None
        if full:
            seg_path = seg_path[1:]  # 去重接点
        full.extend(seg_path)
    return full


def plan_detour(
    start: Point,
    end: Point,
    zones,
    buffer_meters: float = SAFETY_DISTANCE_METERS,
    fence: Polygon | None = None,
) -> DetourResult:
    """门面：单段绕行规划，返回带元信息的结果（不可达时 path=[]）。"""
    direct = euclidean(start, end)
    key_points = extract_key_points(start, end, zones, buffer_meters) if zones else [start, end]
    path = shortest_path(start, end, zones, buffer_meters, fence)
    if not path:
        return DetourResult(path=[], direct_distance=direct, detoured_distance=float("inf"),
                            detoured=True, key_points=key_points)
    return DetourResult(path=path, direct_distance=direct,
                        detoured_distance=path_length(path), detoured=len(path) > 2,
                        key_points=key_points)
