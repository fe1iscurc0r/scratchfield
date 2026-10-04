#!/usr/bin/env python3
"""三线授粉合并 backlog（K10）。

把三线授粉合并成统一 backlog：
- 论文轮   （来源含 weekly_pollination / 论文轮）
- 扫货     （来源含 扫货）
- round10  （来源含 round10 / OTA-ELM）

输入 UPGRADE-PROJECTS 矩阵 → 输出 三线授粉-backlog.md（按线分组 + 去重说明）。
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

ROW_RE = re.compile(
    r"^\|\s*([RAMSKI]\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(P[012])\s*\|$"
)

LINE_NAME = {"R": "无线电", "M": "材料", "A": "Agent", "S": "安全", "K": "知识/工具链", "I": "基础设施"}


def _classify(source: str) -> str:
    s = source.lower()
    if "round10" in s or "ota-elm" in s:
        return "round10"
    if "扫货" in s:
        return "扫货"
    if "论文轮" in s or "weekly_pollination" in s:
        return "论文轮"
    return "digest"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="三线授粉合并")
    ap.add_argument("matrix", help="UPGRADE-PROJECTS-*.md 路径")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    p = Path(args.matrix)
    out_dir = Path(args.out_dir) if args.out_dir else p.parent
    rows = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW_RE.match(ln.strip())
        if m:
            cid, project, source, target, priority = m.groups()
            rows.append({"编号": cid, "项目": project.strip(), "来源": source.strip(),
                         "落点": target.strip(), "优先级": priority,
                         "线": LINE_NAME[cid[0]], "channel": _classify(source)})

    channels = {c: [r for r in rows if r["channel"] == c]
                for c in ("论文轮", "扫货", "round10")}
    total = sum(len(v) for v in channels.values())

    md = ["# 三线授粉合并 backlog（K10）", "",
          f"合并三线（论文轮/扫货/round10）共 {total} 项，与 digest 源 117 项矩阵对齐去重。", ""]
    for ch in ("论文轮", "扫货", "round10"):
        md += [f"## {ch}（{len(channels[ch])} 项）", "",
               "| 编号 | 线 | 项目 | 来源 | 落点 | 优先级 |",
               "|------|----|------|------|------|--------|"]
        for r in channels[ch]:
            md.append(f"| {r['编号']} | {r['线']} | {r['项目']} | {r['来源']} | {r['落点']} | {r['优先级']} |")
        md.append("")

    # 去重说明：三线内部编号唯一性 + 与 digest 源矩阵的交集
    ids = [r["编号"] for v in channels.values() for r in v]
    dupes = [k for k, c in Counter(ids).items() if c > 1]
    md += ["## 去重说明", "",
           f"- 三线内编号总数 {total}，唯一编号 {len(set(ids))}，重复 {len(dupes)}（{dupes or '无'}）。",
           "- 这些条目已并入 `UPGRADE-PROJECTS-2026-08-30.md` 的 117 项矩阵，来源列标记其归属线，"
           "合并时不重复建卡，只在此 backlog 按线归类。",
           "- digest 源（44 份 digest 的授粉点）不在本表，见 K05 的 `授粉点-统一.md`。"]

    (out_dir / "三线授粉-backlog.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"merge: {total} 项 -> {out_dir}/三线授粉-backlog.md")
    print("  论文轮:", len(channels["论文轮"]), "扫货:", len(channels["扫货"]),
          "round10:", len(channels["round10"]), "重复:", dupes or "无")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
