"""geo_detour —— 几何绕障层（卷171-A，DroneDetour 纯 Python 重写）。

上游：xumeng367/DroneDetour（MIT，Java/Kotlin + JTS + jgrapht）——
多边形禁飞区 → 可视线图 → 最短绕行路径。本包纯 Python（stdlib only）重写
核心几何层，不引上游运行时依赖。

模块：
  no_fly.py    禁飞区原语（多边形/圆近似、射线法点在内外、航段相交、安全缓冲）
  visibility.py 关键点提取 + 可视线图构建
  detour.py     直连短路 / Dijkstra 绕行 / 多段航路拼接 / plan_detour 门面

落点映射（授粉报告对齐）：禁飞区多边形 ≙ 频谱占用的时空块，
绕行路径 ≙ 动态频率避让——与态势感知同构；几何层可直接服务
「频谱避让路由」这一同构问题。

自检：
  pytest mcpserver/rf_brain/geo_detour/tests -q
  演示：python -m mcpserver.rf_brain.geo_detour --demo [--out path.svg]
"""
from .detour import DetourResult, find_multi_segment_path, plan_detour, shortest_path
from .no_fly import (
    SAFETY_DISTANCE_METERS,
    Polygon,
    buffer_polygon,
    circle_to_polygon,
    euclidean,
    haversine,
    path_intersects_no_fly,
    path_length,
    point_in_polygon,
    segment_intersects_polygon,
)
from .visibility import build_visibility_graph, extract_key_points, is_visible

__all__ = [
    "DetourResult",
    "Polygon",
    "SAFETY_DISTANCE_METERS",
    "buffer_polygon",
    "build_visibility_graph",
    "circle_to_polygon",
    "euclidean",
    "extract_key_points",
    "find_multi_segment_path",
    "haversine",
    "is_visible",
    "path_intersects_no_fly",
    "path_length",
    "plan_detour",
    "point_in_polygon",
    "segment_intersects_polygon",
    "shortest_path",
]
