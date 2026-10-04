import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
# -*- coding: utf-8 -*-
"""卷136 daily_paper_brief 测试：mtime 扫描 / 空结果 / 关键词匹配 / 打分 / 摘要。

运行：cd <repo> && python -m pytest tests/test_daily_paper_brief.py -q
（或 python tests/test_daily_paper_brief.py 直跑 unittest）
"""
import datetime as dt
import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import daily_paper_brief as dpb  # noqa: E402

DIGEST_MD = """# 2026年8月 arXiv 论文速览

## cond-mat.soft（软物质）——凝胶与流变

| ID | 标题缩写 | 核心贡献 |
|---|---|---|
| 2609.11111 | LigninHydrogelX | 木质素基水凝胶的流变学调控实现高强度与快速自修复 |
| 2609.22222 | UnrelatedQuantum | 量子比特纠错的新编码方案 |
| 2609.33333 | SolarEvapGel | 光热水凝胶太阳能蒸发速率提升 40% 的机理研究 |

## cs.AI（Agent）——其他

| ID | 标题缩写 | 核心贡献 |
|---|---|---|
| 2609.44444 | RFSDRScan | SDR 射频扫描 Agent 的频谱感知框架 |
"""


class TestScanNew(unittest.TestCase):
    def _setup(self, tmp: str) -> Path:
        # 造 docs/paper-roundN-test/digests/digest-*.md 结构
        d = Path(tmp) / "docs" / "paper-round0-test" / "digests"
        d.mkdir(parents=True)
        f = d / "digest-g1-1-test.md"
        f.write_text(DIGEST_MD, encoding="utf-8")
        return f

    def test_scan_new_matches_keywords(self):
        with TemporaryDirectory() as tmp:
            self._setup(tmp)
            # monkeypatch REPO_ROOT 指向 tmp
            old = dpb.REPO_ROOT
            dpb.REPO_ROOT = Path(tmp)
            try:
                today = dt.date.fromtimestamp(time.time()).isoformat()
                out_dir = Path(tmp) / "cache"
                res = dpb.scan_new(today=today, out_dir=out_dir)
            finally:
                dpb.REPO_ROOT = old
            ids = {e["paper_id"] for e in res}
            # 命中：lignin/hydrogel/rheology 一篇 + solar evaporation 一篇 + sdr/rf/radio 一篇
            self.assertIn("2609.11111", ids)
            self.assertIn("2609.33333", ids)
            self.assertIn("2609.44444", ids)
            self.assertNotIn("2609.22222", ids, "无关键词论文不应命中")
            # matched_keywords 正确性
            e1 = next(e for e in res if e["paper_id"] == "2609.11111")
            self.assertTrue(set(e1["matched_keywords"]) >= {"lignin", "hydrogel", "rheology"})
            # latest.json 落盘且可解析
            data = json.loads((out_dir / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data), 3)

    def test_scan_new_empty_ok(self):
        """空结果输出空数组不报错（工单原文）。"""
        with TemporaryDirectory() as tmp:
            dpb_path = Path(tmp) / "docs"
            dpb_path.mkdir()
            old = dpb.REPO_ROOT
            dpb.REPO_ROOT = Path(tmp)
            try:
                out_dir = Path(tmp) / "cache"
                res = dpb.scan_new(today="1999-01-01", out_dir=out_dir)  # 无当天文件
            finally:
                dpb.REPO_ROOT = old
            self.assertEqual(res, [])
            self.assertEqual(
                json.loads((out_dir / "latest.json").read_text(encoding="utf-8")), [])


class TestRank(unittest.TestCase):
    def test_rank_weights(self):
        """cond-mat.soft ×3 材料关键词 + sdr ×2 的加权排序。"""
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            (out_dir / "latest.json").write_text(json.dumps([
                {"paper_id": "1", "title": "t", "summary": "s",
                 "digest_path": "x", "section": "cond-mat.soft（软物质）",
                 "matched_keywords": ["lignin", "hydrogel"]},          # 2×3=6
                {"paper_id": "2", "title": "t", "summary": "s",
                 "digest_path": "x", "section": "cs.AI（Agent）",
                 "matched_keywords": ["lignin", "sdr"]},               # 1×1 + 1×2=3
                {"paper_id": "3", "title": "t", "summary": "s",
                 "digest_path": "x", "section": "materials science",
                 "matched_keywords": ["pyrolysis"]},                   # 1×2=2
            ], ensure_ascii=False), encoding="utf-8")
            ranked = dpb.rank(out_dir=out_dir)
            self.assertEqual([r["paper_id"] for r in ranked], ["1", "2", "3"])
            self.assertEqual(ranked[0]["score"], 6)
            self.assertEqual(ranked[1]["score"], 3)
            self.assertTrue((out_dir / "ranked.json").exists())


class TestSummarize(unittest.TestCase):
    def test_summarize_top_n_and_mode(self):
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            (out_dir / "ranked.json").write_text(json.dumps([
                {"paper_id": "2609.11111", "title": "L", "summary": "木质素水凝胶流变",
                 "digest_path": "x", "section": "s", "matched_keywords": ["lignin"]},
                {"paper_id": "2609.33333", "title": "S", "summary": "太阳能蒸发",
                 "digest_path": "x", "section": "s", "matched_keywords": ["solar evaporation"]},
            ], ensure_ascii=False), encoding="utf-8")
            p = dpb.summarize(top_n=1, out_dir=out_dir)
            txt = p.read_text(encoding="utf-8")
            self.assertIn("arXiv:2609.11111 — 木质素水凝胶流变", txt)
            self.assertIn("rule-based", txt)  # 无 DIGEST_API_KEY 时的模式声明
            self.assertNotIn("2609.33333", txt)  # top_n=1 只取第一


class TestCli(unittest.TestCase):
    def test_all_pipeline(self):
        """--all 一条龙：scan→rank→summarize 三产物齐备。"""
        import subprocess
        with TemporaryDirectory() as tmp:
            self._setup = None
            d = Path(tmp) / "docs" / "paper-round0-test" / "digests"
            d.mkdir(parents=True)
            (d / "digest-g1-1-test.md").write_text(DIGEST_MD, encoding="utf-8")
            cache = Path(tmp) / "cache"
            r = subprocess.run(
                [sys.executable, str(REPO / "scripts" / "daily_paper_brief.py"),
                 "--all", "--cache-dir", str(cache)],
                capture_output=True, text=True, timeout=120,
                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
            # 注意：--all 默认扫"今天"，tmp 里的文件 mtime 就是今天 → 应命中
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((cache / "latest.json").exists())
            self.assertTrue((cache / "ranked.json").exists())
            self.assertTrue((cache / "summary.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
