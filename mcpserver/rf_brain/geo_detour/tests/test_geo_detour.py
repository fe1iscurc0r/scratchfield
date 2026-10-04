"""geo_detour 验收测试（卷171-A）。

工单验收三场景：
  1. 空域无禁飞区 → 直线路径，长度 = 欧氏距离
  2. 单个凸多边形挡路 → 路径绕行且**每段**不与禁飞区相交（逐段 assert）
  3. 路径总长 < 直线距离 × 2（合理绕行上界）
附加：缓冲/圆近似/多段航路/可见性图/Dijkstra 边界用例。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.rf_brain.geo_detour import (  # noqa: E402
    SAFETY_DISTANCE_METERS,
    Polygon,
    buffer_polygon,
    build_visibility_graph,
    circle_to_polygon,
    euclidean,
    extract_key_points,
    find_multi_segment_path,
    haversine,
    path_intersects_no_fly,
    path_length,
    plan_detour,
    point_in_polygon,
    segment_intersects_polygon,
    shortest_path,
)
from mcpserver.rf_brain.geo_detour.detour import dijkstra  # noqa: E402

SQUARE = Polygon(((20.0, -10.0), (45.0, -10.0), (45.0, 25.0), (20.0, 25.0)))


class TestNoFlyPrimitives:
    def test_point_in_polygon_inside_outside(self):
        assert point_in_polygon((30.0, 5.0), SQUARE.vertices)
        assert not point_in_polygon((5.0, 5.0), SQUARE.vertices)
        assert not point_in_polygon((50.0, 5.0), SQUARE.vertices)

    def test_point_on_boundary_counts_inside(self):
        """边界点视为在内（保守）——绕障场景宁可多绕。"""
        assert point_in_polygon((20.0, 5.0), SQUARE.vertices)

    def test_segment_intersects_polygon(self):
        assert segment_intersects_polygon((0.0, 0.0), (60.0, 0.0), SQUARE)
        assert not segment_intersects_polygon((0.0, -50.0), (60.0, -50.0), SQUARE)

    def test_segment_with_endpoint_inside(self):
        assert segment_intersects_polygon((30.0, 5.0), (100.0, 5.0), SQUARE)

    def test_polygon_needs_three_vertices(self):
        with pytest.raises(ValueError):
            Polygon(((0.0, 0.0), (1.0, 1.0)))

    def test_buffer_polygon_expands(self):
        buffered = buffer_polygon(SQUARE, SAFETY_DISTANCE_METERS)
        assert buffered.radius() > SQUARE.radius()
        for v in buffered.vertices:
            assert not SQUARE.contains(v)  # 缓冲点必在原始区外

    def test_buffer_zero_is_identity(self):
        assert buffer_polygon(SQUARE, 0) is SQUARE

    def test_circle_approx(self):
        c = circle_to_polygon((10.0, 10.0), radius_meters=1000.0, segments=16)
        assert len(c.vertices) == 16
        assert c.contains((10.0, 10.0))
        assert not c.contains((10.0 + 0.02, 10.0))  # 1000m ≈ 0.009° 外

    def test_haversine_known_distance(self):
        # 赤道上 1 度经度 ≈ 111.19 km
        d = haversine(0.0, 0.0, 0.0, 1.0)
        assert abs(d - 111194.9) < 200


class TestAcceptanceScenarios:
    """工单三验收场景（A.4）。"""

    def test_no_zones_straight_line_euclidean(self):
        start, end = (0.0, 0.0), (100.0, 40.0)
        result = plan_detour(start, end, [])
        assert result.path == [start, end]
        assert not result.detoured
        assert result.detoured_distance == pytest.approx(euclidean(start, end))
        assert result.overhead_ratio == pytest.approx(1.0)

    def test_single_convex_polygon_detour_each_segment_clear(self):
        start, end = (0.0, 0.0), (60.0, 5.0)
        result = plan_detour(start, end, [SQUARE])
        assert result.detoured
        assert len(result.path) > 2
        # 逐段 assert：每段不与禁飞区相交（工单硬验收）
        for i in range(len(result.path) - 1):
            assert not segment_intersects_polygon(result.path[i], result.path[i + 1], SQUARE), \
                f"第 {i} 段穿越禁飞区"
        assert not path_intersects_no_fly(result.path, [SQUARE])

    def test_detour_length_under_twice_direct(self):
        start, end = (0.0, 0.0), (60.0, 5.0)
        result = plan_detour(start, end, [SQUARE])
        assert result.detoured_distance < result.direct_distance * 2

    def test_direct_path_through_zone_is_detoured(self):
        """起终直线穿区时不得返回直线（直连短路只在无冲突时触发）。"""
        start, end = (0.0, 0.0), (60.0, 0.0)
        result = plan_detour(start, end, [SQUARE])
        assert result.detoured
        assert not path_intersects_no_fly(result.path, [SQUARE])


class TestVisibilityAndGraph:
    def test_extract_key_points_only_intersecting_zones(self):
        start, end = (0.0, 0.0), (60.0, 5.0)
        far_zone = Polygon(((200.0, 200.0), (210.0, 200.0), (210.0, 210.0), (200.0, 210.0)))
        points = extract_key_points(start, end, [SQUARE, far_zone], SAFETY_DISTANCE_METERS)
        # 起终点 + 仅 SQUARE 的缓冲顶点（4 个）
        assert len(points) == 6
        assert start in points and end in points

    def test_visibility_graph_connectivity(self):
        start, end = (0.0, 0.0), (60.0, 5.0)
        points = extract_key_points(start, end, [SQUARE], SAFETY_DISTANCE_METERS)
        adj = build_visibility_graph(points, [SQUARE])
        idx = dijkstra(adj, 0, 1)
        assert idx is not None and idx[0] == 0 and idx[-1] == 1

    def test_dijkstra_unreachable_returns_none(self):
        assert dijkstra({0: [], 1: []}, 0, 1) is None

    def test_dijkstra_same_node(self):
        assert dijkstra({0: []}, 0, 0) == [0]


class TestMultiSegment:
    def test_multi_segment_mixed_direct_and_detour(self):
        waypoints = [(0.0, 0.0), (60.0, 5.0), (120.0, 60.0)]
        path = find_multi_segment_path(waypoints, [SQUARE])
        assert path is not None
        assert path[0] == waypoints[0] and path[-1] == waypoints[-1]
        assert not path_intersects_no_fly(path, [SQUARE])
        # 接点不重复
        for i in range(len(path) - 1):
            assert path[i] != path[i + 1]

    def test_multi_segment_all_clear_is_identity(self):
        waypoints = [(0.0, -50.0), (60.0, -50.0), (120.0, -50.0)]
        path = find_multi_segment_path(waypoints, [SQUARE])
        assert path == waypoints

    def test_shortest_path_same_point(self):
        assert shortest_path((1.0, 1.0), (1.0, 1.0), []) == [(1.0, 1.0)]


class TestResultMetadata:
    def test_overhead_ratio_reported(self):
        result = plan_detour((0.0, 0.0), (60.0, 5.0), [SQUARE])
        assert 1.0 < result.overhead_ratio < 2.0
        assert result.key_points
        assert result.detoured_distance == pytest.approx(path_length(result.path))

    def test_circle_zone_detour(self):
        """圆形禁飞区（近似多边形）同样可绕。"""
        zone = circle_to_polygon((30.0, 0.0), radius_meters=1500.0, segments=24)
        result = plan_detour((0.0, 0.0), (60.0, 0.0), [zone])
        assert result.detoured
        assert not path_intersects_no_fly(result.path, [zone])


class TestDemoCli:
    def test_demo_svg_output(self, tmp_path):
        from mcpserver.rf_brain.geo_detour.__main__ import main
        out = tmp_path / "demo.svg"
        rc = main(["--demo", "--out", str(out)])
        assert rc == 0
        svg = out.read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "NFZ-1" in svg and len(svg) > 500

    def test_demo_svg_is_valid_xml(self, tmp_path):
        import xml.etree.ElementTree as ET

        from mcpserver.rf_brain.geo_detour.__main__ import main
        out = tmp_path / "demo.svg"
        main(["--demo", "--out", str(out)])
        ET.fromstring(out.read_text(encoding="utf-8"))  # 不抛即合法
