#!/usr/bin/env python3
"""工单转化率闭环统计（漏斗 2.0 §2 动作 3 · 工单 238）。

把「工单发放 → Trae 完成 → 主仓合入」全链路打通，量化月度转化率与主题线
转化率 —— 这是「漏斗 2.0 是否真的在运转」的唯一判据。

口径（2026-10-14 对本仓实测校正；与工单原文的偏差已在下方逐条标注）：

- **工单发放**：仓库根目录 ``TRAE_WORKORDER_PROMPT_AGENT_<N>.md`` **首次加入**
  的提交时刻（``git log --diff-filter=A``）。实测该文件从不落在子目录（命中
  路径中 0 条含 ``/``），故 pathspec ``TRAE_WORKORDER_PROMPT_AGENT_*.md`` 已
  等价于「只匹配仓库根」，无需额外前缀。
- **Trae 完成 / 主仓合入**：commit subject 里出现工单号；带 ``(#PR)`` 的视为
  **经 PR 合入主仓**（本仓走 squash，一次合并 = 一个带 ``(#N)`` 的提交）。
- **工单号写法**：⚠️ 工单原文只写了 ``WO-[winsid]``，与实况不符。本仓实测
  **四种并存**：``wNNN`` / ``工单NNN`` / ``卷NNN`` / ``WO-NNN``，且支持斜杠
  列表（``工单220/221``、``卷189/190/192``）。
- **主题线**：``research/workorder_drafts/WO-<N>-<seg>-*.md`` 的 ``seg``
  （``bio`` → biomass）+ commit 关键词兜底。
- **时代**：v1 = 工单号 ≤ 189，v2 = ≥ 190（工单 238 §5）。v1 只进汇总表
  （总览 / 月度 / 主题线），**不进逐条明细与 Top 5**；``--include-v1`` 可放开。
- **CI 状态**：默认**不查**（纯离线）；``--with-ci`` 时走 GitHub REST。
- **相关提交数**：提到该工单号的提交数，**不含该工单的发放提交**（本仓发放提交
  的 subject 自带工单号 —— 实测 182 条发放事件全带号）。实测 0/182 发放提交带
  ``(#PR)`` ⇒ 它不会污染「合入」判定，只需从计数里剔除。

**已知低估（2026-10-14 实测，如实标注）**：本仓存在已合入 PR 的 subject 不含
工单号（如 ``#201`` / ``#203`` / ``#204`` 均属工单 204 任务三 却未带号）⇒ 本
脚本按「subject 含工单号」归因，会**低估**合入数。更准的归因需改用
``tools/workorder_graph.py`` 的「工单 ↔ 代码路径」反查（不在本工单范围）。

依赖：仅 ``git``（离线可跑）。``--with-ci`` 额外需网络 + 凭据。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# git log 里表示「当前提交时间戳」的哨兵（配合 --name-only 分组用）
COMMIT_MARK = "__C__"
WORKORDER_GLOB = "TRAE_WORKORDER_PROMPT_AGENT_*.md"
DRAFTS_DIR = "research/workorder_drafts/"
V2_ERA_MIN = 190          # v2 期起点（工单 238 §5：WO-190 起）
FUNNEL_TARGET_RATE = 50.0  # 漏斗 2.0 §5：月度转化率 ≥ 50%
FUNNEL_TARGET_MODULES = 30  # 漏斗 2.0 §5：6 个月内 ≥ 30 模块合入主仓

# 工单号：四种写法 + 斜杠列表（实测本仓并存）
_ISSUE_RE = re.compile(r"(?:\bw|工单卷?|卷|WO-)[ \t]*(\d{3}(?:/\d{3})*)(?!\d)", re.IGNORECASE)
_PR_RE = re.compile(r"\(#(\d+)\)")
_WORKORDER_FILE_RE = re.compile(r"TRAE_WORKORDER_PROMPT_AGENT_(\d+)\.md$")
_DRAFT_FILE_RE = re.compile(r"WO-(\d+)-([a-z0-9]+)-", re.IGNORECASE)

# 主题线：drafts 文件名的 seg → 报表主题（bio 归 biomass）
THEME_SEG_ALIAS = {
    "bio": "biomass",
    "biomass": "biomass",
    "sdr": "sdr",
    "agent": "agent",
    "esp32": "esp32",
    "pcb": "pcb",
    "other": "other",
}
THEMES = ["biomass", "sdr", "agent", "esp32", "pcb", "other"]
# commit 关键词兜底（仅当 drafts 无记录时使用）
THEME_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("biomass", ("biomass", "生物质", "木质素", "纤维素", "多酚", "材料线")),
    ("sdr", ("sdr", "频谱", "射频", "lora")),
    ("agent", ("智能体", "agent 治理", "多智能体", "agent治理")),
    ("esp32", ("esp32",)),
    ("pcb", ("pcb", "drc", "eda", "立创")),
]


def git(repo: Path, *args: str) -> str:
    """在 repo 上跑 git，返回 stdout（非 0 退出抛 RuntimeError）。"""
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {(r.stderr or '').strip()[:300]}")
    return r.stdout


def normalize_issues(text: str) -> list[int]:
    """从任意文本提取**全部**工单号（去重升序）；无则空列表。

    支持 ``wNNN`` / ``工单NNN`` / ``卷NNN`` / ``WO-NNN`` 及斜杠列表
    ``工单220/221``、``卷189/190/192``。
    """
    found: set[int] = set()
    for m in _ISSUE_RE.finditer(text or ""):
        for part in m.group(1).split("/"):
            if part.isdigit():
                found.add(int(part))
    return sorted(found)


def in_window(ts: int | None, since: int | None, until: int | None) -> bool:
    """时间戳是否落在 [since, until] 闭区间内（None 表示该端不设限）。"""
    if ts is None:
        return False
    if since is not None and ts < since:
        return False
    return not (until is not None and ts > until)


@dataclass
class Issue:
    """一张工单的闭环状态。"""

    number: int
    issued_at: int | None = None   # 首次加入仓库根的提交时刻（Unix 秒）
    issued_commit: str = ""        # 上述那个提交的短 hash（＝发放提交，不计入 commits）
    commits: int = 0               # 提到该工单号的提交数（时间窗内，**不含**发放提交）
    merged: bool = False           # 是否有带 (#PR) 的提交（经 PR 合入主仓）
    prs: set[int] = field(default_factory=set)
    theme: str = "other"
    title: str = ""
    pr_merged: dict[int, bool] = field(default_factory=dict)  # 仅 --with-ci 时填充

    @property
    def era(self) -> str:
        """v1（≤189）/ v2（≥190）—— 工单 238 §5 的时代划分。"""
        return "v1" if self.number < V2_ERA_MIN else "v2"


def load_issued_workorders(repo: Path, since: int | None = None,
                           until: int | None = None) -> dict[int, Issue]:
    """扫 ``--diff-filter=A`` 找每份工单文件**首次加入**仓库根的时刻。

    同一文件被「删了再加」会出现多条 A 事件 ⇒ 取最早时刻。含 ``/`` 的路径
    一律丢弃（防御性：确认工单文件不落子目录后，这条是纯保险）。

    同时记下该提交的短 hash（``issued_commit``）—— 本仓发放提交的 subject 常
    自带工单号（``docs: 工单227——授粉设计稿落地批``），若不去掉会把「相关提交
    数」虚增（实测 182 条发放事件全带号）。实测 0/182 发放提交带 ``(#PR)``，
    故它不会污染「合入」判定，只需从 ``commits`` 计数里剔除。
    """
    out = git(repo, "log", "--diff-filter=A", "--name-only",
              f"--format={COMMIT_MARK}%h%x1f%ct", "--", WORKORDER_GLOB)
    issues: dict[int, Issue] = {}
    cur_h, cur_ct = "", None
    for raw in out.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(COMMIT_MARK):
            h, _, ct = line[len(COMMIT_MARK):].partition("\x1f")
            if ct.isdigit():
                cur_h, cur_ct = h, int(ct)
            continue
        if "/" in line or cur_ct is None:
            continue
        m = _WORKORDER_FILE_RE.search(line)
        if not m:
            continue
        num = int(m.group(1))
        prev = issues.get(num)
        if prev is None or prev.issued_at is None or cur_ct < prev.issued_at:
            issues[num] = Issue(number=num, issued_at=cur_ct, issued_commit=cur_h)
    return {n: it for n, it in issues.items() if in_window(it.issued_at, since, until)}


def load_draft_themes(repo: Path, ref: str = "HEAD") -> dict[int, str]:
    """从 drafts 文件名解析 工单号 → 主题（``WO-230-bio-A-...`` → biomass）。"""
    out = git(repo, "ls-tree", "-r", "--name-only", ref, "--", DRAFTS_DIR)
    themes: dict[int, str] = {}
    for line in out.splitlines():
        m = _DRAFT_FILE_RE.search(line)
        if not m:
            continue
        theme = THEME_SEG_ALIAS.get(m.group(2).lower())
        if theme:
            themes[int(m.group(1))] = theme
    return themes


def guess_theme_from_text(text: str) -> str | None:
    """commit subject 关键词兜底判主题。"""
    low = (text or "").lower()
    for theme, kws in THEME_KEYWORDS:
        if any(k.lower() in low for k in kws):
            return theme
    return None


def load_commits(repo: Path) -> list[tuple[int, str, str]]:
    """全部提交 ``[(ctime, short_hash, subject)]``（新 → 旧）。

    时间过滤交给 Python（避免 ``--since`` 的日期解析歧义）。字段用 ``\\x1f``
    分隔，防止 subject 里出现 ``|`` 时被切错。
    """
    rows: list[tuple[int, str, str]] = []
    for line in git(repo, "log", "--format=%ct%x1f%h%x1f%s").splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3 and parts[0].strip().isdigit():
            rows.append((int(parts[0]), parts[1], parts[2]))
    return rows


def build_issues(repo: Path, since: int | None = None, until: int | None = None,
                 with_ci: bool = False) -> dict[int, Issue]:
    """组装工单闭环台账：发放 + 完成/合入 + 主题（单遍扫描，离线）。"""
    issues = load_issued_workorders(repo, since, until)
    themes = load_draft_themes(repo)
    for ct, h, subj in load_commits(repo):
        if not in_window(ct, since, until):
            continue
        for num in normalize_issues(subj):
            it = issues.setdefault(num, Issue(number=num))
            if h != it.issued_commit:      # 发放提交本身不算「完成活动」
                it.commits += 1
            m = _PR_RE.search(subj)
            if m:
                it.merged = True
                it.prs.add(int(m.group(1)))
            if not it.title:               # 新 → 旧扫描 ⇒ 记最新一次相关提交的 subject
                it.title = subj
    for num, it in issues.items():
        it.theme = themes.get(num) or guess_theme_from_text(it.title) or "other"
    if with_ci:
        fill_ci(repo, issues)
    return issues


def fill_ci(repo: Path, issues: dict[int, Issue]) -> None:
    """可选：走 GitHub REST 查 PR 是否已合并（需凭据 + 网络）。默认不调用。

    凭据读取路径与仓库既有脚本一致（``~/.workbuddy/mcp.json`` 的 github env）；
    任何网络/权限问题都静默跳过，不影响离线主流程。
    """
    import os
    import urllib.error
    import urllib.request

    cfg_path = Path(os.path.expanduser("~/.workbuddy/mcp.json"))
    if not cfg_path.is_file():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    env = cfg.get("mcpServers", {}).get("github", {}).get("env", {})
    tok = env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or env.get("GITHUB_TOKEN")
    if not tok:
        return
    slug = owner_repo(repo)
    for it in issues.values():
        for pr in sorted(it.prs):
            req = urllib.request.Request(f"https://api.github.com/repos/{slug}/pulls/{pr}")
            req.add_header("Authorization", f"Bearer {tok}")
            req.add_header("Accept", "application/vnd.github+json")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    d = json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError):
                continue
            it.pr_merged[pr] = d.get("merged_at") is not None


def owner_repo(repo: Path) -> str:
    """从 origin 推断 ``owner/repo``（失败退回本仓默认值）。"""
    try:
        url = git(repo, "remote", "get-url", "origin").strip()
    except RuntimeError:
        return "fe1iscurc0r/scratchpad"
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    return m.group(1) if m else "fe1iscurc0r/scratchpad"


def month_key(ct: int) -> str:
    return datetime.fromtimestamp(ct, tz=timezone.utc).strftime("%Y-%m")


def summarize(issues: dict[int, Issue], period_label: str,
              include_v1: bool = False) -> dict:
    """总览 + 月度 + 主题线 + Top 5 + 逐条明细。

    ``include_v1=False``（默认）时，v1 期（≤189）只进前三张汇总表，
    不进 Top 5 与逐条明细 —— 对应工单 238 §5。
    """
    issued = [it for it in issues.values() if it.issued_at is not None]
    merged = [it for it in issued if it.merged]
    per_issue = issued if include_v1 else [it for it in issued if it.era == "v2"]

    by_month: dict[str, dict[str, int]] = {}
    for it in issued:
        b = by_month.setdefault(month_key(it.issued_at or 0), {"issued": 0, "merged": 0})
        b["issued"] += 1
        b["merged"] += int(it.merged)

    by_theme: dict[str, dict[str, int]] = {t: {"issued": 0, "merged": 0} for t in THEMES}
    for it in issued:
        b = by_theme.setdefault(it.theme, {"issued": 0, "merged": 0})
        b["issued"] += 1
        b["merged"] += int(it.merged)

    top = sorted(per_issue, key=lambda x: (-x.commits, x.number))[:5]
    return {
        "period": period_label,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include_v1": include_v1,
        "overview": {
            "issued": len(issued),
            "merged": len(merged),
            "rate": round(len(merged) / len(issued) * 100, 1) if issued else None,
            "commits_total": sum(it.commits for it in issued),
            "v1_issued": sum(1 for it in issued if it.era == "v1"),
            "v2_issued": sum(1 for it in issued if it.era == "v2"),
        },
        "by_month": by_month,
        "by_theme": by_theme,
        "top": [_issue_row(it, full=False) for it in top],
        "issues": [_issue_row(it, full=True) for it in sorted(per_issue, key=lambda x: x.number)],
    }


def _clip(text: str, limit: int) -> str:
    """超长标题截断加省略号（避免读者以为「标题就长这样」）。"""
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _issue_row(it: Issue, full: bool) -> dict:
    row = {"number": it.number, "era": it.era, "theme": it.theme, "merged": it.merged,
           "commits": it.commits,
           "issued_date": (datetime.fromtimestamp(it.issued_at, tz=timezone.utc).strftime("%Y-%m-%d")
                           if it.issued_at else None)}
    if full:
        row.update({"issued_at": it.issued_at, "prs": sorted(it.prs), "title": _clip(it.title, 100)})
    else:
        row["title"] = _clip(it.title, 80)
    return row


def rate_str(merged: int, issued: int) -> str:
    return f"{merged / issued * 100:.1f}%" if issued else "n/a"


def render_markdown(rep: dict) -> str:
    """产出 4 张表（总览 / 月度转化 / 主题线维度 / Top 5 高转化工单）+ 口径说明。"""
    ov = rep["overview"]
    L: list[str] = []
    L.append("# 工单转化率闭环统计（漏斗 2.0 · 工单 238）\n")
    L.append(f"> 期间：{rep['period']} · 生成：{rep['generated_at']} · "
             "脚本：`tools/workorder_conversion_stats.py`\n")
    L.append("## 表 1 · 总览\n")
    L.append("| 指标 | 值 |")
    L.append("|---|---:|")
    L.append(f"| 工单发放数 | {ov['issued']} |")
    L.append(f"| 主仓合入数 | {ov['merged']} |")
    L.append(f"| **转化率** | **{rate_str(ov['merged'], ov['issued'])}** |")
    L.append(f"| 相关提交总数（不含发放提交） | {ov['commits_total']} |")
    L.append(f"| 其中 v1 期（≤{V2_ERA_MIN - 1}）发放 | {ov['v1_issued']} |")
    L.append(f"| 其中 v2 期（≥{V2_ERA_MIN}）发放 | {ov['v2_issued']} |")
    L.append("")

    L.append("## 表 2 · 月度转化\n")
    L.append("| 月份 | 发放 | 合入 | 转化率 |")
    L.append("|---|---:|---:|---:|")
    if rep["by_month"]:
        for mk in sorted(rep["by_month"]):
            b = rep["by_month"][mk]
            L.append(f"| {mk} | {b['issued']} | {b['merged']} | "
                     f"{rate_str(b['merged'], b['issued'])} |")
    else:
        L.append("| （无数据） | 0 | 0 | n/a |")
    L.append("")

    L.append("## 表 3 · 主题线维度\n")
    L.append("| 主题线 | 发放 | 合入 | 转化率 |")
    L.append("|---|---:|---:|---:|")
    for t in THEMES:
        b = rep["by_theme"].get(t, {"issued": 0, "merged": 0})
        L.append(f"| {t} | {b['issued']} | {b['merged']} | "
                 f"{rate_str(b['merged'], b['issued'])} |")
    L.append("")

    L.append("## 表 4 · Top 5 高转化工单\n")
    L.append("| 工单 | 主题 | 提交数 | 已合入 | 标题 |")
    L.append("|---|---|---:|:--:|---|")
    if rep["top"]:
        for it in rep["top"]:
            L.append(f"| WO-{it['number']} | {it['theme']} | {it['commits']} | "
                     f"{'✅' if it['merged'] else '—'} | {it['title']} |")
    else:
        L.append("| （无数据） | — | 0 | — | — |")
    L.append("")

    rate = ov["rate"]
    ok = "达标" if (rate is not None and rate >= FUNNEL_TARGET_RATE) else "未达标"
    mod_ok = "达标" if ov["merged"] >= FUNNEL_TARGET_MODULES else "未达标"
    L.append("## 漏斗 2.0 §5 目标对账\n")
    L.append(f"- 月度转化率 ≥ {FUNNEL_TARGET_RATE:.0f}%：本期 {rate_str(ov['merged'], ov['issued'])} ⇒ "
             f"**{ok}**")
    L.append(f"- 6 个月内 ≥ {FUNNEL_TARGET_MODULES} 模块合入主仓：本期 {ov['merged']} ⇒ **{mod_ok}**\n")

    L.append("## 口径说明\n")
    L.append("- **工单发放**：仓库根 `TRAE_WORKORDER_PROMPT_AGENT_<N>.md` 首次加入的提交时刻"
             "（`git log --diff-filter=A`）。")
    L.append("- **主仓合入**：commit subject 含工单号且含 `(#PR)`"
             "（本仓走 squash，一次合并 = 一个 `(#N)` 提交）。")
    L.append("- **相关提交数**：提到该工单号的提交数，**不含该工单的发放提交**"
             "（本仓发放提交的 subject 自带工单号，实测 182 条发放事件全带号）。")
    L.append("- **工单号写法**：兼容 `wNNN` / `工单NNN` / `卷NNN` / `WO-NNN` "
             "及斜杠列表（`工单220/221`、`卷189/190/192`）。")
    L.append("- **主题线**：`research/workorder_drafts/WO-<N>-<seg>-*.md` 的 seg"
             "（`bio`→biomass）+ commit 关键词兜底。")
    L.append(f"- **时代划分**：v1 = ≤{V2_ERA_MIN - 1}，v2 = ≥{V2_ERA_MIN}。"
             f"{'本期 **含** v1 明细' if rep['include_v1'] else 'v1 只进前三张汇总表，不进 Top 5 与逐条明细'}。")
    L.append("- **时间窗语义**（cohort）：按**发放时刻**归期 —— 窗口外发放的工单即使窗口内合入也不计入。")
    L.append("- **CI 状态**：默认不查（离线）；`--with-ci` 时走 GitHub REST。")
    L.append("- **历史重写 caveat**：`--diff-filter=A` 记的是文件**在 main 上首次出现**的时刻。"
             "若该文件是历史重写后被「净增量重放」的（本仓 `120ac5da` 一次加回 182~192 共 11 份），"
             "发放时刻会偏晚，月度归属随之偏移。")
    L.append("- **已知低估**：存在已合入 PR 的 subject 不含工单号"
             "（如 `#201`/`#203`/`#204` 属工单 204 任务三 却未带号）⇒ 合入数偏低。")
    return "\n".join(L) + "\n"


def parse_period(period: str) -> tuple[int | None, int | None, str]:
    """``30d`` / ``90d`` / ``all`` / ``YYYY-MM-DD..YYYY-MM-DD`` → (since, until, label)。"""
    now = int(time.time())
    p = (period or "30d").strip()
    if p == "all":
        return None, None, "all"
    m = re.fullmatch(r"(\d+)d", p)
    if m:
        days = int(m.group(1))
        return now - days * 86400, None, f"近 {days} 天"
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", p)
    if m:
        s = int(datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        u = int(datetime.strptime(m.group(2), "%Y-%m-%d")
                .replace(tzinfo=timezone.utc).timestamp()) + 86399
        return s, u, f"{m.group(1)} ~ {m.group(2)}"
    raise ValueError(f"无法解析 --period: {period!r}（支持 30d / 90d / all / YYYY-MM-DD..YYYY-MM-DD）")


def find_repo_root(start: Path) -> Path:
    """从 start 向上找 git 仓库根（非 git 目录则返回 start）。"""
    r = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else start


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="工单转化率闭环统计（漏斗 2.0 · 工单 238）")
    ap.add_argument("--repo", default=None, help="仓库路径（默认取脚本所在仓库根）")
    ap.add_argument("--period", default="30d",
                    help="30d / 90d / all / YYYY-MM-DD..YYYY-MM-DD（默认 30d）")
    ap.add_argument("--theme", default=None,
                    help="只统计某主题线（biomass/sdr/agent/esp32/pcb/other）")
    ap.add_argument("--out-dir", default="reports", help="输出目录（默认 <repo>/reports）")
    ap.add_argument("--name", default=None, help="报告文件名前缀（默认 workorder_conversion_stats_<日期>）")
    ap.add_argument("--include-v1", action="store_true", help="把 v1 期（≤189）也放进 Top 5 与逐条明细")
    ap.add_argument("--with-ci", action="store_true", help="额外查 PR 合并状态（需网络 + 凭据）")
    ap.add_argument("--json-only", action="store_true", help="只写 JSON，不写 Markdown")
    args = ap.parse_args(argv)

    repo = Path(args.repo) if args.repo else find_repo_root(Path(__file__).resolve().parent)
    since, until, label = parse_period(args.period)

    issues = build_issues(repo, since, until, with_ci=args.with_ci)
    if args.theme:
        issues = {n: it for n, it in issues.items() if it.theme == args.theme}
    rep = summarize(issues, label, include_v1=args.include_v1)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = repo / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or f"workorder_conversion_stats_{datetime.now().strftime('%Y-%m-%d')}"

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    print(f"[stats] JSON     -> {json_path}")
    if not args.json_only:
        md_path = out_dir / f"{stem}.md"
        md_path.write_text(render_markdown(rep), encoding="utf-8", newline="\n")
        print(f"[stats] Markdown -> {md_path}")
    ov = rep["overview"]
    print(f"[stats] 发放 {ov['issued']} / 合入 {ov['merged']} / 转化率 "
          f"{rate_str(ov['merged'], ov['issued'])} | 期间 {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
