"""graphrag 测试（SPEC-02 Phase 2 验收：图谱 + 向量 + 查询 <5s 返回路径与原文）。

快速用例用合成小语料 + 打桩嵌入（词元降级路径）；
最后一个用例跑真实 vault/academic 语料 + 真实 bge-small-zh（模型不可用则走降级，断言放宽）。
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from mcpserver.material_science.graphrag import importer, query, vector_index
from mcpserver.material_science.graphrag.store import GraphStore

MINI_VAULT = {
    "01-材料库/前驱体/木质素.md": (
        "# 木质素\n\n## 来源\n木质素是造纸黑液的主要成分，芳香族结构丰富。\n\n"
        "## 碳化制备\n木质素经 700-900 度碳化可得多孔碳，KOH 活化提升比表面积。\n"),
    "02-工艺/碳化工艺流程.md": (
        "# 碳化工艺流程\n\n## 升温程序\nN2 保护下以 5 度每分钟升温至目标温度，保温 2 小时。\n"),
    "03-表征/SEM扫描电镜.md": "# SEM\n\n## 形貌观察\n二次电子像观察孔隙形貌。\n",
}
MINI_ACADEMIC = {
    "thermo/MODEL_INTERFACE.md": "# thermo\n\n## 核心 API\nChemical 类查询物性。\n\n## 数据格式\n返回 dict。\n",
}


class GraphRagBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.vault = self.tmp / "vault"
        self.academic = self.tmp / "academic"
        for rel, content in MINI_VAULT.items():
            p = self.vault / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        for rel, content in MINI_ACADEMIC.items():
            p = self.academic / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        self.graph_dir = self.tmp / "graph"
        self.store = GraphStore(self.graph_dir)
        # 快速路径：嵌入打桩为不可用，走词元降级（真实模型用例自行恢复）
        self._orig = vector_index._embed_texts
        vector_index._embed_texts = lambda texts: None

    def tearDown(self):
        vector_index._embed_texts = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestImport(GraphRagBase):
    def test_import_builds_nodes_edges_communities(self):
        r = importer.import_corpus(self.store, self.vault, self.academic)
        self.assertTrue(r["success"])
        self.assertEqual(r["docs"], 4)
        types = self.store.stats()["node_types"]
        self.assertEqual(types["doc"], 4)
        self.assertGreater(types["section"], 4)
        # contains 边：每篇文档至少一条
        contains = [e for e in self.store.edges if e["relation"] == "contains"]
        self.assertGreaterEqual(len(contains), 4)
        # 共现边：木质素·碳化制备 与 碳化工艺流程 共享词元（碳化/升温等）
        mentions = [e for e in self.store.edges if e["relation"] == "mentions"]
        self.assertGreater(len(mentions), 0)
        self.assertGreaterEqual(r["communities"], 1)
        self.assertTrue((self.graph_dir / "graph.json").exists())

    def test_import_idempotent_rebuild(self):
        importer.import_corpus(self.store, self.vault, self.academic)
        n1 = len(self.store.nodes)
        importer.import_corpus(self.store, self.vault, self.academic)
        self.assertEqual(len(self.store.nodes), n1)  # 重建不累积


class TestQueryFallback(GraphRagBase):
    def test_query_returns_path_and_snippet(self):
        importer.import_corpus(self.store, self.vault, self.academic)
        vector_index.build_index(self.store)
        r = query.graph_query("木质素的碳化制备方法", graph_dir=self.graph_dir)
        self.assertTrue(r["success"])
        self.assertEqual(r["backend"], "token_fallback")
        self.assertLess(r["elapsed_s"], 5.0)
        top = r["results"][0]
        self.assertIn("碳化", top["section"] + top["path"])
        self.assertTrue(top["snippet"])          # 原文摘录
        self.assertTrue(top["source"].endswith(".md"))
        self.assertTrue(top["community_docs"])   # 社区导航

    def test_query_before_import_fails_fast(self):
        r = query.graph_query("随便问问", graph_dir=self.tmp / "empty")
        self.assertFalse(r["success"])
        self.assertIn("未构建", r["error"])


class TestToolRegistration(GraphRagBase):
    def test_register_tools_into_agent(self):
        from mcpserver.material_science.graphrag import register_graphrag_tools

        class _FakeAgent:
            tools = {}

        agent = _FakeAgent()
        register_graphrag_tools(agent)
        for name in ("graphrag_import", "graphrag_query", "graphrag_stats"):
            self.assertIn(name, agent.tools)
        os.environ["LUMO_GRAPHRAG_DIR"] = str(self.graph_dir)
        try:
            imp = agent.tools["graphrag_import"]({
                "vault_dir": str(self.vault), "academic_dir": str(self.academic)})
            self.assertTrue(imp["success"])
            q = agent.tools["graphrag_query"]({"question": "碳化工艺升温程序"})
            self.assertTrue(q["success"])
            stats = agent.tools["graphrag_stats"]({})
            self.assertTrue(stats["success"])
            # 缺参护栏
            self.assertFalse(agent.tools["graphrag_query"]({})["success"])
        finally:
            os.environ.pop("LUMO_GRAPHRAG_DIR", None)


class TestLiveCorpus(unittest.TestCase):
    """真实语料 + 真实嵌入（验收用例：5 秒内返回图谱路径 + 原文）。"""

    def test_real_corpus_query_under_5s(self):
        repo = Path(__file__).resolve().parents[1]
        if not (repo / "vault").exists():
            self.skipTest("vault 语料不存在")
        graph_dir = Path(tempfile.mkdtemp()) / "graph"
        try:
            store = GraphStore(graph_dir)
            r = importer.import_corpus(store)  # 仓内默认：vault + academic
            self.assertTrue(r["success"])
            self.assertGreaterEqual(r["docs"], 16)  # 12 篇笔记 + 16 个 MODEL_INTERFACE
            idx = vector_index.build_index(store)
            self.assertGreater(idx["indexed"], 50)

            t0 = time.monotonic()
            res = query.graph_query("木质素基碳材料的制备方法", graph_dir=graph_dir)
            elapsed = time.monotonic() - t0
            self.assertTrue(res["success"], res.get("error"))
            self.assertLess(elapsed, 5.0, f"查询耗时 {elapsed:.2f}s 超验收线")
            top = res["results"][0]
            # 命中内容应与碳材料制备相关（真实嵌入或词元降级都该命中）
            hay = top["section"] + top["snippet"] + top["path"]
            self.assertTrue(any(k in hay for k in ("碳", "木质素", "制备", "碳化")),
                            f"命中内容不相关: {hay[:120]}")
            self.assertTrue(top["snippet"])
        finally:
            shutil.rmtree(graph_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
