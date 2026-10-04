"""writing_pipeline 测试（SPEC-02 Phase 4 验收：选题到初稿一条龙）。

用 LUMO_WRITING_DIR / LUMO_DUCKDB_PATH 隔离到临时目录，不污染真实 %APPDATA%。
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import os
import tempfile
import unittest
from pathlib import Path

from mcpserver.material_science.writing_pipeline import bibtex, pipeline, templates

DEMO_CSV = """sample_id,date,material,method,temperature_c,duration_min,metric_primary
S001,2026-08-22,秸秆,碳化,750,60,10.2
S002,2026-08-22,秸秆,碳化,760,90,11.1
S003,2026-08-22,秸秆,碳化,770,120,11.5
S004,2026-08-22,玉米芯,碳化,750,90,12.4
S005,2026-08-22,玉米芯,碳化,800,120,13.0
S006,2026-08-22,玉米芯,碳化,820,150,12.7
"""


class WritingPipelineTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_env = {k: os.environ.get(k) for k in ("LUMO_WRITING_DIR", "LUMO_DUCKDB_PATH")}
        os.environ["LUMO_WRITING_DIR"] = str(Path(self.tmp.name) / "writing")
        os.environ["LUMO_DUCKDB_PATH"] = str(Path(self.tmp.name) / "workbench.duckdb")
        self.bib = Path(self.tmp.name) / "writing" / "references.bib"

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestBibtex(WritingPipelineTestBase):
    def test_add_load_find_roundtrip(self):
        r = bibtex.add_entry("smith2025", "Advanced Foams", "Smith, J. and Wu, L.",
                             2025, journal="Adv. Mater.", doi="10.1000/x", bib_path=self.bib)
        self.assertTrue(r["success"])
        # key 重复拒绝
        dup = bibtex.add_entry("smith2025", "Dup", "X", 2025, bib_path=self.bib)
        self.assertFalse(dup["success"])
        entries = bibtex.load_entries(self.bib)
        self.assertEqual(entries["smith2025"]["year"], "2025")
        self.assertEqual(entries["smith2025"]["doi"], "10.1000/x")
        hits = bibtex.find_entries("foam", self.bib)
        self.assertEqual(hits[0]["key"], "smith2025")

    def test_seed_idempotent(self):
        r1 = bibtex.seed_academic_refs(self.bib)
        self.assertEqual(len(r1["added"]), 5)
        r2 = bibtex.seed_academic_refs(self.bib)
        self.assertEqual(r2["added"], [])
        self.assertEqual(len(r2["skipped"]), 5)

    def test_cite_section_numbered(self):
        bibtex.seed_academic_refs(self.bib)
        cite = bibtex.cite_section(["thermo2024", "xiao2023slices", "no_such"], self.bib)
        self.assertFalse(cite["success"])  # 有 missing
        self.assertEqual(cite["missing"], ["no_such"])
        self.assertIn("thermo2024 -> [1]", cite["marks"])
        self.assertIn("Nature Communications", cite["markdown"])


class TestTemplates(unittest.TestCase):
    def test_render_keeps_unfilled(self):
        out = templates.render_template(templates.NATURE_ARTICLE, {"title": "T"})
        self.assertIn("# T", out)
        self.assertIn("{{abstract}}", out)

    def test_section_guidelines_cover_core_sections(self):
        for k in ("abstract", "introduction", "results", "methods", "discussion"):
            self.assertIn(k, templates.SECTION_GUIDELINES)


class TestPipeline(WritingPipelineTestBase):
    def test_draft_without_csv(self):
        r = pipeline.run_pipeline("生物质碳材料的制备方法优化", bib_path=self.bib)
        self.assertTrue(r["success"])
        draft = Path(r["draft_path"]).read_text(encoding="utf-8")
        for section in ("## Abstract", "## Introduction", "## Results",
                        "## Methods", "## References"):
            self.assertIn(section, draft)
        self.assertIn("ChEDL", draft)  # 种子引用的标题已挂进引言
        self.assertEqual(len(r["citations"]), 5)

    def test_draft_with_csv_runs_duckdb_chain(self):
        csv = Path(self.tmp.name) / "demo.csv"
        csv.write_text(DEMO_CSV, encoding="utf-8")
        r = pipeline.run_pipeline("生物质碳材料的制备方法优化", csv_path=str(csv),
                                  bib_path=self.bib)
        self.assertTrue(r["success"])
        self.assertIsNotNone(r["analysis_report"])
        self.assertTrue(Path(r["analysis_report"]).exists())
        draft = Path(r["draft_path"]).read_text(encoding="utf-8")
        self.assertIn("分组对比", draft)
        self.assertIn("相关性", draft)
        self.assertIn("玉米芯", draft)  # 最优组写进 Results
        # 一条龙耗时应远小于 1 分钟（SPEC Phase 3 验收线同样适用）
        self.assertLess(r["elapsed_s"], 30)

    def test_pipeline_handles_bad_csv_gracefully(self):
        r = pipeline.run_pipeline("x", csv_path=str(Path(self.tmp.name) / "missing.csv"),
                                  bib_path=self.bib)
        self.assertTrue(r["success"])  # 管线不中断，Results 节带失败说明
        draft = Path(r["draft_path"]).read_text(encoding="utf-8")
        self.assertIn("数据分析失败", draft)


class TestToolRegistration(WritingPipelineTestBase):
    def test_register_tools_into_agent(self):
        from mcpserver.material_science.writing_pipeline import register_writing_tools

        class _FakeAgent:
            tools = {}

        agent = _FakeAgent()
        register_writing_tools(agent)
        for name in ("writing_bibtex_add", "writing_bibtex_search", "writing_draft"):
            self.assertIn(name, agent.tools)
        # 走工具入口跑一遍：新增→检索→成稿
        self.assertTrue(agent.tools["writing_bibtex_add"]({
            "key": "t1", "title": "Test Title", "authors": "A. B.", "year": 2026,
        })["success"])
        self.assertEqual(agent.tools["writing_bibtex_search"]({"keyword": "test"})["count"], 1)
        draft = agent.tools["writing_draft"]({"topic": "demo 选题"})
        self.assertTrue(draft["success"])
        # 缺参护栏
        self.assertFalse(agent.tools["writing_draft"]({})["success"])


if __name__ == "__main__":
    unittest.main()
