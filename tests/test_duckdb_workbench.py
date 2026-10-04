"""SPEC-02 Phase 3 验收测试：duckdb 材料数据分析工作台

验收口径：一份实验 CSV → 3 个标准分析 → Markdown 报告，全程 <1 分钟。
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import csv
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcpserver.material_science.duckdb_workbench import workbench  # noqa: E402

# 模拟生物质碳化实验数据（对齐 experiment_records_template.csv 口径，扩到 12 行保证统计意义）
SAMPLE_ROWS = [
    ["paper", "source_path", "precursor", "crosslinker", "koh_ratio", "heating_rate",
     "carbonization_temp", "holding_time", "conductivity", "surface_area", "porosity", "yield_rate"],
    ["own-record", "实验记录2026-08-10", "秸秆", "戊二醛", 4, 5, 750, 120, 10.8, 1350, 87, 33],
    ["own-record", "实验记录2026-08-10", "玉米芯", "戊二醛", 3, 5, 800, 120, 11.2, 1400, 88, 30],
    ["own-record", "实验记录2026-08-11", "秸秆", "柠檬酸", 3, 5, 700, 90, 8.4, 1100, 82, 38],
    ["own-record", "实验记录2026-08-11", "稻壳", "戊二醛", 4, 10, 800, 120, 12.1, 1500, 90, 28],
    ["own-record", "实验记录2026-08-12", "玉米芯", "柠檬酸", 2, 5, 750, 60, 7.6, 980, 78, 41],
    ["own-record", "实验记录2026-08-12", "稻壳", "柠檬酸", 3, 5, 850, 120, 13.5, 1550, 91, 26],
    ["own-record", "实验记录2026-08-13", "秸秆", "戊二醛", 5, 5, 800, 120, 12.8, 1480, 89, 27],
    ["own-record", "实验记录2026-08-13", "玉米芯", "戊二醛", 4, 5, 750, 90, 10.2, 1300, 85, 32],
    ["own-record", "实验记录2026-08-14", "稻壳", "戊二醛", 3, 5, 700, 120, 9.1, 1150, 83, 36],
    ["own-record", "实验记录2026-08-14", "秸秆", "柠檬酸", 4, 10, 850, 120, 14.0, 1600, 92, 25],
    ["own-record", "实验记录2026-08-15", "玉米芯", "柠檬酸", 3, 5, 800, 120, 11.0, 1380, 87, 31],
    ["own-record", "实验记录2026-08-15", "稻壳", "柠檬酸", 4, 10, 800, 90, 11.8, 1420, 88, 29],
]


class TestDuckdbWorkbench(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "test.duckdb"
        self.csv_path = self.tmp / "carbonization.csv"
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(SAMPLE_ROWS)

    def tearDown(self):
        self._tmp.cleanup()

    def test_import_csv_builds_table(self):
        """CSV 导入建表：行数/列数与源文件一致。"""
        result = workbench.import_file(str(self.csv_path), table="carbon", db_path=self.db_path)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["rows"], 12)
        self.assertIn("conductivity", result["columns"])
        self.assertIn("precursor", result["columns"])

    def test_import_failfast_on_missing_or_empty(self):
        """fail-fast：不存在的文件、空文件都必须报错而非静默建空表。"""
        r1 = workbench.import_file(str(self.tmp / "not_exist.csv"), db_path=self.db_path)
        self.assertFalse(r1["success"])

        empty = self.tmp / "empty.csv"
        empty.write_text("a,b,c\n", encoding="utf-8")
        r2 = workbench.import_file(str(empty), db_path=self.db_path)
        self.assertFalse(r2["success"], "零数据行必须报错")

    def test_readonly_query_guard(self):
        """只读护栏：DROP/INSERT/DELETE 一律拒绝。"""
        for sql in ("DROP TABLE carbon", "INSERT INTO carbon VALUES (1)", "DELETE FROM carbon"):
            r = workbench.run_query(sql, db_path=self.db_path)
            self.assertFalse(r["success"], sql)
        # SELECT 放行
        workbench.import_file(str(self.csv_path), table="carbon", db_path=self.db_path)
        r = workbench.run_query("SELECT COUNT(*) AS n FROM carbon", db_path=self.db_path)
        self.assertTrue(r["success"])
        self.assertEqual(r["rows"][0][0], 12)

    def test_three_standard_analyses(self):
        """三个标准分析全过：描述统计 / 分组对比 / 相关性。"""
        workbench.import_file(str(self.csv_path), table="carbon", db_path=self.db_path)
        results = workbench.run_standard_analyses("carbon", db_path=self.db_path)
        self.assertEqual(len(results), 3)
        for item in results:
            self.assertTrue(item["success"], item)

        overview = results[0]
        self.assertEqual(overview["total_rows"], 12)
        self.assertGreater(overview["numeric_stats"]["conductivity"]["mean"], 0)

        group = results[1]
        # 自动推断：第一个非数值列 paper/source_path 做分组列……这里显式指定更有意义
        group2 = workbench.analysis_group_compare("carbon", "precursor", "conductivity",
                                                  db_path=self.db_path)
        self.assertTrue(group2["success"])
        self.assertEqual(group2["best_group"], "稻壳")  # 稻壳均值 (12.1+13.5+9.1+11.8)/4=11.625 最高

        corr = results[2]
        # 自动推断取末两数值列（porosity ↔ yield_rate）：构造数据里产率越高孔隙率越低，强负相关
        self.assertLess(corr["pearson_r"], -0.9)
        self.assertEqual(corr["strength"], "强")

    def test_full_pipeline_under_one_minute(self):
        """验收口径：CSV → 导入 → 3 标准分析 → Markdown 报告，全程 <60s。"""
        t0 = time.monotonic()
        imp = workbench.import_file(str(self.csv_path), table="carbon", db_path=self.db_path)
        self.assertTrue(imp["success"])
        analyses = workbench.run_standard_analyses(
            "carbon", group_col="precursor", metric_col="conductivity", db_path=self.db_path)
        report_path = self.tmp / "report.md"
        rep = workbench.generate_report("carbon", analyses, output_path=str(report_path))
        elapsed = time.monotonic() - t0

        self.assertTrue(rep["success"])
        self.assertLess(elapsed, 60, f"管线耗时 {elapsed:.2f}s 超验收线")
        content = report_path.read_text(encoding="utf-8")
        for section in ("描述统计", "分组对比", "相关性分析"):
            self.assertIn(section, content)
        self.assertIn("稻壳", content)

    def test_register_tools_into_agent(self):
        """注册层：4 个工具注入 agent.tools。"""
        from mcpserver.material_science.duckdb_workbench import register_duckdb_tools

        class FakeAgent:
            tools = {}

        register_academic = FakeAgent()
        register_duckdb_tools(register_academic)
        for name in ("duckdb_import", "duckdb_query", "duckdb_analyze", "duckdb_report"):
            self.assertIn(name, register_academic.tools)


if __name__ == "__main__":
    unittest.main()
