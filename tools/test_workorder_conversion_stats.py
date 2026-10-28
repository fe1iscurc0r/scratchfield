"""工单 238 · ``workorder_conversion_stats`` 的单元 + 集成测试。

放 ``tools/`` 下与模块同目录，沿用本仓惯例（``pyproject.toml`` 的 ``testpaths``
只含根 ``tests/``，模块测试用显式路径跑）：

    pytest tools/test_workorder_conversion_stats.py

集成用例会在 ``tmp_path`` 里现造一个真 git 仓库（受控提交时间）——
不碰本仓、不需要网络。
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from workorder_conversion_stats import (
    THEMES,
    Issue,
    _clip,
    build_issues,
    in_window,
    load_draft_themes,
    load_issued_workorders,
    main,
    month_key,
    normalize_issues,
    parse_period,
    rate_str,
    render_markdown,
    summarize,
)

git_only = pytest.mark.skipif(shutil.which("git") is None, reason="需要 git 可执行文件")


# ─────────────────────────── 纯函数：工单号识别 ───────────────────────────

def test_normalize_issues_w_style():
    # 实测本仓最常见写法：feat(w237): ... (#327)
    assert normalize_issues("feat(w237): 灵感素材库接入 RAG（biomass/sdr 双线） (#327)") == [237]


def test_normalize_issues_gongdan_style():
    assert normalize_issues("fix(ci): conftest find_spec 容错（工单224） (#230)") == [224]
    assert normalize_issues("工单202：情报管线整合周工单 (#161)") == [202]


def test_normalize_issues_juan_style():
    # 工单原文没写这种，但本仓实测存在（卷145/卷162/卷166/卷173/卷189）
    assert normalize_issues("卷162：领域包（Domain Pack）机制 (#89)") == [162]


def test_normalize_issues_wo_dash_style():
    assert normalize_issues("chore(repo): WO-237 收口") == [237]
    assert normalize_issues("Chore: wo-237 小写也认") == [237]


def test_normalize_issues_slash_list():
    # 实测：feat(卷189/190/192): ... (#135) 与 （工单220/221） (#222)
    assert normalize_issues("feat(卷189/190/192): 工具链三层优化 (#135)") == [189, 190, 192]
    assert normalize_issues("perf+audit: 冷启动基线 + 架构四线（工单220/221） (#222)") == [220, 221]


def test_normalize_issues_dedup_and_sort():
    assert normalize_issues("w237 + 工单237 + 卷237 都指同一张") == [237]


def test_normalize_issues_no_match():
    assert normalize_issues("chore(deps): bump vue from 3.5.42 to 3.5.43 (#160)") == []
    assert normalize_issues("") == []
    assert normalize_issues(None) == []


def test_normalize_issues_rejects_partial_digit_runs():
    # 4 位数字：\d{3}(?!\d) 不成立 ⇒ 不成号（防「试卷2026」这类误报）
    assert normalize_issues("试卷2026 年真题") == []
    # 下划线是词内字符 ⇒ \bw 不成立 ⇒ 不误认文件名里的 _w209_
    assert normalize_issues("tools/_w209_renderer_fix_deps.py") == []
    # 两位数的历史写法 w71-09 不满足 3 位 ⇒ 不误报
    assert normalize_issues("w71-09 知识图谱") == []


# ─────────────────────────── 纯函数：时间窗 / 期间 ───────────────────────────

def test_in_window():
    assert in_window(None, None, None) is False        # 无时刻一律不算入窗
    assert in_window(100, None, None) is True
    assert in_window(100, 100, 200) is True            # 闭区间
    assert in_window(200, 100, 200) is True
    assert in_window(99, 100, None) is False
    assert in_window(201, None, 200) is False


def test_parse_period_all():
    assert parse_period("all") == (None, None, "all")


def test_parse_period_days():
    since, until, label = parse_period("30d")
    assert until is None and label == "近 30 天"
    assert abs(int(time.time()) - 30 * 86400 - since) < 10


def test_parse_period_range():
    since, until, label = parse_period("2026-08-01..2026-08-31")
    assert label == "2026-08-01 ~ 2026-08-31"
    assert datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%d") == "2026-08-01"
    # 右端含当天最后一秒
    assert datetime.fromtimestamp(until, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") == "2026-08-31 23:59"


def test_parse_period_invalid():
    with pytest.raises(ValueError):
        parse_period("上个月")


def test_month_key():
    assert month_key(int(datetime(2026, 10, 14, tzinfo=timezone.utc).timestamp())) == "2026-10"


def test_rate_str():
    assert rate_str(0, 0) == "n/a"      # 零发放不除零
    assert rate_str(0, 4) == "0.0%"
    assert rate_str(1, 3) == "33.3%"


def test_clip_truncates_with_ellipsis():
    assert _clip("abc", 3) == "abc"
    assert _clip("abc", 9) == "abc"
    assert _clip("abcd", 3) == "ab…"    # 截断必须留省略号，别让人以为标题就这么长


# ─────────────────────────── 汇总 / 渲染（含零合入边界） ───────────────────────────

def _mk(number, issued_at, commits=0, merged=False, theme="other", title=""):
    return Issue(number=number, issued_at=issued_at, commits=commits, merged=merged,
                 theme=theme, title=title)


AUG = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
SEP = int(datetime(2026, 9, 15, tzinfo=timezone.utc).timestamp())


def test_summarize_zero_merge_boundary():
    """工单 §4.5：首次跑可能零合入 ⇒ 脚本必须兼容「全部 0 合入」。"""
    rep = summarize({190: _mk(190, SEP), 191: _mk(191, SEP, commits=3)}, "all")
    assert rep["overview"] == {"issued": 2, "merged": 0, "rate": 0.0, "commits_total": 3,
                               "v1_issued": 0, "v2_issued": 2}
    md = render_markdown(rep)
    assert "**0.0%**" in md
    # 未合入的工单照样进 Top 表，只是「已合入」列是 —（而非把整表打成「无数据」）
    assert "| WO-191 | other | 3 | — |" in md
    assert "| （无数据） | — | 0 | — | — |" not in md


def test_summarize_empty():
    rep = summarize({}, "all")
    assert rep["overview"]["issued"] == 0 and rep["overview"]["rate"] is None
    md = render_markdown(rep)
    assert "| （无数据） | 0 | 0 | n/a |" in md      # 表 2 无数据行
    assert "| （无数据） | — | 0 | — | — |" in md      # 表 4 无数据行
    assert "**n/a**" in md


def test_summarize_by_month_and_theme():
    issues = {190: _mk(190, AUG, theme="biomass", merged=True),
              191: _mk(191, SEP, theme="sdr")}
    rep = summarize(issues, "all")
    assert rep["by_month"]["2026-08"] == {"issued": 1, "merged": 1}
    assert rep["by_month"]["2026-09"] == {"issued": 1, "merged": 0}
    assert rep["by_theme"]["biomass"] == {"issued": 1, "merged": 1}
    assert rep["by_theme"]["sdr"] == {"issued": 1, "merged": 0}
    assert set(rep["by_theme"]) == set(THEMES)       # 6 条主题线齐全（缺的补 0）


def test_summarize_top_ordering():
    issues = {190: _mk(190, AUG, commits=2), 191: _mk(191, AUG, commits=7),
              192: _mk(192, AUG, commits=7)}
    rep = summarize(issues, "all")
    assert [r["number"] for r in rep["top"]] == [191, 192, 190]   # 提交数降序，同数按号升序


def test_summarize_v1_excluded_from_top_and_detail():
    """工单 §5：v1（≤189）只在汇总里出现，不单独统计。"""
    issues = {145: _mk(145, AUG, commits=9, merged=True), 190: _mk(190, AUG, commits=1)}
    rep = summarize(issues, "all")
    assert rep["overview"]["issued"] == 2                 # 汇总含 v1
    assert rep["overview"]["v1_issued"] == 1
    assert rep["overview"]["v2_issued"] == 1
    assert [r["number"] for r in rep["top"]] == [190]     # Top 不含 v1
    assert [r["number"] for r in rep["issues"]] == [190]  # 明细不含 v1
    rep2 = summarize(issues, "all", include_v1=True)
    assert [r["number"] for r in rep2["issues"]] == [145, 190]
    assert rep2["include_v1"] is True


def test_render_markdown_has_four_tables():
    rep = summarize({190: _mk(190, SEP, commits=2, merged=True, theme="biomass",
                              title="feat(w190): 完成")}, "近 30 天")
    md = render_markdown(rep)
    for header in ("## 表 1 · 总览", "## 表 2 · 月度转化",
                   "## 表 3 · 主题线维度", "## 表 4 · Top 5 高转化工单"):
        assert header in md
    assert "| WO-190 | biomass | 2 | ✅ | feat(w190): 完成 |" in md
    assert "漏斗 2.0 §5 目标对账" in md
    assert "期间：近 30 天" in md
    for theme in THEMES:                                  # 表 3 六个主题线都在
        assert f"| {theme} |" in md


def test_render_markdown_target_check_marks():
    ok = render_markdown(summarize({190: _mk(190, SEP, merged=True)}, "all"))
    assert "**达标**" in ok
    bad = render_markdown(summarize({190: _mk(190, SEP)}, "all"))
    assert "**未达标**" in bad


# ─────────────────────────── 集成：真 git 仓库 ───────────────────────────

def _run(repo: Path, *args: str, env: dict | None = None) -> None:
    full = dict(os.environ)
    full.update({"GIT_AUTHOR_NAME": "tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
                 "GIT_COMMITTER_NAME": "tester", "GIT_COMMITTER_EMAIL": "tester@example.com"})
    if env:
        full.update(env)
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=full)


def _commit(repo: Path, msg: str, stamp: str) -> None:
    """stamp 形如 ``2026-08-01T10:00:00``（UTC）。"""
    iso = f"{stamp} +0000"
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "--allow-empty", "-m", msg,
         env={"GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso})


def _add_workorder(repo: Path, num: int) -> None:
    (repo / f"TRAE_WORKORDER_PROMPT_AGENT_{num}.md").write_text(
        f"# 工单 {num}\n", encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _run(r, "init", "-q", "-b", "main")
    _run(r, "config", "user.name", "tester")
    _run(r, "config", "user.email", "tester@example.com")
    _run(r, "config", "commit.gpgsign", "false")
    return r


@git_only
def test_load_issued_workorders_and_window(repo):
    _add_workorder(repo, 190)
    _commit(repo, "docs: 发工单 190", "2026-08-01T10:00:00")
    _add_workorder(repo, 191)
    _commit(repo, "docs: 发工单 191", "2026-09-01T10:00:00")

    issues = load_issued_workorders(repo)
    assert set(issues) == {190, 191}
    assert issues[190].issued_at < issues[191].issued_at

    lo = issues[191].issued_at
    assert set(load_issued_workorders(repo, since=lo)) == {191}
    assert set(load_issued_workorders(repo, until=lo - 1)) == {190}
    assert set(load_issued_workorders(repo, since=lo, until=lo + 1)) == {191}


@git_only
def test_load_issued_workorders_deleted_then_readded_keeps_earliest(repo):
    _add_workorder(repo, 200)
    _commit(repo, "docs: 发工单 200", "2026-08-05T10:00:00")
    (repo / "TRAE_WORKORDER_PROMPT_AGENT_200.md").unlink()
    _commit(repo, "chore: 归档工单 200", "2026-08-20T10:00:00")
    _add_workorder(repo, 200)
    _commit(repo, "docs: 复活工单 200", "2026-09-20T10:00:00")

    issues = load_issued_workorders(repo)
    assert month_key(issues[200].issued_at) == "2026-08"   # 取最早那次 A 事件


@git_only
def test_workorder_glob_does_not_cross_directories(repo):
    """口径护栏：pathspec ``TRAE_..._AGENT_*.md`` 只命中仓库根 —— 子目录里的同名
    文件不算「发放」。本仓 ``workorders/archive/`` 确有此名文件（60 个），实测
    命中路径中 0 条含 ``/``。
    """
    sub = repo / "workorders" / "archive"
    sub.mkdir(parents=True)
    (sub / "TRAE_WORKORDER_PROMPT_AGENT_150.md").write_text("x", encoding="utf-8")
    _commit(repo, "docs: 子目录里的工单", "2026-08-03T10:00:00")
    assert load_issued_workorders(repo) == {}            # 子目录不算发放

    _add_workorder(repo, 150)                            # 根目录同名文件才算
    _commit(repo, "docs: 根目录发工单 150", "2026-09-03T10:00:00")
    issues = load_issued_workorders(repo)
    assert set(issues) == {150}
    assert month_key(issues[150].issued_at) == "2026-09"


@git_only
def test_load_draft_themes(repo):
    d = repo / "research" / "workorder_drafts"
    d.mkdir(parents=True)
    for name in ("WO-230-bio-A-experimental-design-and-execution.md",
                 "WO-232-sdr-rf-protocol-signalproc.md",
                 "WO-233-agent-agent-governance-audit.md",
                 "POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md"):
        (d / name).write_text("x", encoding="utf-8")
    _commit(repo, "docs: 落 drafts", "2026-10-11T10:00:00")
    assert load_draft_themes(repo) == {230: "biomass", 232: "sdr", 233: "agent"}


@git_only
def test_load_draft_themes_absent_dir_is_empty(repo):
    _add_workorder(repo, 190)
    _commit(repo, "docs: 无 drafts", "2026-09-01T10:00:00")
    assert load_draft_themes(repo) == {}


@git_only
def test_build_issues_end_to_end(repo):
    _add_workorder(repo, 145)
    _commit(repo, "docs: 发工单 145", "2026-08-02T10:00:00")
    _add_workorder(repo, 190)
    _commit(repo, "docs: 发工单 190", "2026-09-02T10:00:00")
    _add_workorder(repo, 191)
    _commit(repo, "docs: 发工单 191", "2026-09-03T10:00:00")
    _commit(repo, "feat(w190): 做完了 (#301)", "2026-09-10T10:00:00")
    _commit(repo, "refactor: 工单191 中间态（未合入）", "2026-09-11T10:00:00")
    _commit(repo, "chore(deps): bump vue (#302)", "2026-09-12T10:00:00")

    issues = build_issues(repo)
    assert issues[190].merged is True and issues[190].prs == {301}
    assert issues[190].commits == 1
    assert issues[191].merged is False and issues[191].commits == 1
    assert issues[145].commits == 0                        # 只发放、无相关提交
    assert issues[190].theme == "other"                    # 无 drafts ⇒ 关键词兜底/other


@git_only
def test_issuance_commit_not_counted_as_activity(repo):
    """发放提交的 subject 自带工单号（实测 182 条全带号）⇒ 不能算进活跃提交。"""
    _add_workorder(repo, 190)
    _commit(repo, "docs: 工单190——发单", "2026-09-02T10:00:00")
    issues = build_issues(repo)
    assert issues[190].commits == 0                       # 只有发放提交 ⇒ 0 活跃
    assert issues[190].title == "docs: 工单190——发单"     # 但 title 仍取它（唯一提及）
    assert issues[190].issued_commit != ""

    _commit(repo, "feat(w190): 干活 (#301)", "2026-09-10T10:00:00")
    issues = build_issues(repo)
    assert issues[190].commits == 1
    assert issues[190].merged is True and issues[190].prs == {301}


@git_only
def test_build_issues_slash_list_attributes_both(repo):
    _add_workorder(repo, 220)
    _add_workorder(repo, 221)
    _commit(repo, "docs: 发工单 220/221", "2026-09-01T10:00:00")
    _commit(repo, "perf+audit: 双线收口（工单220/221） (#222)", "2026-09-05T10:00:00")
    issues = build_issues(repo)
    assert issues[220].merged is True and issues[221].merged is True
    assert issues[220].prs == {222} and issues[221].prs == {222}


@git_only
def test_main_writes_md_and_json(repo, tmp_path):
    _add_workorder(repo, 190)
    _commit(repo, "docs: 发工单 190", "2026-09-02T10:00:00")
    _commit(repo, "feat(w190): 做完了 (#301)", "2026-09-10T10:00:00")

    out = tmp_path / "out"
    rc = main(["--repo", str(repo), "--period", "all",
               "--out-dir", str(out), "--name", "baseline"])
    assert rc == 0
    md = (out / "baseline.md").read_text(encoding="utf-8")
    data = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
    assert "## 表 4 · Top 5 高转化工单" in md
    assert data["overview"] == {"issued": 1, "merged": 1, "rate": 100.0,
                                "commits_total": 1, "v1_issued": 0, "v2_issued": 1}


@git_only
def test_main_writes_lf_only(repo, tmp_path):
    """回归：Windows 上 ``Path.write_text`` 默认把 ``\\n`` 翻成 ``\\r\\n`` ⇒ 报告
    blob 变 CRLF，与本仓 LF 基线不符（经 Git Data API 交付时不会自动归一化）。
    """
    _add_workorder(repo, 190)
    _commit(repo, "docs: 发工单 190", "2026-09-02T10:00:00")
    out = tmp_path / "out"
    assert main(["--repo", str(repo), "--period", "all",
                 "--out-dir", str(out), "--name", "lf"]) == 0
    for name in ("lf.md", "lf.json"):
        blob = (out / name).read_bytes()
        assert blob.count(b"\r\n") == 0, f"{name} 出现 CRLF"
        assert blob.count(b"\n") > 0, f"{name} 是空文件"


@git_only
def test_main_json_only_writes_no_md(repo, tmp_path):
    _add_workorder(repo, 190)
    _commit(repo, "docs: 发工单 190", "2026-09-02T10:00:00")
    out = tmp_path / "out"
    assert main(["--repo", str(repo), "--period", "all", "--json-only",
                 "--out-dir", str(out), "--name", "j"]) == 0
    assert (out / "j.json").is_file()
    assert not (out / "j.md").exists()


@git_only
def test_main_theme_filter(repo, tmp_path):
    d = repo / "research" / "workorder_drafts"
    d.mkdir(parents=True)
    (d / "WO-230-bio-A-x.md").write_text("x", encoding="utf-8")
    (d / "WO-232-sdr-B-y.md").write_text("x", encoding="utf-8")
    for num in (230, 232):
        _add_workorder(repo, num)
    _commit(repo, "docs: 发工单 230/232", "2026-09-02T10:00:00")
    out = tmp_path / "out"
    assert main(["--repo", str(repo), "--period", "all", "--theme", "biomass",
                 "--out-dir", str(out), "--name", "bio"]) == 0
    data = json.loads((out / "bio.json").read_text(encoding="utf-8"))
    assert data["overview"]["issued"] == 1
    assert [r["number"] for r in data["issues"]] == [230]
