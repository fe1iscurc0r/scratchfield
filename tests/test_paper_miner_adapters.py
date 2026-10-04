"""paper_miner / biopred / build_dataset / 新 adapter 专项单元测试。

覆盖（全部离线，不依赖 Ollama/sklearn/xgboost/markitdown 真实可用）：
1. build_dataset 端到端：papers.db → carbonization.db 抽取 + schema 对齐
2. biopred 退化路径 + 描述解析 + 特征工程
3. extractor._json_from_text 稳健性（mock LLM 输出）
4. 3 个新 adapter healthcheck 在依赖缺失时返回 False 不崩溃
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 静默 healthcheck 里的 warning
import logging

logging.basicConfig(level=logging.ERROR)

from mcpserver.material_science import biopred, build_dataset
from mcpserver.paper_miner import db as pdb


def _seed_papers_db(path: str) -> None:
    """写入 3 条含温度+导电率的实验记录。"""
    x = pdb.init_db(path)
    x.insert_experiment({"paper": "t1", "precursor": "秸秆", "koh_ratio": 4,
                         "heating_rate": 5, "carbonization_temp": 800,
                         "holding_time": 120, "conductivity": 12.3})
    x.insert_experiment({"paper": "t2", "precursor": "木质素", "koh_ratio": 2,
                         "heating_rate": 10, "carbonization_temp": 600,
                         "holding_time": 60, "conductivity": 5.1})
    x.insert_experiment({"paper": "t3", "precursor": "玉米芯", "koh_ratio": 3,
                         "heating_rate": 5, "carbonization_temp": 900,
                         "holding_time": 180, "conductivity": 18.7})
    x.close()


class TestBuildDataset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.papers_db = os.path.join(self.tmp, "papers.db")
        self.out_db = os.path.join(self.tmp, "carbonization.db")
        _seed_papers_db(self.papers_db)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_end_to_end_extract(self):
        s = build_dataset.build_dataset(source_db=self.papers_db, out_db=self.out_db)
        self.assertTrue(s["ok"])
        self.assertEqual(s["written_rows"], 3)
        self.assertFalse(s["ready_to_train"])  # 3 < 50
        self.assertIn("warning", s)

    def test_output_schema_matches_biopred(self):
        build_dataset.build_dataset(source_db=self.papers_db, out_db=self.out_db)
        rows = biopred._load_dataset(self.out_db)
        self.assertEqual(len(rows), 3)
        # 字段名与 biopred._feature_vector 期望一致
        for rec in rows:
            self.assertIsNotNone(rec.get("carbonization_temp"))
            self.assertIsNotNone(rec.get("conductivity"))

    def test_missing_source_skips_gracefully(self):
        s = build_dataset.build_dataset(source_db="/nonexistent/papers.db", out_db=self.out_db)
        self.assertTrue(s["ok"])
        self.assertIn("跳过", s["sources"][0])

    def test_csv_merge(self):
        csv_path = os.path.join(self.tmp, "rec.csv")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("precursor,carbonization_temp,conductivity\n")
            f.write("壳聚糖,700,8.5\n")
            f.write("秸秆,800,15.0\n")
            f.write("生物质,500,\n")  # 缺导电率，应被过滤
        s = build_dataset.build_dataset(source_db=self.papers_db, csv_path=csv_path, out_db=self.out_db)
        self.assertEqual(s["written_rows"], 5)  # 3 文献 + 2 有效 CSV


class TestBiopred(unittest.TestCase):
    def test_parse_description_json(self):
        p = biopred._parse_description('{"precursor":"秸秆","koh_ratio":4,"temp":800}')
        self.assertEqual(p["precursor"], "秸秆")
        self.assertEqual(p["koh_ratio"], 4.0)
        self.assertEqual(p["carbonization_temp"], 800.0)

    def test_parse_description_text(self):
        p = biopred._parse_description("秸秆+KOH:4 800°C 保温120min 升温5/min")
        self.assertEqual(p["precursor"], "秸秆")
        self.assertEqual(p["koh_ratio"], 4.0)
        self.assertEqual(p["carbonization_temp"], 800.0)
        self.assertEqual(p["holding_time"], 120.0)
        self.assertEqual(p["heating_rate"], 5.0)

    def test_predict_empty_db_degrades(self):
        r = biopred.predict("秸秆 800°C", db_path="/nonexistent/x.db")
        self.assertFalse(r["ok"])
        self.assertIn("为空或缺失", r["error"])

    def test_suggest_insufficient_data_degrades(self):
        r = biopred.suggest(db_path="/nonexistent/x.db")
        self.assertFalse(r["ok"])
        self.assertIn("数据不足", r["error"])

    def test_precursor_fingerprint(self):
        self.assertEqual(biopred._precursor_fp("碱木质素"), 1.1)
        self.assertEqual(biopred._precursor_fp("未知物质"), biopred._DEFAULT_FP)

    def test_feature_vector_keys(self):
        # 确保 schema 对齐：_feature_vector 期望的 5 个键
        rec = {"precursor": "秸秆", "koh_ratio": 4, "heating_rate": 5,
               "carbonization_temp": 800, "holding_time": 120}
        v = biopred._feature_vector(rec)
        self.assertEqual(len(v), 5)


class TestExtractorJson(unittest.TestCase):
    def test_parse_bare_array(self):
        from mcpserver.paper_miner import extractor
        out = extractor._json_from_text('[{"precursor":"秸秆","temp":800}]')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["precursor"], "秸秆")

    def test_parse_fenced(self):
        from mcpserver.paper_miner import extractor
        out = extractor._json_from_text('```json\n[{"carbonization_temp":800}]\n```')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["carbonization_temp"], 800)

    def test_parse_empty(self):
        from mcpserver.paper_miner import extractor
        self.assertEqual(extractor._json_from_text("没有实验数据"), [])


class TestNewAdapterHealthchecks(unittest.TestCase):
    """依赖缺失时 healthcheck 应返回 False 且不抛异常。"""

    def test_markitdown_hc_no_crash(self):
        from mcpserver.adapters import markitdown
        # 无论 markitdown 是否安装，都不应抛异常
        try:
            result = markitdown.healthcheck()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"markitdown.healthcheck 抛异常: {e}")

    def test_llm4decompile_hc_no_crash(self):
        from mcpserver.adapters import llm4decompile
        try:
            result = llm4decompile.healthcheck()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"llm4decompile.healthcheck 抛异常: {e}")

    def test_paper_miner_hc_no_crash(self):
        from mcpserver.adapters import paper_miner
        try:
            result = paper_miner.healthcheck()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"paper_miner.healthcheck 抛异常: {e}")


class TestDatabaseRoundtrip(unittest.TestCase):
    def test_insert_and_query(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "p.db")
            x = pdb.init_db(db_path)
            x.insert_experiment({"paper": "p", "precursor": "秸秆",
                                 "carbonization_temp": 800, "conductivity": 10})
            rows = x.query_experiments(min_temp=700, min_conductivity=5)
            self.assertEqual(len(rows), 1)
            rows2 = x.query_experiments(min_temp=900)
            self.assertEqual(len(rows2), 0)
            x.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)