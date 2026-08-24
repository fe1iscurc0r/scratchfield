# memory/contradiction 单元测试 — 矛盾检测 + supersedes 链（F-03）
#
# 覆盖（3 用例组）：
#   1. 同实体同属性不同值 → 矛盾检出 + supersedes 有向边 + 链可查
#   2. 不误报：不同属性 / 不同实体 / 相同值重复登记
#   3. 链式取代（v1←v2←v3）+ 幂等重复登记 + 迁移幂等（老库重建）
# 运行：python -m pytest NEKO/N.E.K.O/memory/test_contradiction.py -q
"""Tests for memory.contradiction (contradiction detection + supersedes chain)."""

from __future__ import annotations

import pytest

from memory.contradiction import ContradictionDetector
from memory.memory_graph import MemoryGraph


@pytest.fixture()
def graph(tmp_path):
    g = MemoryGraph(tmp_path / "graph.db")
    yield g
    g.close()


@pytest.fixture()
def detector(tmp_path, graph):
    d = ContradictionDetector(tmp_path / "facts.db", graph)
    yield d
    d.close()


class TestSameEntitySameAttributeDifferentValue:
    """用例一：同实体同属性不同值 → 矛盾 + supersedes 链。"""

    def test_contradiction_detected_and_edge_written(self, detector, graph):
        detector.register_fact("f1", "材料A", "密度", "1.2")
        conflicts = detector.register_fact("f2", "材料A", "密度", "1.5")
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["old_fact_id"] == "f1" and c["old_value"] == "1.2"
        assert c["new_fact_id"] == "f2" and c["new_value"] == "1.5"
        assert c["entity"] == "材料A" and c["attribute"] == "密度"
        # supersedes 有向边：f2 --supersedes--> f1（f2 是 source）
        sg = graph.get_subgraph("f2")
        sup = [e for e in sg["edges"] if e["type"] == "supersedes"]
        assert any(e["source"] == "f2" and e["target"] == "f1" for e in sup)
        # 反向不存在（非对称）
        assert not any(e["source"] == "f1" for e in sup)
        # 链查询：从 f2 可达被取代的 f1
        assert detector.get_supersede_chain("f2") == ["f1"]
        assert detector.get_supersede_chain("f1") == []

    def test_find_contradictions_by_entity_attribute(self, detector):
        detector.register_fact("f1", "材料A", "密度", "1.2")
        assert detector.find_contradictions("材料A", "密度") == []  # 单值不报
        detector.register_fact("f2", "材料A", "密度", "1.5")
        group = detector.find_contradictions("材料A", "密度")
        assert {g["fact_id"] for g in group} == {"f1", "f2"}
        assert {g["value"] for g in group} == {"1.2", "1.5"}


class TestNoFalsePositives:
    """用例二：非矛盾情形不误报。"""

    def test_different_attribute_no_conflict(self, detector):
        detector.register_fact("f1", "材料A", "密度", "1.2")
        conflicts = detector.register_fact("f2", "材料A", "熔点", "180")
        assert conflicts == []

    def test_different_entity_no_conflict(self, detector):
        detector.register_fact("f1", "材料A", "密度", "1.2")
        conflicts = detector.register_fact("f2", "材料B", "密度", "1.2")
        assert conflicts == []

    def test_same_value_reregistration_no_conflict(self, detector):
        """同值重复登记（不同 fact_id）→ 不构成矛盾，不写边。"""
        detector.register_fact("f1", "材料A", "密度", "1.2")
        conflicts = detector.register_fact("f9", "材料A", "密度", "1.2")
        assert conflicts == []
        assert detector.get_supersede_chain("f9") == []


class TestChainAndIdempotency:
    """用例三：链式取代 + 幂等。"""

    def test_star_chain_v3_supersedes_both(self, detector):
        """v1←v2←v3：v3 登记时同时取代 v1、v2（星形取代链）。"""
        detector.register_fact("v1", "服务器", "端口", "8000")
        detector.register_fact("v2", "服务器", "端口", "8001")
        conflicts = detector.register_fact("v3", "服务器", "端口", "8002")
        assert {c["old_fact_id"] for c in conflicts} == {"v1", "v2"}
        # 从 v3 沿 supersedes 出边可达 v1、v2（1 跳星形）
        chain = detector.get_supersede_chain("v3")
        assert set(chain) == {"v1", "v2"}
        # v2 只取代 v1（v3 是后登记者，不会出现在 v2 的链上）
        assert detector.get_supersede_chain("v2") == ["v1"]
        assert detector.get_supersede_chain("v1") == []

    def test_register_idempotent_same_fact(self, detector, graph):
        """重复登记同一事实：索引幂等、边幂等（不重复计数不炸）。"""
        detector.register_fact("f1", "实体", "属性", "a")
        detector.register_fact("f2", "实体", "属性", "b")
        again = detector.register_fact("f2", "实体", "属性", "b")  # 重复
        assert len(again) == 1  # 仍报告对 f1 的取代（f1 value 不同是客观矛盾）
        # 图上 f2→f1 的 supersedes 边只有一条（INSERT OR REPLACE 幂等）
        sg = graph.get_subgraph("f2")
        sup_edges = [e for e in sg["edges"]
                     if e["type"] == "supersedes" and e["source"] == "f2"]
        assert len(sup_edges) == 1
        assert detector.count() == 2  # 索引不膨胀

    def test_reopen_existing_db_migration_idempotent(self, tmp_path, graph):
        """迁移幂等：老库（已有数据）上重建 detector 不丢数据不炸。"""
        db = tmp_path / "facts.db"
        d1 = ContradictionDetector(db, graph)
        d1.register_fact("f1", "e", "a", "1")
        d1.close()
        d2 = ContradictionDetector(db, graph)  # 二次打开：CREATE IF NOT EXISTS 幂等
        try:
            assert d2.count() == 1
            conflicts = d2.register_fact("f2", "e", "a", "2")  # 老数据参与检测
            assert len(conflicts) == 1
        finally:
            d2.close()

    def test_empty_fields_rejected(self, detector):
        with pytest.raises(ValueError):
            detector.register_fact("", "e", "a", "1")
        with pytest.raises(ValueError):
            detector.register_fact("f", "e", " ", "1")
