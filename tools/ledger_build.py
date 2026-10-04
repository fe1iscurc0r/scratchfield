#!/usr/bin/env python3
"""三线产出归一总台账生成（卷179）。

复刻 2026-09-07 手工总台账（docs/2026-09-07-授粉日报论文-总台账.md）为常驻机制。

三线数据源（**只读扫描**）：
  授粉线：docs/ 下文件名匹配 `超限战轮|授粉报告` 的 md
          —— 轮次表从文件名提日期、从正文表格行 `✅ P0/P1/P2` 计数
  日报线：docs/gitee-stars-backfill-YYYY-MM-DD.json（条目数）
  论文线：~/research/papers/（progress.txt 统计行 + digests/full 计数）——
          路径不可达时**显式标注**，不静默跳过

用法：
    python tools/ledger_build.py                    # 全量重建 → docs/ledger-<today>.md
    python tools/ledger_build.py --since 2026-09-20 # 只列该日期之后
    python tools/ledger_build.py --out docs/ledger-2026-09-28.md   # 指定输出（周台账幂等覆盖）

硬约束：只读 + 新增 docs 产物；抽取失败的行标「⚠️ 抽取失败待人工」不静默。
stdlib only。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
PAPERS_DIR = Path.home() / "research" / "papers"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
ROUND_RE = re.compile(r"超限战轮(\d+)")
P0_RE = re.compile(r"✅\s*\*\*?P0\*\*?|✅\s*P0")
P1_RE = re.compile(r"✅\s*\*\*?P1\*\*?|✅\s*P1")
P2_RE = re.compile(r"✅\s*\*\*?P2\*\*?|✅\s*P2")


# ---------------- 授粉线 ----------------

def scan_pollination(since: str | None) -> list[dict]:
    rows = []
    files = sorted(p for p in DOCS.glob("*.md")
                   if re.search(r"超限战轮|授粉报告", p.name))
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = DATE_RE.search(f.name)
        day = m.group(1) if m else None
        if since and (day is None or day < since):
            continue
        rm = ROUND_RE.search(f.name)
        angle = ""
        title = re.match(r"^#\s+(.+)", text)
        if title:
            angle = title.group(1).strip().lstrip("# ").strip()
            angle = re.sub(r"^超限战轮\d+\s*[·—-]?\s*", "", angle)
            angle = angle.replace("授粉报告", "").strip(" —·")
        p0, p1, p2 = (len(P0_RE.findall(text)), len(P1_RE.findall(text)),
                      len(P2_RE.findall(text)))
        # 硬约束：抽取失败（三种标记都为零 → 该报告未用「✅ Pn」格式）标 ⚠️ 而非静默出 0
        extract_ok = (p0 + p1 + p2) > 0
        rows.append({
            "file": f.name,
            "date": day or "⚠️ 抽取失败待人工（文件名无日期）",
            "round": rm.group(1) if rm else "",
            "angle": angle or "⚠️ 抽取失败待人工（标题缺失）",
            "p0": p0 if extract_ok else "⚠️",
            "p1": p1 if extract_ok else "⚠️",
            "p2": p2 if extract_ok else "⚠️",
            "extract_ok": extract_ok,
        })
    rows.sort(key=lambda r: (r["date"], r["file"]))
    return rows


# ---------------- 日报线 ----------------

def scan_daily(since: str | None) -> list[dict]:
    rows = []
    for f in sorted(DOCS.glob("gitee-stars-backfill-*.json")):
        m = DATE_RE.search(f.name)
        day = m.group(1) if m else None
        if since and (day is None or day < since):
            continue
        n = None
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                n = len(data)
            elif isinstance(data, dict):
                n = len(data.get("repos") or data.get("items") or data)
        except (json.JSONDecodeError, OSError):
            n = None
        rows.append({"date": day or "⚠️ 抽取失败待人工", "file": f.name,
                     "count": n if n is not None else "⚠️ 抽取失败待人工"})
    rows.sort(key=lambda r: r["date"])
    return rows


# ---------------- 论文线 ----------------

def scan_papers() -> dict:
    out: dict = {"path": str(PAPERS_DIR), "reachable": PAPERS_DIR.exists()}
    if not out["reachable"]:
        out["note"] = "⚠️ 数据源不可达（本机无 ~/research/papers/）——非跳过，需在流水线主机运行"
        return out
    full = PAPERS_DIR / "digests" / "full"
    out["digest_md"] = len(list(full.glob("*.md"))) if full.exists() else "⚠️ digests/full 不存在"
    for name in ("progress.txt", "failed_active.txt"):
        p = PAPERS_DIR / name
        if p.exists():
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            out[name] = len(lines)
        else:
            out[name] = "⚠️ 文件不存在"
    return out


def build(since: str | None, out_path: Path) -> None:
    pol = scan_pollination(since)
    daily = scan_daily(since)
    papers = scan_papers()

    lines = [f"# 三线总台账 · {date.today().isoformat()}", "",
             "> 自动生成（`tools/ledger_build.py`，卷179）——只读扫描三线产出，"
             "不修改任何既有报告。" +
             (f" 增量视图：since {since}" if since else " 全量视图。"), ""]

    lines += ["## 授粉线", "",
              f"共 {len(pol)} 份报告" + (f"（since {since}）" if since else ""), "",
              "| 日期 | 轮次 | 角度 | P0 | P1 | P2 | 文件 |", "|---|---|---|---|---|---|---|"]
    for r in pol:
        lines.append(f"| {r['date']} | {r['round'] or '—'} | {r['angle'][:40]} | "
                     f"{r['p0']} | {r['p1']} | {r['p2']} | `{r['file'][:52]}` |")

    lines += ["", "## 日报线", "",
              "| 日期 | 条目数 | 文件 |", "|---|---|---|"]
    for r in daily:
        lines.append(f"| {r['date']} | {r['count']} | `{r['file']}` |")

    lines += ["", "## 论文线", ""]
    if not papers.get("reachable"):
        lines.append(f"- {papers['note']}")
    else:
        lines.append(f"- {papers['path']}")
        for k in ("digest_md", "progress.txt", "failed_active.txt"):
            if k in papers:
                label = {"digest_md": "digests/full md 数"}.get(k, k)
                lines.append(f"- {label}：{papers[k]}")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ledger] 已生成 {out_path}")
    print(f"  授粉线 {len(pol)} 份 | 日报线 {len(daily)} 份 | "
          f"论文线 {'可达' if papers.get('reachable') else '不可达（已标注）'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="三线产出归一总台账（卷179）")
    ap.add_argument("--since", default=None, help="只列该日期（YYYY-MM-DD）之后的")
    ap.add_argument("--out", default=None, help="输出路径（缺省 docs/ledger-<today>.md）")
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else (DOCS / f"ledger-{date.today().isoformat()}.md")
    build(args.since, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
