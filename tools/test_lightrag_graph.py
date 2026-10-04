"""lightrag_graph 测试（W73-04 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lightrag_graph import LightGraphIndex, extract_entities


def test_extract_entities():
    ents = extract_entities("Alice works at Google and uses TensorFlow.")
    assert "Alice" in ents or "Google" in ents


def test_add_document_builds_edges():
    idx = LightGraphIndex()
    idx.add_document("d1", "Alice works at Google and uses TensorFlow.")
    assert len(idx.edges) > 0


def test_graph_retrieve_multi_hop():
    idx = LightGraphIndex()
    idx.add_document("d1", "Alice works at Google and uses TensorFlow.")
    idx.add_document("d2", "Bob develops PyTorch at Meta.")
    idx.add_document("d3", "Google and Meta collaborate on AI.")
    results = idx.graph_retrieve("Google TensorFlow")
    assert results and results[0] == "d1"  # 直接命中 d1


def test_graph_retrieve_finds_related():
    idx = LightGraphIndex()
    idx.add_document("d1", "Alice works at Google and uses TensorFlow.")
    idx.add_document("d2", "Google and Meta collaborate on AI.")
    results = idx.graph_retrieve("TensorFlow Google")
    assert "d1" in results or "d2" in results
