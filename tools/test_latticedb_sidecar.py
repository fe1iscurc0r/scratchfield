"""W69-03 融合测试：latticedb 记忆 sidecar（mock 降级 + 三合一查询）。

运行：python -m pytest tools/test_latticedb_sidecar.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from latticedb_sidecar import LatticeSidecar


def _emb(seed: float) -> np.ndarray:
    return np.array([seed, 1.0 - seed, 0.5])


def test_mock_degradation_without_latticedb():
    """无 latticedb 时 mock 降级（诚实降级）。"""
    s = LatticeSidecar()
    assert s.degraded is True  # 本环境未装 latticedb → mock


def test_add_node_and_edge():
    s = LatticeSidecar()
    s.add_node("a", "neural networks overview", _emb(0.9))
    s.add_node("b", "graph database paper", _emb(0.2))
    s.add_edge("a", "PART_OF", "b")
    assert len(s._nodes) == 2
    assert ("PART_OF", "b") in s._edges["a"]


def test_query_fulltext_match():
    """全文命中：qtext 命中的节点排在结果里。"""
    s = LatticeSidecar()
    s.add_node("a", "neural networks", _emb(0.9))
    s.add_node("b", "unrelated text", _emb(0.2))
    res = s.query(qvec=_emb(0.9), qtext="neural", top_k=5)
    ids = [n for n, _ in res]
    assert "a" in ids and "b" not in ids


def test_query_vector_ranking():
    """向量近邻：向量更近的节点得分更高。"""
    s = LatticeSidecar()
    s.add_node("near", "graph db", _emb(0.85))
    s.add_node("far", "graph db", _emb(0.15))
    res = s.query(qvec=_emb(0.9), qtext="graph", top_k=2)
    assert res[0][0] == "near"
    assert res[1][0] == "far"


def test_query_graph_adjacency_expansion():
    """图邻接：命中节点的邻居被折扣补入结果。"""
    s = LatticeSidecar()
    s.add_node("a", "neural networks", _emb(0.9))
    s.add_node("b", "b's text", _emb(0.3))
    s.add_edge("a", "PART_OF", "b")
    res = s.query(qvec=_emb(0.9), qtext="neural", top_k=5)
    ids = [n for n, _ in res]
    assert "a" in ids and "b" in ids  # b 经图邻接补入
