# memory_graph 单元测试 — 记忆关联图谱（授粉自 mcp-memory-service）
#
# 覆盖：对称/非对称边存储、自环拒绝、相似度越界、非法关系类型、
#       多跳递归 CTE 遍历、最短路径 BFS、子图提取、关系类型统计、循环预防
# 运行：python3 -m pytest NEKO/N.E.K.O/memory/test_memory_graph.py -q
"""Tests for MemoryGraph (SQLite recursive CTE association graph)."""

from __future__ import annotations

import pytest

from memory.memory_graph import (
    ASYMMETRIC_RELATIONSHIPS,
    SYMMETRIC_RELATIONSHIPS,
    MemoryGraph,
    VALID_RELATIONSHIPS,
    normalize_entity_id,
)


@pytest.fixture()
def graph(tmp_path):
    g = MemoryGraph(tmp_path / "test_graph.db")
    yield g
    g.close()


# ---------------------------------------------------------------- 校验
class TestValidation:
    def test_normalize(self) -> None:
        assert normalize_entity_id("  Hello World ") == "hello world"
        assert normalize_entity_id("CI-V") == "ci-v"

    def test_self_loop_rejected(self, graph) -> None:
        assert graph.store_association("a", "a") is False
        assert graph.count() == 0

    def test_empty_rejected(self, graph) -> None:
        assert graph.store_association("", "b") is False
        assert graph.store_association("a", "  ") is False

    def test_similarity_bounds(self, graph) -> None:
        assert graph.store_association("a", "b", similarity=1.5) is False
        assert graph.store_association("a", "b", similarity=-0.1) is False
        assert graph.count() == 0

    def test_invalid_relationship(self, graph) -> None:
        assert graph.store_association("a", "b", relationship_type="loves") is False
        assert graph.count() == 0

    def test_valid_relationship_sets(self) -> None:
        assert SYMMETRIC_RELATIONSHIPS == {"related", "contradicts"}
        # F-03：supersedes 加入非对称集（矛盾检测新值取代旧值，新→旧有向）
        assert ASYMMETRIC_RELATIONSHIPS == {"causes", "fixes", "supports", "follows", "supersedes"}
        assert len(VALID_RELATIONSHIPS) == 7


# ---------------------------------------------------------------- 边存储
class TestStore:
    def test_symmetric_stores_both_directions(self, graph) -> None:
        assert graph.store_association("a", "b", similarity=0.8, relationship_type="related")
        # 对称关系：双向可达
        connected_from_a = {h for h, _ in graph.find_connected("a", max_hops=1)}
        connected_from_b = {h for h, _ in graph.find_connected("b", max_hops=1)}
        assert connected_from_a == {"b"}
        assert connected_from_b == {"a"}

    def test_asymmetric_stores_one_direction(self, graph) -> None:
        assert graph.store_association("a", "b", similarity=0.6, relationship_type="causes")
        from_a = {h for h, _ in graph.find_connected("a", max_hops=1)}
        from_b = {h for h, _ in graph.find_connected("b", max_hops=1)}
        assert from_a == {"b"}   # A → B 可达
        assert from_b == set()   # B 不可达 A（有向）

    def test_contradicts_symmetric(self, graph) -> None:
        assert graph.store_association("a", "b", relationship_type="contradicts")
        assert {h for h, _ in graph.find_connected("b", max_hops=1)} == {"a"}

    def test_upsert_replaces(self, graph) -> None:
        assert graph.store_association("a", "b", similarity=0.5)
        assert graph.store_association("a", "b", similarity=0.9)
        # find_connected 不返回 similarity，直接查库确认替换
        rows = graph.get_subgraph("a", max_hops=1)["edges"]
        sims = {e["similarity"] for e in rows}
        assert 0.9 in sims


# ---------------------------------------------------------------- 多跳遍历
class TestFindConnected:
    def test_two_hop(self, graph) -> None:
        graph.store_association("a", "b")
        graph.store_association("b", "c")
        res = dict(graph.find_connected("a", max_hops=2))
        assert res["b"] == 1
        assert res["c"] == 2

    def test_hops_bound(self, graph) -> None:
        graph.store_association("a", "b")
        graph.store_association("b", "c")
        graph.store_association("c", "d")
        res = dict(graph.find_connected("a", max_hops=2))
        assert "d" not in res  # 3 跳超出
        res3 = dict(graph.find_connected("a", max_hops=3))
        assert "d" in res3

    def test_cycle_prevention(self, graph) -> None:
        graph.store_association("a", "b")
        graph.store_association("b", "a")  # 环
        graph.store_association("b", "c")
        res = dict(graph.find_connected("a", max_hops=5))
        # 不死循环，距离正确
        assert res["b"] == 1
        assert res["c"] == 2

    def test_relationship_filter(self, graph) -> None:
        graph.store_association("a", "b", relationship_type="related")
        graph.store_association("a", "c", relationship_type="causes")
        rel = {h for h, _ in graph.find_connected("a", max_hops=1, relationship_type="causes")}
        assert rel == {"c"}

    def test_empty_hash_returns_empty(self, graph) -> None:
        assert graph.find_connected("") == []


# ---------------------------------------------------------------- 最短路径
class TestShortestPath:
    def test_direct(self, graph) -> None:
        graph.store_association("a", "b")
        assert graph.shortest_path("a", "b") == ["a", "b"]

    def test_chain(self, graph) -> None:
        graph.store_association("a", "b")
        graph.store_association("b", "c")
        graph.store_association("c", "d")
        assert graph.shortest_path("a", "d") == ["a", "b", "c", "d"]

    def test_same_node(self, graph) -> None:
        assert graph.shortest_path("a", "a") == ["a"]

    def test_unreachable(self, graph) -> None:
        graph.store_association("a", "b")
        graph.store_association("c", "d")
        assert graph.shortest_path("a", "d") is None


# ---------------------------------------------------------------- 子图/统计
class TestSubgraphAndStats:
    def test_subgraph(self, graph) -> None:
        graph.store_association("a", "b", similarity=0.7)
        graph.store_association("a", "c", relationship_type="causes")
        sg = graph.get_subgraph("a")
        assert set(sg["nodes"]) == {"a", "b", "c"}
        assert len(sg["edges"]) == 3  # a→b, b→a(对称反向), a→c
        types = {e["type"] for e in sg["edges"]}
        assert types == {"related", "causes"}

    def test_relationship_stats(self, graph) -> None:
        graph.store_association("a", "b")  # related 对称 → 2 条边（a→b, b→a）
        graph.store_association("a", "c", relationship_type="causes")  # 有向 → 1 条边
        stats = graph.get_relationship_types("a")
        assert stats["related"] == 2
        assert stats["causes"] == 1

    def test_count(self, graph) -> None:
        assert graph.count() == 0
        graph.store_association("a", "b")  # 对称 → 2 条边
        assert graph.count() == 2
        graph.store_association("c", "d", relationship_type="causes")  # 有向 → 1 条边
        assert graph.count() == 3


# ---------------------------------------------------------------- 元数据
class TestMetadata:
    def test_metadata_stored(self, graph) -> None:
        graph.store_association(
            "a", "b", similarity=0.9,
            connection_types=["semantic", "temporal"],
            metadata={"source": "session-42"},
        )
        sg = graph.get_subgraph("a")
        edge = sg["edges"][0]
        assert edge["similarity"] == 0.9
