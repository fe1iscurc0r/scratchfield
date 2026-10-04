"""A61 Pivot-and-Station MAPF 测试：可解 / 端点正确 / 无顶点冲突 / 确定性。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.pivot_station_mapf import (
    Warehouse,
    evaluate,
    solve,
)


def _pad(paths):
    """把短路径用终点填充到等长，便于逐时刻冲突检查"""
    m = max(len(p) for p in paths)
    return [p + [p[-1]] * (m - len(p)) for p in paths]


def test_dense_instance_solved():
    r = evaluate()
    assert r["solved"]
    assert r["makespan"] >= 1


def test_paths_endpoints_correct():
    wh = Warehouse()
    agents = [((1, 1), (5, 7)), ((1, 8), (5, 1)), ((3, 8), (4, 8)), ((1, 3), (5, 5))]
    paths = solve(wh, agents)
    assert paths is not None
    for (s, g), p in zip(agents, paths):
        assert p[0] == s and p[-1] == g


def test_no_vertex_conflicts_off_station():
    wh = Warehouse()
    agents = [((1, 1), (5, 7)), ((1, 8), (5, 1)), ((3, 8), (4, 8)), ((1, 3), (5, 5))]
    paths = _pad(solve(wh, agents))
    for t in range(len(paths[0])):
        cells = [p[t] for p in paths]
        non_station = [c for c in cells if c not in wh.stations]
        assert len(non_station) == len(set(non_station))  # 非缓冲位不共占


def test_moves_are_adjacent_or_wait():
    wh = Warehouse()
    agents = [((1, 1), (5, 7))]
    p = solve(wh, agents)[0]
    for a, b in zip(p, p[1:]):
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1  # 四邻移动或原地等待
