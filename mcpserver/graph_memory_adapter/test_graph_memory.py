# -*- coding: utf-8 -*-
"""卷139 测试：轻量 KG 记忆（三表 + 递归 CTE）。

覆盖：写入/幂等、确定性 ID 归一、多跳检索、别名命中、空结果、
钳位、hook 注入、批量 ingest、子图导出、fail-fast。
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]  # 适配器目录 → 仓库根
sys.path.insert(0, str(REPO))

from mcpserver.graph_memory_adapter.adapter import GraphMemoryBridge  # noqa: E402
from mcpserver.graph_memory_adapter.engine import (  # noqa: E402
    GraphMemory,
    entity_id,
    normalise,
    reset_graph_memory,
)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "g.db"
        self.mem = GraphMemory(self.db)

    def tearDown(self):
        # 先清单例（bridge 走的单例可能仍持有句柄），再关直连实例
        reset_graph_memory()
        self.mem.close()


class TestIdentity(unittest.TestCase):
    def test_deterministic_entity_id(self):
        """同 type + 同归一名 → 同一 ID（跨文档自动归一，无需 ML）。"""
        a = entity_id("PERSON", "Ops Manager")
        b = entity_id("PERSON", "  ops   manager ")
        self.assertEqual(a, b, "归一后名相同应得到同一 ID")
        self.assertNotEqual(a, entity_id("ROLE", "Ops Manager"),
                            "不同类型应是不同节点")

    def test_normalise(self):
        self.assertEqual(normalise("  Ops   Manager "), "ops_manager")
        self.assertEqual(normalise(None), "")


class TestRemember(_Base):
    def test_remember_and_idempotent(self):
        r1 = self.mem.remember("陆墨", "delegates_to", "砚", source_doc="org")
        self.assertTrue(r1["ok"])
        self.assertTrue(r1["created"], "首次写入应标记 created")
        r2 = self.mem.remember("陆墨", "delegates_to", "砚", source_doc="org")
        self.assertFalse(r2["created"], "重复写应幂等（不产生重复边）")
        st = self.mem.stats()
        self.assertEqual(st["entities"], 2)
        self.assertEqual(st["relations"], 1, "重复写不应增加边数")

    def test_remember_empty_operand_fails_fast(self):
        for bad in (("", "r", "t"), ("e", "", "t"), ("e", "r", "")):
            r = self.mem.remember(*bad)
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "empty_operand")

    def test_description_backfill(self):
        """先无描述写入，后带描述写入 → 描述应补上（条件信息不丢）。"""
        self.mem.remember("水凝胶", "has_property", "溶胀率")
        self.mem.remember("水凝胶", "has_property", "溶胀率",
                          description="pH=7 时 340%")
        row = self.mem._conn.execute(
            "SELECT description FROM entities WHERE name='水凝胶'").fetchone()
        self.assertEqual(row["description"], "pH=7 时 340%")


class TestRecall(_Base):
    def _seed_chain(self):
        """造一条 3 跳链：A → B → C → D。"""
        self.mem.remember("甲", "knows", "乙", source_doc="d1")
        self.mem.remember("乙", "owns", "丙", source_doc="d1")
        self.mem.remember("丙", "part_of", "丁", source_doc="d2")

    def test_multihop_reaches_three_hops(self):
        self._seed_chain()
        f1 = self.mem.recall("甲", hops=1, top_k=10)
        self.assertEqual(len(f1.triples), 1, "1 跳只应看到 甲→乙")
        f3 = self.mem.recall("甲", hops=3, top_k=10)
        self.assertEqual(len(f3.triples), 3, "3 跳应看到整条链")
        preds = {t[1] for t in f3.triples}
        self.assertEqual(preds, {"knows", "owns", "part_of"})

    def test_hop_clamp_upper_bound(self):
        """hops 超上限（引擎层不钳，adapter 钳 5）——这里验引擎按参数走。"""
        self._seed_chain()
        f = self.mem.recall("甲", hops=2, top_k=10)
        self.assertEqual(len(f.triples), 2)

    def test_seed_via_alias(self):
        """别名命中也应能作为种子（名字没出现但别名出现）。"""
        self.mem.remember("邵长惠", "advises", "用户", source_doc="d3")
        self.mem.add_alias("邵长惠", "导师")
        f = self.mem.recall("导师的建议是什么", hops=2)
        self.assertTrue(f.triples, "别名'导师'应命中实体")

    def test_empty_query_and_no_match(self):
        """空提问 / 无匹配提问都要返回空结果且不报错。"""
        self._seed_chain()
        self.assertEqual(self.mem.recall("").triples, [])
        self.assertEqual(self.mem.recall("完全无关的量子色动力学").triples, [])

    def test_notes_carry_conditions(self):
        """条件挂在实体 description 上，检索必须带出（否则事实不完整）。"""
        self.mem.remember("报销", "approved_by", "财务",
                          description="单笔上限 5000 元", source_doc="policy")
        f = self.mem.recall("报销 谁批", hops=2)
        self.assertTrue(f.notes, "应带出实体注释")
        self.assertIn("5000", " ".join(d for _, d in f.notes))
        self.assertIn("其中", f.as_text())

    def test_as_text_shape(self):
        self._seed_chain()
        text = self.mem.recall("甲", hops=3).as_text()
        self.assertIn("甲 --[knows]--> 乙", text)
        self.assertIn("记忆：3 条事实", text)


class TestHook(_Base):
    def test_hook_empty_when_no_match(self):
        self.assertEqual(self.mem.hook_prompt("无匹配问题"), "")

    def test_hook_returns_injection_text(self):
        self.mem.remember("陆墨", "supervises", "砚", source_doc="org")
        text = self.mem.hook_prompt("陆墨管谁")
        self.assertIn("陆墨 --[supervises]--> 砚", text)

    def test_hook_truncates(self):
        for i in range(60):
            self.mem.remember("根", f"rel{i}", f"叶{i}", source_doc="big")
        text = self.mem.hook_prompt("根", hops=1, top_k=50, max_chars=300)
        self.assertLessEqual(len(text), 300)


class TestIngestAndExport(_Base):
    def test_ingest_entities(self):
        """卷142 抽取管线的落地接口：nodes + edges + aliases。"""
        r = self.mem.ingest_entities(
            nodes=[{"name": "陆墨", "type": "ROLE", "description": "主管"},
                   {"name": "砚", "type": "ROLE", "description": "工程干员"}],
            edges=[{"source": "陆墨", "predicate": "delegates_to", "target": "砚"}],
            aliases=[{"entity": "砚", "alias": "工程干员"}],
            source_doc="doc-x")
        self.assertTrue(r["ok"])
        st = self.mem.stats()
        self.assertEqual(st["entities"], 2, "自指边不应造出多余实体")
        self.assertEqual(st["relations"], 1, "自指边不应留在关系表")
        self.assertEqual(st["aliases"], 1)

    def test_export_subgraph(self):
        self.mem.remember("甲", "knows", "乙", source_doc="d")
        sub = self.mem.export_subgraph("甲", hops=1)
        self.assertEqual(len(sub["nodes"]), 2)
        self.assertEqual(len(sub["links"]), 1)
        self.assertEqual(sub["links"][0]["predicate"], "knows")


class TestBridge(_Base):
    def setUp(self):
        super().setUp()
        self.bridge = GraphMemoryBridge(db_path=str(self.db))

    def test_tools_happy_path(self):
        r = self.bridge.graph_memory_remember(
            entity="陆墨", relation="delegates_to", target="砚",
            aliases="主管", source_doc="org")
        self.assertEqual(r["status"], "ok")
        rec = self.bridge.graph_memory_recall(query="陆墨", hops=2)
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(len(rec["triples"]), 1)
        self.assertIsInstance(rec["text"], str)
        hook = self.bridge.graph_memory_hook(context="陆墨")
        self.assertTrue(hook["injected"])
        st = self.bridge.graph_memory_stats()
        self.assertEqual(st["entities"], 2)

    def test_tools_fail_fast(self):
        self.assertEqual(
            self.bridge.graph_memory_remember(entity="", relation="r", target="t")["status"],
            "error")
        self.assertEqual(
            self.bridge.graph_memory_recall(query="  ")["status"], "error")
        self.assertEqual(
            self.bridge.graph_memory_export(query="")["status"], "error")

    def test_tool_clamping(self):
        """hops 99 → 5；top_k 999 → 50（防一次拉爆上下文）。"""
        for i in range(8):
            self.bridge.graph_memory_remember(
                entity=f"n{i}", relation="next", target=f"n{i+1}")
        rec = self.bridge.graph_memory_recall(query="n0", hops=999, top_k=999)
        self.assertEqual(rec["hops"], 5)
        self.assertLessEqual(len(rec["triples"]), 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
