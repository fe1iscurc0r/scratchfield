# -*- coding: utf-8 -*-
"""卷142 测试：文本→KG 抽取管线（prompt 模板 + 抽取 + 归一化 + 与139联通）。

全部离线：LLM 用假函数注入，零 API key、零网络。
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]  # 适配器目录 → 仓库根
sys.path.insert(0, str(REPO))

from mcpserver.graph_memory_adapter import kg_extract as kx  # noqa: E402
from mcpserver.graph_memory_adapter.engine import GraphMemory, reset_graph_memory  # noqa: E402

# ---- 假 LLM：按 prompt 里的特征词路由到固定应答，模拟小模型的典型输出 ----

FAKE_CONCEPTS = """```json
[
  {"entity": "木质素纳米颗粒", "importance": 5, "category": "object", "aliases": ["Lignin NPs"]},
  {"entity": "水凝胶", "importance": 5, "category": "object", "aliases": []},
  {"entity": "γ 射线交联", "importance": 4, "category": "event", "aliases": []},
  {"entity": "溶胀率", "importance": 3, "category": "condition", "aliases": []},
  {"entity": "称重法", "importance": 2, "category": "不存在的类别", "aliases": []}
]
```"""

FAKE_RELATIONS = """[
  {"node_1": "木质素纳米颗粒", "node_2": "水凝胶", "edge": "produced_by"},
  {"node_1": "γ 射线交联", "node_2": "水凝胶", "edge": "produced_by"},
  {"node_1": "溶胀率", "node_2": "称重法", "edge": "measured_by"},
  {"node_1": "溶胀率", "node_2": "水凝胶", "edge": "has_property"},
  {"node_1": "幽灵节点", "node_2": "水凝胶", "edge": "references"},
  {"node_1": "溶胀率", "node_2": "称重法", "edge": "duplicate_of_above"}
]"""


def fake_llm(system: str, user: str) -> str:
    """按 system prompt 的特征词分流（先判关系，再判概念）。

    注意顺序：关系 prompt 里也含"原子化"（层级的"尽可能原子化"），
    所以必须先按关系独有标记（node_1 / 网络图构建器）判断。
    """
    if "node_1" in system or "网络图构建器" in system:
        return FAKE_RELATIONS
    if "importance" in system or "关键概念" in system:
        return FAKE_CONCEPTS
    raise AssertionError(f"未识别的 prompt: {system[:60]}")


class TestPrompts(unittest.TestCase):
    def test_prompt_files_load(self):
        for name in ("kg-extract-concept.md", "kg-extract-relation.md"):
            p = kx.load_prompt(name)
            self.assertTrue(p["system"].strip(), f"{name} 的 system prompt 不应为空")
        concept = kx.load_prompt("kg-extract-concept.md")["system"]
        for cat in ("event", "condition", "organisation"):
            self.assertIn(cat, concept, "类别词表应写在 prompt 里")

    def test_prompt_missing_raises(self):
        with self.assertRaises(kx.ExtractError):
            kx.load_prompt("nope.md")


class TestJsonTolerance(unittest.TestCase):
    def test_fence_and_plain(self):
        self.assertEqual(len(kx._extract_json_array("```json\n[{\"a\":1}]\n```")), 1)
        self.assertEqual(len(kx._extract_json_array('[{"a":1}]')), 1)

    def test_prose_around_json(self):
        raw = '好的，这是结果：[{"a":1},{"b":2}] 以上。'
        self.assertEqual(len(kx._extract_json_array(raw)), 2)

    def test_invalid_raises(self):
        for bad in ("", "完全没有 JSON", "{不是数组}"):
            with self.assertRaises(kx.ExtractError):
                kx._extract_json_array(bad)


class TestExtractConcepts(unittest.TestCase):
    def test_happy_path_and_category_whitelist(self):
        cs = kx.extract_concepts("任意文本", fake_llm)
        self.assertEqual(len(cs), 5)
        self.assertEqual(cs[0]["entity"], "木质素纳米颗粒")
        self.assertEqual(cs[0]["importance"], 5)
        self.assertEqual(cs[0]["aliases"], ["Lignin NPs"])
        # 白名单外的类别 → misc（不丢弃）
        self.assertEqual(cs[-1]["category"], "misc")

    def test_empty_text(self):
        self.assertEqual(kx.extract_concepts("", fake_llm), [])
        self.assertEqual(kx.extract_concepts("   ", fake_llm), [])

    def test_importance_clamped(self):
        def llm(s, u):
            return '[{"entity":"X","importance":99,"category":"concept"}]'
        self.assertEqual(kx.extract_concepts("t", llm)[0]["importance"], 5)


class TestExtractRelations(unittest.TestCase):
    def test_endpoints_must_be_known_and_dedup(self):
        ents = ["木质素纳米颗粒", "水凝胶", "γ 射线交联", "溶胀率", "称重法"]
        rels = kx.extract_relations("文本", ents, fake_llm)
        # 边是无向对（端点顺序不该影响判定）→ 用 frozenset 比较
        pairs = [frozenset((r["node_1"], r["node_2"])) for r in rels]
        self.assertNotIn(frozenset(("幽灵节点", "水凝胶")), pairs,
                         "端点不在清单里的边应被丢弃")
        # 溶胀率-称重法 出现两次 → 只留一条
        self.assertEqual(pairs.count(frozenset(("称重法", "溶胀率"))), 1)
        self.assertEqual(len(rels), 4)

    def test_no_entities_no_call(self):
        called = []
        kx.extract_relations("文本", [], lambda s, u: called.append(1) or "[]")
        self.assertEqual(called, [], "无实体时不该调 LLM")


class TestNormalisation(unittest.TestCase):
    def test_exact_key_merge(self):
        am = kx.build_alias_map(["Lignin NPs", "lignin  nps", "水凝胶"])
        self.assertEqual(am["Lignin NPs"], am["lignin  nps"])
        self.assertEqual(am["水凝胶"], "水凝胶")

    def test_ascii_fuzzy_merge(self):
        am = kx.build_alias_map(["ops manager", "opsmanager"])
        self.assertEqual(am["ops manager"], am["opsmanager"],
                         "ASCII 名相似度 ≥0.9 应合并")

    def test_chinese_no_fuzzy(self):
        """中文不做模糊合并（误合并风险高）。"""
        am = kx.build_alias_map(["水凝胶", "气凝胶"])
        self.assertNotEqual(am["水凝胶"], am["气凝胶"])

    def test_canonical_is_longest(self):
        am = kx.build_alias_map(["ops manager", "Ops Managers"])
        self.assertEqual(am["ops manager"], "Ops Managers", "规范名取最长的原名")

    def test_deterministic(self):
        names = ["a b", "ab", "水凝胶"]
        self.assertEqual(kx.build_alias_map(names), kx.build_alias_map(names))

    def test_apply_alias_map_drops_self_loop(self):
        nodes = [{"name": "Lignin NPs", "type": "OBJECT"},
                 {"name": "ligninnps", "type": "OBJECT"}]
        edges = [{"source": "Lignin NPs", "predicate": "same_as", "target": "ligninnps"}]
        am = kx.build_alias_map([n["name"] for n in nodes])
        n2, e2 = kx.apply_alias_map(nodes, edges, am)
        self.assertEqual(len(n2), 1, "两节点应合并为一")
        self.assertEqual(e2, [], "合并后产生的自环应被丢弃")


class TestPipelineIntegration(unittest.TestCase):
    """端到端：抽取 → 归一 → 写入卷139 存储 → 多跳检索可召回。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mem = GraphMemory(Path(self._tmp.name) / "g.db")

    def tearDown(self):
        reset_graph_memory()
        self.mem.close()

    def test_extract_normalise_ingest_recall(self):
        # 1. 抽取
        payload = kx.extract_triples("木质素纳米颗粒经 γ 射线交联形成水凝胶，溶胀率用称重法测定。",
                                     fake_llm)
        self.assertTrue(payload["nodes"])
        self.assertTrue(payload["edges"])
        # 2. 归一（模拟 LLM 用简称的情况）
        alias_map = kx.build_alias_map([n["name"] for n in payload["nodes"]]
                                       + [a["alias"] for a in payload["aliases"]])
        nodes, edges = kx.apply_alias_map(payload["nodes"], payload["edges"], alias_map)
        # 3. 写入存储层（卷139 接口）
        r = self.mem.ingest_entities(nodes, edges, payload["aliases"], source_doc="paper-x")
        self.assertTrue(r["ok"])
        # 4. 多跳召回
        facts = self.mem.recall("水凝胶 溶胀率", hops=2, top_k=10)
        self.assertTrue(facts.triples, "写入后应能召回")
        preds = {t[1] for t in facts.triples}
        self.assertIn("has_property", preds)
        # 5. 别名也能命中
        facts2 = self.mem.recall("Lignin NPs 是什么", hops=2, top_k=10)
        self.assertTrue(facts2.triples, "别名应能作为检索种子")


if __name__ == "__main__":
    unittest.main(verbosity=2)
