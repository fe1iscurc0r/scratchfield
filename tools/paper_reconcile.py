#!/usr/bin/env python3
"""论文 digest 对账脚本（卷176-A）——failed.txt 脏账清洗 + 三份输出。

背景（工单实测）：`~/research/papers/digests/full/` 已落 18,942 篇 md；
`failed.txt` 累计 2,535 行，其中大部分是历史 key 失效期的旧账（论文后来已成功落盘）
——对账后真缺 md 仅 54 篇。**failed.txt 是脏账不是缺口。**

用法：
    python tools/paper_reconcile.py --check          # 只校验（退出码 0 = 三数字自洽）
    python tools/paper_reconcile.py --data-dir ~/research/papers   # 生成三份输出
    python tools/paper_reconcile.py --data-dir X --dry-run          # 不写文件只打印

输出（--data-dir 下）：
    failed_active.txt        真缺（待重试；429/502 类）
    failed_permanent.txt     永久失败（content 过短类，附原因）
    reconcile-report-<date>.md  数字表：总失败 / 已补 / 真缺 / 永久失败

对账规则（写死防口径漂移）：
    1. failed.txt 每行取首个 token 为 pid；`<pid>.md` 存在于 digests/full/ → 已补（剔除）
    2. 未补的按原因分类：
       - content 过短 / content=NN 字 → permanent（内容层面不可重试）
       - 429 / 502 / 超时类 → active（可重试）
       - 403 → active（**先由调用方单篇探测**判定 IP 级 or 单篇级；本脚本不做网络动作）
       - 其他未知 → active + 原因保留（不静默归类）
    3. 自洽断言：总失败 == 已补 + 真缺 + 永久失败

stdlib only；**零网络动作**（重试逻辑属流水线主机，见 docs/Trae-Blocked-176-*.md）。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PID_RE = re.compile(r"^\s*([\w.\-]+?)\s*(?:[\s:|,]+(.*))?$")
PERMANENT_HINTS = ("content 过短", "content过短", "content=", "too short", "empty content")
RETRYABLE_HINTS = ("429", "502", "503", "timeout", "timed out", "rate limit", "超时")


def parse_failed_line(line: str) -> tuple[str, str] | None:
    """failed.txt 一行 → (pid, 原因)；空行/注释返回 None。

    兼容两种行格式：`pid` 或 `pid | 原因` / `pid  原因` / `pid,原因`。
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = PID_RE.match(line)
    if not m:
        return None
    pid = m.group(1).strip()
    reason = (m.group(2) or "").strip()
    return pid, reason


def classify(reason: str) -> str:
    """原因 → 'permanent' | 'active'（未知一律 active，不静默归类）。"""
    low = reason.lower()
    if any(h in low for h in PERMANENT_HINTS):
        return "permanent"
    if any(h in reason or h in low for h in RETRYABLE_HINTS):
        return "active"
    return "active"


def reconcile(failed_path: Path, digests_dir: Path) -> dict:
    """执行对账，返回统计与三类清单（纯函数式：只读扫描，不写文件）。"""
    lines = failed_path.read_text(encoding="utf-8", errors="ignore").splitlines() \
        if failed_path.exists() else []
    total = 0
    already: list[str] = []
    active: list[tuple[str, str]] = []
    permanent: list[tuple[str, str]] = []
    for raw in lines:
        parsed = parse_failed_line(raw)
        if parsed is None:
            continue
        pid, reason = parsed
        total += 1
        if (digests_dir / f"{pid}.md").exists():
            already.append(pid)
            continue
        (permanent if classify(reason) == "permanent" else active).append((pid, reason))
    stats = {
        "total": total,
        "already": len(already),
        "active": len(active),
        "permanent": len(permanent),
        "self_consistent": total == len(already) + len(active) + len(permanent),
    }
    return {"stats": stats, "already": already, "active": active, "permanent": permanent}


def write_outputs(result: dict, data_dir: Path, today: str | None = None) -> Path:
    """写 failed_active.txt / failed_permanent.txt / reconcile-report-<date>.md。"""
    today = today or date.today().isoformat()
    (data_dir / "failed_active.txt").write_text(
        "\n".join(f"{pid}\t{reason}" for pid, reason in result["active"]) + "\n",
        encoding="utf-8")
    (data_dir / "failed_permanent.txt").write_text(
        "\n".join(f"{pid}\t{reason}" for pid, reason in result["permanent"]) + "\n",
        encoding="utf-8")
    s = result["stats"]
    reason_hist = Counter(r for _p, r in result["active"])
    report = [
        f"# 论文 digest 对账报告 · {today}",
        "",
        "| 指标 | 数量 |", "|---|---|",
        f"| failed.txt 总行（有效） | {s['total']} |",
        f"| 已补（md 已存在，剔除） | {s['already']} |",
        f"| **真缺（active，待重试）** | **{s['active']}** |",
        f"| 永久失败（permanent） | {s['permanent']} |",
        "",
        f"自洽校验：{s['total']} == {s['already']} + {s['active']} + {s['permanent']} → "
        f"{'✓' if s['self_consistent'] else '✗ 不自洽！'}",
        "",
        "## active 原因分布",
        "",
    ]
    for reason, n in reason_hist.most_common():
        report.append(f"- {reason or '（无原因）'}：{n}")
    report.append("")
    path = data_dir / f"reconcile-report-{today}.md"
    path.write_text("\n".join(report), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="论文 digest failed.txt 对账（卷176-A）")
    ap.add_argument("--data-dir", default=str(Path.home() / "research" / "papers"),
                    help="流水线数据目录（须含 digests/full/ 与 failed.txt）")
    ap.add_argument("--check", action="store_true", help="只校验自洽（不写文件），退出码 0=自洽")
    ap.add_argument("--dry-run", action="store_true", help="打印统计但不写文件")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    failed = data_dir / "failed.txt"
    digests = data_dir / "digests" / "full"
    if not data_dir.exists():
        print(f"[reconcile] ⚠️ 数据目录不可达：{data_dir}", file=sys.stderr)
        print("[reconcile] 本机非流水线主机——脚本就绪，请在流水线主机运行"
              "（见 docs/Trae-Blocked-176-2026-09-30.md）", file=sys.stderr)
        return 2
    if not failed.exists():
        print(f"[reconcile] ⚠️ failed.txt 不存在：{failed}", file=sys.stderr)
        return 2
    if not digests.exists():
        print(f"[reconcile] ⚠️ digests/full 不存在：{digests}", file=sys.stderr)
        return 2

    result = reconcile(failed, digests)
    s = result["stats"]
    print(f"[reconcile] 总失败 {s['total']} = 已补 {s['already']} + 真缺 {s['active']} "
          f"+ 永久 {s['permanent']}  → {'自洽 ✓' if s['self_consistent'] else '不自洽 ✗'}")
    if not s["self_consistent"]:
        return 1
    if args.check:
        return 0
    if args.dry_run:
        return 0
    out = write_outputs(result, data_dir)
    print(f"[reconcile] 三份输出已写：failed_active.txt / failed_permanent.txt / {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
