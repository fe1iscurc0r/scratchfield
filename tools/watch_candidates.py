#!/usr/bin/env python3
"""候选仓观察名单巡检（卷151 任务D）。

用途：盯住「无 LICENSE / 竞品 / 值得跟踪」的候选仓，只在**有变化**时输出。
- 对比项：star 数 / 最近推送时间 / 许可（spdx）
- 基线：data/watch_baseline.json（`--init` 生成；变化时自动回写）
- 无变化 → 不输出任何内容（cron 静默语义，可直接接 hermes cron 的 no_agent 模式）

实现说明（与本卷工单的偏差，务必知悉）：
1. 工单写「使用 `gh api`」，但本机与目标 cron 环境未必装 gh；
   本脚本改用 **Python 标准库 urllib 直连 GitHub REST**，零外部依赖（供应链铁律：不引新包）。
2. 令牌从环境变量 `GH_TOKEN` / `GITHUB_TOKEN` 读取（提高配额、可读私有仓）；
   不传则匿名访问（公开仓 60 次/小时，本名单 5 个仓足够）。

用法：
    python3 tools/watch_candidates.py --init        # 首次建立基线
    python3 tools/watch_candidates.py               # 巡检（有变化才打印）
    python3 tools/watch_candidates.py --json        # 输出 JSON（供上层消费）
    python3 tools/watch_candidates.py --repo owner/name   # 临时追加观察一个仓
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "data" / "watch_baseline.json"

# 观察名单（卷151 任务D 点名；owner/repo 全名按 docs/新项目调研-2026-09-23.md 校正）
DEFAULT_REPOS: list[dict[str, str]] = [
    {"repo": "IsaH93/lignin-ftir-chemometrics", "why": "材料线：FTIR→木质素纯度+S/G比 端到端管线（无许可，盯其补许可）"},
    {"repo": "In-Silico-RG/Lignin_Forward_Gen", "why": "材料线：正向 kMC 预测木质素连接键库存（无许可）"},
    {"repo": "art-mufteev/hydrogels", "why": "观察：martignac/MartiniGlass 作者新仓（建仓即空，盯首个动态）"},
    {"repo": "momori777/Artemis", "why": "竞品：本地 AI 女友后宫（与 NEKO+Lumo 定位重叠，盯许可与功能）"},
    {"repo": "okf-memory/okf-agent-memory", "why": "基建：Git-native 持久记忆 / Google OKF 实现（盯规范演进）"},
]

API = "https://api.github.com/repos/{repo}"
TIMEOUT_S = 20


def fetch_repo(repo: str, token: str | None) -> dict:
    """取仓库元数据；不存在返回 {'missing': True}，网络失败抛异常。"""
    req = urllib.request.Request(API.format(repo=repo))
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "lumo-watch-candidates")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"missing": True}
        raise
    lic = (data.get("license") or {}).get("spdx_id") or ""
    return {
        "stars": int(data.get("stargazers_count") or 0),
        "pushed_at": str(data.get("pushed_at") or ""),
        "license": "" if lic == "NOASSERTION" else lic,
        "archived": bool(data.get("archived")),
    }


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"[warn] 基线文件损坏，按空基线处理：{BASELINE_PATH}", file=sys.stderr)
        return {}


def save_baseline(data: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def diff_one(before: dict | None, after: dict) -> list[str]:
    """返回变化描述；无变化返回空列表。"""
    if after.get("missing"):
        return ["仓已不可见（404：删除/改名/转私有）"] if before is not None else []
    if before is None:
        return [f"新增观察（stars={after['stars']} license={after['license'] or '无'})"]
    changes: list[str] = []
    if before.get("stars") != after["stars"]:
        changes.append(f"stars {before.get('stars')} → {after['stars']}")
    if before.get("pushed_at") != after["pushed_at"]:
        changes.append(f"最近推送 {before.get('pushed_at') or '—'} → {after['pushed_at']}")
    if (before.get("license") or "") != after["license"]:
        changes.append(f"许可 {before.get('license') or '无'} → {after['license'] or '无'}")
    if bool(before.get("archived")) != after["archived"]:
        changes.append(f"归档状态 → {after['archived']}")
    return changes


def main() -> int:
    global BASELINE_PATH  # noqa: PLW0603 — 仅为支持 --baseline 覆盖，脚本级工具（须在首次使用前声明）

    ap = argparse.ArgumentParser(description="候选仓观察名单巡检（有变化才输出）")
    ap.add_argument("--init", action="store_true", help="用当前状态建立/覆盖基线（不报告变化）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--repo", action="append", default=[], help="临时追加观察仓（owner/name，可多次）")
    ap.add_argument("--baseline", default=str(BASELINE_PATH), help="基线文件路径")
    args = ap.parse_args()

    BASELINE_PATH = Path(args.baseline).resolve()

    watch: list[dict[str, str]] = list(DEFAULT_REPOS)
    for extra in args.repo:
        watch.append({"repo": extra, "why": "（命令行追加）"})

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    baseline = load_baseline()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    changed: list[dict] = []
    new_baseline: dict = dict(baseline)
    errors: list[str] = []

    for item in watch:
        repo = item["repo"]
        try:
            after = fetch_repo(repo, token)
        except Exception as e:  # 网络/限流：不污染基线，只记错
            errors.append(f"{repo}: {type(e).__name__}: {e}")
            continue

        before = baseline.get(repo)
        if args.init:
            new_baseline[repo] = after
            continue

        diffs = diff_one(before, after)
        if diffs:
            changed.append({"repo": repo, "why": item["why"], "changes": diffs})
            new_baseline[repo] = after

    if args.init:
        save_baseline(new_baseline)
        print(f"基线已写入 {BASELINE_PATH}（{len([k for k in new_baseline if not new_baseline[k].get('missing')])} 个仓）")
        return 0

    if changed:
        save_baseline(new_baseline)  # 变化才回写，避免无变化时反复改写文件

    for err in errors:
        print(f"[error] 取数失败（基线未动）{err}", file=sys.stderr)

    if args.json:
        print(json.dumps({"checked_at": now, "changed": changed, "errors": errors}, ensure_ascii=False, indent=2))
        return 0

    if changed:
        print(f"候选仓观测变化（{now}）：")
        for c in changed:
            print(f"- {c['repo']}：{'；'.join(c['changes'])}")
            print(f"  为什么要盯：{c['why']}")
    # 无变化 → 不输出（cron 静默语义）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
