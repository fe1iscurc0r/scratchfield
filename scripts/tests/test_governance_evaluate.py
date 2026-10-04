"""scripts/system_governance.py 卷174 新增能力的单元测试。

覆盖（工单验收：evaluate ≥6 用例 + cpm ≥2 用例）：
- _collect_pollination_candidates：三模式采集 / 中文描述过滤 / 优先级去重 / 空目录不炸
- _decide_state：三态优先级 landed > claimed > paper
- cpm 关键路径链：相邻节点有依赖边 + 起点为图起点（es==0）

system_governance.py 不是包，用 importlib 按路径加载。
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "system_governance_under_test", PROJECT_ROOT / "scripts" / "system_governance.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gov = _load_module()


class TestCollectCandidates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "docs"
        self.tmp.mkdir()

    def test_table_bold_owner_repo_collected(self):
        (self.tmp / "轮A-授粉报告-2026-09-26.md").write_text(
            "| 项目 | ⭐ | 许可 | 一句话 | 分类 | 状态 |\n"
            "|---|---|---|---|---|---|\n"
            "| **PMEAL/porespy** | 422 | MIT | 多孔表征 | MCP | ✅ P0 |\n",
            encoding="utf-8")
        items = gov._collect_pollination_candidates(self.tmp)
        self.assertEqual([i["repo"] for i in items], ["porespy"])
        self.assertEqual(items[0]["priority"], "P0")

    def test_chinese_description_row_filtered(self):
        """中文描述粗体格（含 merge/keep 词组）不得被当项目名（真实误收案例）。"""
        (self.tmp / "轮B-授粉报告-2026-09-25.md").write_text(
            "| **归并阶段用 LLM 做 merge/keep 决策** | - | - | 描述 | - | P0 |\n",
            encoding="utf-8")
        self.assertEqual(gov._collect_pollination_candidates(self.tmp), [])

    def test_heading_with_repo_suffix_collected(self):
        (self.tmp / "轮C-授粉报告-2026-09-19.md").write_text(
            "### 4. lmfit ★1237（BSD-3-Clause ✅，PyPI 元数据确认）· lmfit/lmfit-py\n",
            encoding="utf-8")
        items = gov._collect_pollination_candidates(self.tmp)
        self.assertEqual([i["repo"] for i in items], ["lmfit-py"])

    def test_heading_single_name_collected(self):
        (self.tmp / "轮D-授粉报告-2026-09-19.md").write_text(
            "### 4. lmfit ★1237（BSD-3-Clause ✅）\n", encoding="utf-8")
        items = gov._collect_pollination_candidates(self.tmp)
        self.assertEqual([i["repo"] for i in items], ["lmfit"])

    def test_priority_dedupe_keeps_highest(self):
        """同项目多报告出现时保留最高优先级（P0 > P1）。"""
        (self.tmp / "轮E1-授粉报告.md").write_text(
            "| **PMEAL/porespy** | 1 | MIT | 一句话 | 学术 | ✅ P1 |\n", encoding="utf-8")
        (self.tmp / "轮E2-授粉报告.md").write_text(
            "| **PMEAL/porespy** | 2 | MIT | 一句话 | 学术 | ✅ P0 |\n", encoding="utf-8")
        items = gov._collect_pollination_candidates(self.tmp)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "P0")
        self.assertEqual(len(items[0]["reports"]), 2)

    def test_empty_docs_no_crash(self):
        empty = Path(tempfile.mkdtemp()) / "docs"
        empty.mkdir()
        self.assertEqual(gov._collect_pollination_candidates(empty), [])


class TestDecideState(unittest.TestCase):
    def test_landed_beats_claimed(self):
        state, ev = gov._decide_state("porespy", {"porespy"}, "porespy 派单文本", "log porespy")
        self.assertEqual(state, "landed")

    def test_claimed_when_only_workorder(self):
        state, ev = gov._decide_state("porespy", set(), "porespy 派单文本", "")
        self.assertEqual(state, "claimed")
        self.assertIn("派单", ev)

    def test_paper_when_no_evidence(self):
        state, ev = gov._decide_state("raspa3", set(), "", "")
        self.assertEqual(state, "paper")

    def test_empty_repo_is_paper(self):
        state, _ = gov._decide_state("", {"anything"}, "text", "log")
        self.assertEqual(state, "paper")


class TestCpmChain(unittest.TestCase):
    """卷174-C 验收：关键路径链相邻节点有依赖边 + 起点为图起点。"""

    def _chain_valid(self, mod) -> tuple[bool, str]:
        r = mod.cpm()
        if not r:
            return False, "cpm 返回 None"
        path = r["critical"]
        if len(path) < 2:
            return False, f"链过短: {path}"
        edges = set()
        for wid, (_n, _d, preds, _s) in mod.WORK_ITEMS.items():
            for p in preds:
                edges.add((p, wid))
        for a, b in zip(path, path[1:]):
            if (a, b) not in edges:
                return False, f"链上 {a}→{b} 无依赖边"
        # 起点须无前置（图起点）
        head_preds = [p for p, c in edges if c == path[0]]
        if head_preds:
            return False, f"链起点 {path[0]} 有前置 {head_preds}"
        return True, ""

    def test_real_workitems_chain_connected(self):
        ok, why = self._chain_valid(gov)
        self.assertTrue(ok, why)

    def test_synthetic_chain_through_done_bridge(self):
        """done 桥接项（dur=0）必须留在链上——修掉旧口径的断链缺陷。"""
        original = gov.WORK_ITEMS
        gov.WORK_ITEMS = {
            'A': ('根任务', 2, [], 'done'),
            'B': ('桥接done', 3, ['A'], 'done'),
            'C': ('桥接done', 1, ['B'], 'done'),
            'D': ('唯一欠账', 4, ['C'], 'todo'),
        }
        try:
            r = gov.cpm()
            self.assertEqual(r["critical"], ["A", "B", "C", "D"])
            self.assertEqual(r["total"], 4)
        finally:
            gov.WORK_ITEMS = original


class TestIslandExempt(unittest.TestCase):
    """卷175-A：孤岛豁免清单——research 标「数据产地」，--model 显示时带标注。"""

    def test_research_is_exempt(self):
        self.assertIn('research', gov.ISLAND_EXEMPT)
        self.assertIn('数据产地', gov.ISLAND_EXEMPT['research'])

    def test_exempt_does_not_remove_island(self):
        """豁免只是显示层标注，孤岛仍要在数据里出现（治理可见性不丢）。"""
        mods = {
            'research': {'py': 1, 'lines': 1, 'deps': set(), 'lazy_deps': set()},
            'apiserver': {'py': 1, 'lines': 1, 'deps': {'mcpserver'}, 'lazy_deps': set()},
            'mcpserver': {'py': 1, 'lines': 1, 'deps': set(), 'lazy_deps': set()},
        }
        r = gov.analyze(mods)
        self.assertIn('research', r['islands'])


if __name__ == "__main__":
    unittest.main()
