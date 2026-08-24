# memory_graph 扩展测试 — shortest_path / get_subgraph（F-03 图谱补全）
#
# 覆盖（2 方法）：
#   - shortest_path：直连 / 最短性（存在更短路径时改选）/ 不可达 None /
#     对称关系双向 / supersedes 有向语义
#   - get_subgraph：多跳节点收集（max_hops=2）/ 集合内边完整 /
#     max_hops=1 与旧语义兼容 / 方向性（有向边不反向扩散）
# 运行：python -m pytest NEKO/N.E.K.O/memory/test_graph_ext.py -q
"""Extension tests for memory_graph shortest_path / get_subgraph (F-03)."""

from __future__ import annotations

import pytest

from memory.memory_graph import MemoryGraph


@pytest.fixture()
def graph(tmp_path):
    g = MemoryGraph(tmp_path / "graph.db")
    yield g
    g.close()


class TestShortestPath:
    def test_direct_connection(self, graph):
        graph.store_association("a", "b", relationship_type="related")
        assert graph.shortest_path("a", "b") == ["a", "b"]

    def test_prefers_shorter_path_when_added(self, graph):
        """先建 3 跳链，再补 1 条捷径 → 最短路径切换到捷径。"""
        graph.store_association("a", "b", relationship_type="causes")
        graph.store_association("b", "c", relationship_type="causes")
        graph.store_association("c", "d", relationship_type="causes")
        assert graph.shortest_path("a", "d") == ["a", "b", "c", "d"]
        graph.store_association("a", "d", relationship_type="related")
        assert graph.shortest_path("a", "d") == ["a", "d"]

    def test_unreachable_returns_none(self, graph):
        graph.store_association("a", "b", relationship_type="causes")
        graph.store_association("c", "d", relationship_type="causes")
        assert graph.shortest_path("a", "d") is None
        # 注：shortest_path 是双向（无向视角）遍历——main 既有语义，
        # 有向边的方向性由 find_connected / get_supersede_chain 承载（见下）

    def test_symmetric_traversable_both_directions(self, graph):
        graph.store_association("a", "b", relationship_type="contradicts")
        assert graph.shortest_path("a", "b") == ["a", "b"]
        assert graph.shortest_path("b", "a") == ["b", "a"]  # 对称可反向

    def test_same_node_returns_self(self, graph):
        assert graph.shortest_path("a", "a") == ["a"]

    def test_case_and_space_normalization(self, graph):
        graph.store_association("Node A", "node-b", relationship_type="related")
        assert graph.shortest_path("node  a", "NODE-B") == ["node a", "node-b"]

    def test_supersedes_directed_chain(self, graph):
        """F-03 语义：supersedes 正向链 f3→f2→f1 最短路正确。

        方向性（旧不可达新）由 find_connected(relationship_type="supersedes")
        承载（contradiction.get_supersede_chain 依赖它）；shortest_path 本身
        是 main 既有的双向连通性视角，不承担方向语义。
        """
        graph.store_association("f3", "f2", relationship_type="supersedes")
        graph.store_association("f2", "f1", relationship_type="supersedes")
        assert graph.shortest_path("f3", "f1") == ["f3", "f2", "f1"]


class TestGetSubgraphMultiHop:
    def test_two_hop_nodes_and_inner_edges(self, graph):
        """链 a-b-c-d：2 跳子图含 a,b,c 与其间全部边；d 不可入集。"""
        graph.store_association("a", "b", relationship_type="related")
        graph.store_association("b", "c", relationship_type="related")
        graph.store_association("c", "d", relationship_type="related")
        sg = graph.get_subgraph("a", max_hops=2)
        assert set(sg["nodes"]) == {"a", "b", "c"}
        # 集合内边：a-b 双向 + b-c 双向（related 对称各存 2 条）
        inner = {(e["source"], e["target"]) for e in sg["edges"]}
        assert {("a", "b"), ("b", "a"), ("b", "c"), ("c", "b")} <= inner
        assert all(("d" not in (e["source"] + e["target"])) for e in sg["edges"])

    def test_max_hops_one_keeps_legacy_semantics(self, graph):
        """max_hops=1：起点+直接邻居（旧语义），多跳邻居不混入。"""
        graph.store_association("a", "b", relationship_type="related")
        graph.store_association("b", "c", relationship_type="related")
        sg = graph.get_subgraph("a", max_hops=1)
        assert set(sg["nodes"]) == {"a", "b"}
        assert {("a", "b"), ("b", "a")} == {
            (e["source"], e["target"]) for e in sg["edges"]
        }

    def test_directed_relation_respected_in_reach(self, graph):
        """有向边只沿出边扩散：a--causes-->b 的子图从 b 出发不含 a。"""
        graph.store_association("a", "b", relationship_type="causes")
        sg_from_b = graph.get_subgraph("b", max_hops=2)
        assert set(sg_from_b["nodes"]) == {"b"}
        sg_from_a = graph.get_subgraph("a", max_hops=2)
        assert set(sg_from_a["nodes"]) == {"a", "b"}

    def test_supersedes_chain_subgraph(self, graph):
        """F-03 联动：supersedes 链上子图从最新事实出发可收全链。"""
        graph.store_association("f3", "f2", relationship_type="supersedes")
        graph.store_association("f3", "f1", relationship_type="supersedes")
        sg = graph.get_subgraph("f3", max_hops=3)
        assert set(sg["nodes"]) == {"f1", "f2", "f3"}
        sup_edges = [e for e in sg["edges"] if e["type"] == "supersedes"]
        assert {(e["source"], e["target"]) for e in sup_edges} == {
            ("f3", "f2"), ("f3", "f1"),
        }

    def test_isolated_node_returns_self_only(self, graph):
        sg = graph.get_subgraph("lonely", max_hops=5)
        assert sg == {"nodes": ["lonely"], "edges": []}
