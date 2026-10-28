#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_to_workorder.py 的单元测试（工单 240）。

跑法（模块测试放模块旁，`testpaths` 只含根 tests/，故须显式给路径）：
    python -m pytest tools/test_cron_to_workorder.py -q
"""

from __future__ import annotations

import datetime as _dt
import json
import os

import cron_to_workorder as cw
import pytest

DAY = _dt.date(2026, 10, 14)

SWEEP_MD = """# GitHub 扫货日报 · 2026-10-13

## 🆕 本日新发现

| ⭐ | 许可 | 项目 | 状态 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 3017 | MIT | samugit83/redamon | 🆕 新 | 开源自托管 AI 渗透测试框架 — MCP server 编排 |
| 1142 | Apache-2.0 | wbopan/cui | ❌ | ~~已归档 Hermes TUI 参考~~ |
| 512 | MIT | nopoc/plainthing | 🆕 新 | 一个纯描述性句子，没有入口词 |

## 🏆 Top 3 推荐

| ⭐ | 许可 | 项目 | 状态 | 一句话 |
|---|---|---|---|---|
| 698 | MIT | Playa-Cyrene/Cyrene-Agent | 🆕 新 | Live2D 桌宠 engine + 角色化记忆 memory 分层 |
| 11 | GPL-3.0 | bad/gplproject | 🆕 新 | copyleft 工具库 |

## 🚫 本轮明确排除

| 项目 | 排除原因 |
|---|---|
| `foo/bar` | GPL-3.0 copyleft |
"""

DIGEST_MD = """# Digest — G1 Round2 · 2026-08-30

