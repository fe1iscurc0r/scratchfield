"""卷179 验收测试：台账脚本的抽取逻辑（锚点断言）+ 硬约束行为。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> tools/ -> 仓库根
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load():
    spec = importlib.util.spec_from_file_location(
        "ledger_build_under_test", PROJECT_ROOT / "tools" / "ledger_build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lb = _load()


class TestPollinationExtraction:
    def test_round25_anchor_matches_source_table(self):
        """验收锚点：轮25 的 P0/P1 与 docs/超限战轮25-*.md 原文表格一致。

        工单验收文字写「P0=5/P1=4」，但原文表格实测 P0=4（RASPA3/porespy/
        PORMAKE/mofdscribe）、P1=4——**以原文为准**，本用例断言的就是与原文一致。
        """
        rows = [r for r in lb.scan_pollination(None) if r["round"] == "25"]
        assert len(rows) == 1, f"轮25 应恰有一份报告，实际 {len(rows)}"
        r = rows[0]
        assert r["p0"] == 4, f"轮25 P0 应为 4（原文表格 ✅P0 ×4），实测 {r['p0']}"
        assert r["p1"] == 4, f"轮25 P1 应为 4，实测 {r['p1']}"

    def test_extraction_failure_is_flagged_not_zero(self):
        """硬约束：未用「✅ Pn」格式的报告，三个数标 ⚠️ 而非静默出 0。"""
        rows = lb.scan_pollination(None)
        flagged = [r for r in rows if not r["extract_ok"]]
        assert flagged, "本仓存在非 ✅Pn 格式的旧报告，应有被标注项"
        for r in flagged:
            assert r["p0"] == "⚠️" and r["p1"] == "⚠️" and r["p2"] == "⚠️"

    def test_since_filter(self):
        all_rows = lb.scan_pollination(None)
        recent = lb.scan_pollination("2026-09-25")
        assert len(recent) < len(all_rows)
        assert all(r["date"] >= "2026-09-25" for r in recent if r["date"][0].isdigit())


class TestDailyExtraction:
    def test_backfill_json_counts(self):
        rows = lb.scan_daily(None)
        assert rows, "应有 gitee-stars-backfill JSON"
        assert all(isinstance(r["count"], int) or r["count"] == "⚠️ 抽取失败待人工" for r in rows)


class TestPapersLine:
    def test_unreachable_is_explicit_not_silent(self):
        """论文线路径不可达时必须显式标注（不静默跳过）。"""
        p = lb.scan_papers()
        if not p.get("reachable"):
            assert "⚠️" in p["note"]
        else:
            assert "digest_md" in p


class TestBuildOutput:
    def test_build_writes_three_sections(self, tmp_path):
        out = tmp_path / "ledger-test.md"
        lb.build(None, out)
        text = out.read_text(encoding="utf-8")
        for section in ("## 授粉线", "## 日报线", "## 论文线"):
            assert section in text
        assert "⚠️" in text  # 至少论文线或旧报告有标注