| # | ID | 核心摘要 |
|---|----|----------|
| 1 | `2608.22958v1` | 木质素热解 pyrolysis 的机器学习势能引擎实现 |
| 2 | `2608.21111v1` | 一句没有入口词纯描述 |
"""


def _src(cron_id: str = "a37ffecbd730") -> cw.CronSource:
    return cw.SOURCE_BY_ID[cron_id]


# ------------------------------------------------------------ parse_period / 窗口
@pytest.mark.parametrize(
    ("period", "expect"),
    [("24h", 86400), ("48h", 172800), ("7d", 604800), ("7D", 604800), ("ALL", None), ("all", None)],
)
def test_parse_period_ok(period, expect):
    assert cw.parse_period(period) == expect


@pytest.mark.parametrize("bad", ["", "24", "1w", "0h", "-3d", "24x", "h"])
def test_parse_period_rejects(bad):
    with pytest.raises(ValueError):
        cw.parse_period(bad)


@pytest.mark.parametrize(("secs", "days"), [(None, None), (86400, 1), (86399, 1), (86401, 2), (129600, 2), (604800, 7)])
def test_window_days(secs, days):
    assert cw.window_days(secs) == days


def test_file_ref_date_prefers_filename_over_mtime(tmp_path):
    f = tmp_path / "GitHub-Sweep-Daily-2020-01-02.md"
    f.write_text("x", encoding="utf-8")
    assert cw.file_ref_date(f, mtime_fallback=True) == _dt.date(2020, 1, 2)


def test_file_ref_date_undated_uses_mtime_only_when_allowed(tmp_path):
    f = tmp_path / "no-date-here.md"
    f.write_text("x", encoding="utf-8")
    assert cw.file_ref_date(f, mtime_fallback=False) is None
    assert cw.file_ref_date(f, mtime_fallback=True) == _dt.date.today()


def test_in_window_day_granularity(tmp_path):
    today_file = tmp_path / "a-2026-10-14.md"
    yday_file = tmp_path / "a-2026-10-13.md"
    old_file = tmp_path / "a-2026-10-01.md"
    for f in (today_file, yday_file, old_file):
        f.write_text("x", encoding="utf-8")
    assert cw.in_window(today_file, DAY, 1)
    assert not cw.in_window(yday_file, DAY, 1)
    assert cw.in_window(yday_file, DAY, 2)
    assert not cw.in_window(old_file, DAY, 7)
    assert cw.in_window(old_file, DAY, None)


def test_in_window_undated_rejected_when_mtime_fallback_off(tmp_path):
    """clone 场景回归：无日期文件名 + mtime 兜底关 ⇒ 不得入选（否则全仓误入）。"""
    f = tmp_path / "授粉点-统一.md"
    f.write_text("x", encoding="utf-8")
    assert not cw.in_window(f, DAY, 1, mtime_fallback=False)
    assert cw.in_window(f, DAY, 1, mtime_fallback=True)


# ------------------------------------------------------------ 文本工具
def test_clip_strips_markdown_noise():
    assert cw.clip("**粗** `code` ~~del~~  多空", 100) == "粗 code del 多空"


def test_clip_truncates_with_ellipsis():
    out = cw.clip("a" * 100, 10)
    assert len(out) == 10 and out.endswith("…")


def test_clip_noop_when_short():
    assert cw.clip("短句", 80) == "短句"


@pytest.mark.parametrize(
    ("text", "expect"),
    [("Hello World!", "hello-world"), ("a/b/c", "a-b-c"), ("---", "untitled"), ("", "untitled")],
)
def test_slugify(text, expect):
    assert cw.slugify(text) == expect


def test_slugify_respects_limit():
    assert len(cw.slugify("x" * 100, limit=10)) == 10


def test_slugify_keeps_chinese_title_usable():
    """纯中文标题 slug 化后为空 → 回退 untitled（不产出 `.md` 这种空名）。"""
    assert cw.slugify("中文标题") == "untitled"


# ------------------------------------------------------------ 关键词 / 门槛
def test_match_themes_multi():
    hits = cw.match_themes("MCP server 把 SDR 频谱数据接入 biomass 木质素流程")
    assert {"agent", "sdr", "biomass"} <= set(hits)


def test_match_themes_empty():
    assert cw.match_themes("nothing relevant here") == []


def test_match_poc_hints():
    assert "mcp" in cw.match_poc_hints("An MCP server toolkit")
    assert cw.match_poc_hints("纯描述 无入口") == []


def test_extract_slug_from_url():
    assert cw.extract_slug("see https://github.com/foo/bar for details") == "foo/bar"


def test_extract_slug_from_table_cell():
    assert cw.extract_slug("| 1 | MIT | owner/repo-x | 新 | desc |") == "owner/repo-x"


def test_extract_slug_rejects_repo_paths():
    """`docs/xxx` 这类仓内路径不得被当成 GitHub 仓库。"""
    assert cw.extract_slug("| 1 | MIT | docs/paper-round2-2026-08-30 | x | y |") == ""


def test_extract_slug_none():
    assert cw.extract_slug("| 1 | MIT | 没有 slug 的行 | x | y |") == ""


def test_extract_arxiv_pid():
    assert cw.extract_arxiv_pid("| 1 | `2608.22958v1` | 摘要 |") == "2608.22958v1"
    assert cw.extract_arxiv_pid("no pid") == ""


def test_row_desc_prefers_last_cell():
    assert cw.row_desc(["1", "标题", "一句话核心贡献够长"]) == "一句话核心贡献够长"


def test_row_desc_falls_back_to_longest():
    assert cw.row_desc(["1", "很长的标题内容在这里", "短"]) == "很长的标题内容在这里"


def test_looks_like_ref():
    assert cw.looks_like_ref("digest-g5-1a-2026-08-30.md")
    assert not cw.looks_like_ref("A real descriptive sentence")


@pytest.mark.parametrize(
    ("line", "section", "risk"),
    [
        ("| x | MIT | a/b | ❌ | archived |", "Top 3 推荐", "高"),
        ("| x | GPL-3.0 | a/b | 新 | toolkit |", "Top 3 推荐", "高"),
        ("| x | MIT | a/b | ⚠️已评估 | toolkit |", "Top 3 推荐", "中"),
        ("| x | MIT | a/b | 新 | toolkit |", "🏆 Top 3 推荐", "低"),
        ("| x | MIT | a/b | 新 | toolkit |", "🆕 本日新发现", "中"),
    ],
)
def test_assess_risk(line, section, risk):
    assert cw.assess_risk(line, section)[0] == risk


def test_detect_license():
    assert cw.detect_license("| 1 | MIT | a/b | 新 | x |") == "MIT"
    assert cw.detect_license("| 1 | Apache-2.0 | a/b | 新 | x |") == "Apache-2.0"
    assert cw.detect_license("| 1 | 无 | a/b | 新 | x |") == ""


# ------------------------------------------------------------ 双门槛抽取
def test_extract_candidates_gates_and_skips():
    cands = cw.extract_candidates(SWEEP_MD, _src(), "docs/GitHub-Sweep-Daily-2026-10-13.md")
    slugs = {c.slug for c in cands}
    assert "samugit83/redamon" in slugs
    # 无 PoC 入口词的行被门槛 A 丢弃
    assert "nopoc/plainthing" not in slugs
    # 删除线行被跳过
    assert "wbopan/cui" not in slugs
    # 排除段整段跳过
    assert "foo/bar" not in slugs


def test_extract_candidates_risk_low_in_recommend_section():
    cands = cw.extract_candidates(SWEEP_MD, _src(), "r.md", max_items=10)
    by_slug = {c.slug: c for c in cands}
    assert by_slug["Playa-Cyrene/Cyrene-Agent"].risk == "低"
    assert by_slug["bad/gplproject"].risk == "高"


def test_extract_candidates_respects_max_items():
    cands = cw.extract_candidates(SWEEP_MD, _src(), "r.md", max_items=1)
    assert len(cands) == 1


def test_extract_candidates_arxiv_only_table():
    """论文 digest 表无 slug 列，须靠 arXiv 编号满足门槛 B。"""
    cands = cw.extract_candidates(DIGEST_MD, _src("ad17cd9d341f"), "docs/digests/digest-g1.md")
    assert [c.slug for c in cands] == ["arXiv:2608.22958v1"]
    assert cands[0].theme == "biomass"


def test_extract_candidates_empty_on_plain_text():
    assert cw.extract_candidates("就是一段话，没有表格。", _src(), "r.md") == []


def test_extract_candidates_poc_marks_rule_mode():
    cands = cw.extract_candidates(SWEEP_MD, _src(), "r.md")
    assert all("[规则生成]" in c.poc for c in cands)
    assert all(c.mode == "rule-based" for c in cands)


# ------------------------------------------------------------ 去重 / 轮转
def test_dedupe_keeps_highest_score():
    a = cw.Candidate(_src(), "r1.md", "A", "e", "p", "agent", ("agent",), "中", "x", "foo/bar", "MIT", 3, "rule")
    b = cw.Candidate(_src(), "r2.md", "B", "e", "p", "agent", ("agent",), "中", "x", "FOO/BAR", "MIT", 9, "rule")
    uniq, dropped = cw.dedupe_candidates([a, b])
    assert dropped == 1
    assert len(uniq) == 1
    assert uniq[0].report_rel == "r2.md"


def test_pick_round_robin_covers_multiple_crons():
    ids = ["a37ffecbd730", "ad17cd9d341f"]
    mk = lambda cid, slug, s: cw.Candidate(  # noqa: E731
        _src(cid), "r.md", slug, "e", "p", "agent", ("agent",), "中", "x", slug, "MIT", s, "rule"
    )
    pool = [mk("a37ffecbd730", "a/1", 9), mk("a37ffecbd730", "a/2", 8), mk("ad17cd9d341f", "d/1", 1)]
    picked = cw.pick_round_robin(pool, ids, 2)
    assert {c.source.cron_id for c in picked} == set(ids)


def test_pick_round_robin_handles_empty_source():
    ids = ["a37ffecbd730", "67c43c05f468"]
    only = cw.Candidate(_src(ids[0]), "r.md", "t", "e", "p", "x", ("x",), "中", "y", "a/b", "MIT", 1, "rule")
    assert len(cw.pick_round_robin([only], ids, 5)) == 1


def test_pick_round_robin_keeps_score_order_within_source():
    ids = ["a37ffecbd730"]
    hi = cw.Candidate(_src(ids[0]), "r.md", "hi", "e", "p", "x", ("x",), "中", "y", "a/hi", "MIT", 9, "rule")
    lo = cw.Candidate(_src(ids[0]), "r.md", "lo", "e", "p", "x", ("x",), "中", "y", "a/lo", "MIT", 1, "rule")
    assert [c.title for c in cw.pick_round_robin([hi, lo], ids, 2)] == ["hi", "lo"]


# ------------------------------------------------------------ 源定义守卫
def test_sources_have_no_pattern_duplicates():
    seen: dict[str, str] = {}
    for src in cw.SOURCES:
        for pat in src.patterns:
            assert pat not in seen, f"pattern {pat!r} 同时属于 {seen[pat]} 与 {src.cron_id}"
            seen[pat] = src.cron_id


def test_find_overlaps_detects_shared_claim(tmp_path, monkeypatch):
    """构造两条源认领同一文件 ⇒ 必须被 find_overlaps 点名（回归：曾把候选错误归属）。"""
    shared = tmp_path / "docs" / "pollination" / "batches"
    shared.mkdir(parents=True)
    (shared / "GitHub扫货日报-2026-10-09.md").write_text("x", encoding="utf-8")
    fake = (
        cw.CronSource("s1", "n1", (), ("docs/pollination/batches/*.md",), "other"),
        cw.CronSource("s2", "n2", (), ("docs/pollination/batches/GitHub扫货日报-*.md",), "other"),
    )
    monkeypatch.setattr(cw, "SOURCES", fake)
    got = cw.find_overlaps(tmp_path)
    assert len(got) == 1
    assert got[next(iter(got))] == ["s1", "s2"]


def test_find_overlaps_real_sources_no_overlap_on_crafted_tree(tmp_path):
    tree = [
        "docs/GitHub-Sweep-Daily-2026-10-13.md",
        "docs/pollination/batches/GitHub扫货日报-2026-10-09.md",
        "docs/超限战轮39-x-授粉报告-2026-10-11.md",
        "docs/扫货-GHtrending-2026-09-02.md",
        "docs/paper-round2-2026-08-30/digests/digest-g1-1-2026-08-30.md",
    ]
    for rel in tree:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    assert cw.find_overlaps(tmp_path) == {}


def test_default_crons_are_first_five():
    expected = tuple(s.cron_id for s in cw.SOURCES[:5])
    assert expected == cw.DEFAULT_CRONS
    assert len(cw.DEFAULT_CRONS) == 5


def test_source_by_id_matches_sources():
    assert set(cw.SOURCE_BY_ID) == {s.cron_id for s in cw.SOURCES}


# ------------------------------------------------------------ 渲染 / 体积
def test_render_draft_is_same_shape_as_trae_workorder():
    cand = cw.extract_candidates(SWEEP_MD, _src(), "docs/x.md")[0]
    body = cw.render_draft(cand, "245", "2026-10-14")
    lines = body.splitlines()
    assert lines[0].startswith("# 工单 245 · ")
    for token in ("委托方：用户", "来源 cron", "来源报告", "## §0 · 摘录", "## §1 · 候选 PoC", "## §3 · 风险评估"):
        assert token in body, token


def test_render_draft_flags_auto_draft():
    cand = cw.extract_candidates(SWEEP_MD, _src(), "docs/x.md")[0]
    assert "自动草稿" in cw.render_draft(cand, "245", "2026-10-14")


def test_render_draft_under_2kb():
    cand = cw.extract_candidates(SWEEP_MD, _src(), "docs/x.md")[0]
    assert len(cw.render_draft(cand, "245", "2026-10-14").encode("utf-8")) <= cw.MAX_DRAFT_BYTES


def test_enforce_size_noop_when_small():
    assert cw.enforce_size("abc") == "abc"


def test_enforce_size_truncates_and_keeps_utf8_valid():
    body = "中文" * 2000
    out = cw.enforce_size(body, 500)
    assert len(out.encode("utf-8")) <= 500
    out.encode("utf-8").decode("utf-8")  # 不抛即 UTF-8 有效


def test_next_root_number(tmp_path):
    assert cw.next_root_number(tmp_path) == 1
    for n in (238, 240):
        (tmp_path / f"TRAE_WORKORDER_PROMPT_AGENT_{n}.md").write_text("x", encoding="utf-8")
    assert cw.next_root_number(tmp_path) == 241


def test_next_root_number_ignores_non_workorder_files(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "TRAE_WORKORDER_PROMPT_AGENT_abc.md").write_text("x", encoding="utf-8")
    assert cw.next_root_number(tmp_path) == 1


# ------------------------------------------------------------ e2e：scan
@pytest.fixture()
def fake_repo(tmp_path):
    root = tmp_path / "repo"
    for rel, body in [
        ("docs/GitHub-Sweep-Daily-2026-10-13.md", SWEEP_MD),
        ("docs/paper-round2-2026-08-30/digests/digest-g1-1-2026-08-30.md", DIGEST_MD),
    ]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    return root


def test_main_scan_end_to_end(fake_repo, tmp_path):
    out = tmp_path / "out"
    rc = cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--max-per-file", "2", "--max-total", "4", "--cand-base", "245",
    ])
    assert rc == 0
    drafts = sorted(p for p in out.glob("WO-*.md"))
    assert len(drafts) >= 3, "验收要求 ≥3 份草稿"
    for d in drafts:
        raw = d.read_bytes()
        assert len(raw) <= cw.MAX_DRAFT_BYTES, d.name
        assert raw.count(b"\r\n") == 0, f"{d.name} 行尾非 LF（Windows write_text 回归）"
        assert b"# \xe5\xb7\xa5\xe5\x8d\x95 " in raw  # 首行 `# 工单 `


def test_main_writes_lf_only_for_manifest(fake_repo, tmp_path):
    out = tmp_path / "out"
    assert cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14", "--output", str(out),
    ]) == 0
    man = out / "_manifest.json"
    assert man.exists()
    assert man.read_bytes().count(b"\r\n") == 0


def test_main_manifest_records_provenance(fake_repo, tmp_path):
    out = tmp_path / "out"
    cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--cand-base", "245",
    ])
    man = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
    assert man["day"] == "2026-10-14" and man["cand_base"] == 245
    assert set(man) >= {
        "day", "period", "model", "crons", "candidates_total", "candidates_deduped",
        "duplicates_dropped", "source_overlaps", "source_resolution", "drafts",
    }
    assert man["source_overlaps"] == []
    for d in man["drafts"]:
        assert set(d) >= {"file", "cron", "slug", "theme", "risk", "score", "bytes", "mode", "source_report"}
        assert d["bytes"] <= cw.MAX_DRAFT_BYTES


def test_main_scan_records_rule_mode_when_no_key(fake_repo, tmp_path, monkeypatch):
    monkeypatch.delenv("M3_API_KEY", raising=False)
    monkeypatch.delenv("DIGEST_API_KEY", raising=False)
    out = tmp_path / "out"
    cw.main(["--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14", "--output", str(out)])
    man = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
    assert all(d["mode"].startswith("rule-based") for d in man["drafts"])
    assert all("rule-based" in s for s in man["source_resolution"] if "候选 0" not in s)


def test_main_scan_unknown_cron_returns_2(fake_repo, tmp_path):
    rc = cw.main(["--repo", str(fake_repo), "--scan", "--crons", "deadbeef", "--output", str(tmp_path / "o")])
    assert rc == 2


def test_main_scan_24h_ignores_other_days(fake_repo, tmp_path):
    out = tmp_path / "out"
    rc = cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "24h", "--date", "2026-10-13",
        "--mtime-fallback", "off", "--output", str(out), "--max-total", "5",
    ])
    assert rc == 0
    man = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
    # 只有 2026-10-13 那份扫货日报入选
    assert all(d["source_report"].endswith("GitHub-Sweep-Daily-2026-10-13.md") for d in man["drafts"])


def test_main_scan_bad_period_exits_nonzero(fake_repo, tmp_path):
    with pytest.raises(ValueError):
        cw.main(["--repo", str(fake_repo), "--scan", "--period", "99w", "--output", str(tmp_path / "o")])


def test_main_no_mode_prints_help_returns_2(capsys):
    assert cw.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


# ------------------------------------------------------------ e2e：list-sources
def test_main_list_sources_reports_zero_hit_source(fake_repo, capsys):
    assert cw.main(["--repo", str(fake_repo), "--list-sources"]) == 0
    out = capsys.readouterr().out
    assert "67c43c05f468" in out
    assert "0 命中" in out
    assert "无源重叠" in out


# ------------------------------------------------------------ e2e：promote
@pytest.fixture()
def promoted(fake_repo, tmp_path):
    out = tmp_path / "out"
    cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--max-total", "3", "--cand-base", "245",
    ])
    draft = sorted(out.glob("WO-*.md"))[0]
    return fake_repo, draft


def test_promote_dry_run_writes_nothing(promoted):
    root, draft = promoted
    assert cw.main(["--repo", str(root), "--promote", str(draft), "--next-number", "245"]) == 0
    assert not (root / "TRAE_WORKORDER_PROMPT_AGENT_245.md").exists()


def test_promote_apply_renames_and_moves_to_root(promoted):
    root, draft = promoted
    assert cw.main(["--repo", str(root), "--promote", str(draft), "--next-number", "245", "--apply"]) == 0
    dst = root / "TRAE_WORKORDER_PROMPT_AGENT_245.md"
    assert dst.is_file()
    body = dst.read_text(encoding="utf-8")
    assert body.startswith("# 工单 245 · ")
    assert "委托方：用户" in body
    assert dst.read_bytes().count(b"\r\n") == 0
    assert draft.exists(), "promote 不删除原草稿（只复制提升）"


def test_promote_is_idempotent_and_refuses_overwrite(promoted):
    root, draft = promoted
    args = ["--repo", str(root), "--promote", str(draft), "--next-number", "245", "--apply"]
    assert cw.main(args) == 0
    before = (root / "TRAE_WORKORDER_PROMPT_AGENT_245.md").read_bytes()
    assert cw.main(args) == 3
    assert (root / "TRAE_WORKORDER_PROMPT_AGENT_245.md").read_bytes() == before


def test_promote_auto_next_number(promoted):
    root, draft = promoted
    (root / "TRAE_WORKORDER_PROMPT_AGENT_244.md").write_text("# 工单 244\n", encoding="utf-8")
    assert cw.main(["--repo", str(root), "--promote", str(draft), "--apply"]) == 0
    assert (root / "TRAE_WORKORDER_PROMPT_AGENT_245.md").is_file()


def test_promote_rejects_missing_draft(fake_repo):
    assert cw.main(["--repo", str(fake_repo), "--promote", str(fake_repo / "nope.md"), "--apply"]) == 2


def test_promote_rejects_non_workorder_first_line(fake_repo, tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# 随便一个标题\n", encoding="utf-8")
    assert cw.main(["--repo", str(fake_repo), "--promote", str(bad), "--apply"]) == 2


def test_promote_refuses_when_first_line_not_at_top_h1(promoted, tmp_path):
    root, _ = promoted
    bad = tmp_path / "leading.md"
    bad.write_text("\n\n# 工单 999 · 前面有空行\n", encoding="utf-8")
    assert cw.main(["--repo", str(root), "--promote", str(bad), "--apply"]) == 2


# ------------------------------------------------------------ happy-path 契约
def test_generated_draft_contains_all_required_fields(fake_repo, tmp_path):
    """工单 §3 验收：每份草稿含 来源 cron / 来源报告 / 摘录 / 候选 PoC / 风险评估。"""
    out = tmp_path / "out"
    cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--max-total", "4",
    ])
    for d in sorted(out.glob("WO-*.md")):
        body = d.read_text(encoding="utf-8")
        for token in ("来源 cron", "来源报告", "## §0 · 摘录", "## §1 · 候选 PoC", "## §3 · 风险评估"):
            assert token in body, f"{d.name} 缺 {token}"


def test_repo_relative_paths_in_manifest(fake_repo, tmp_path):
    out = tmp_path / "out"
    cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--max-total", "2",
    ])
    man = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
    for d in man["drafts"]:
        assert "\\" not in d["source_report"]
        assert not d["source_report"].startswith(fake_repo.name + "/")


def test_scan_output_outside_repo_does_not_crash(fake_repo, tmp_path, capsys):
    """`--output` 在仓外时 rel_to 必须优雅退回绝对路径（回归：曾抛 ValueError）。"""
    out = tmp_path / "elsewhere" / "auto"
    assert cw.main([
        "--repo", str(fake_repo), "--scan", "--period", "all", "--date", "2026-10-14",
        "--output", str(out), "--max-total", "1",
    ]) == 0
    assert "valueerror" not in capsys.readouterr().out.lower()


def test_no_cron_module_import_of_network_libs():
    """策略守卫：模块不得在顶层 import litellm / requests（LLM 走惰性导入）。"""
    src = (cw.Path(os.path.abspath(cw.__file__))).read_text(encoding="utf-8")
    head = src.split('"""', 2)[2] if src.count('"""') >= 2 else src
    for forbidden in ("\nimport litellm", "\nimport requests", "\nimport openai"):
        assert forbidden not in head, f"顶层出现了 {forbidden!r}"
