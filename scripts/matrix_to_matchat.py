#!/usr/bin/env python3
"""授粉矩阵 → 结构化（K07）。

解析 UPGRADE-PROJECTS-2026-08-30.md 的 117 项授粉矩阵表格 →
结构化 JSON / CSV（编号/线/来源/落点/优先级/状态），供 MatChat 知识库入库。

并打印 3 个查询示例作为验收。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

LINE_NAME = {"R": "无线电", "M": "材料", "A": "Agent", "S": "安全", "K": "知识/工具链", "I": "基础设施"}

ROW_RE = re.compile(
    r"^\|\s*([RAMSKI]\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(P[012])\s*\|$"
)


def parse_matrix(text: str) -> list[dict]:
    out: list[dict] = []
    for ln in text.splitlines():
        m = ROW_RE.match(ln.strip())
        if not m:
            continue
        cid, project, source, target, priority = m.groups()
        line = LINE_NAME.get(cid[0], cid[0])
        out.append(
            {
                "编号": cid,
                "线": line,
                "项目": project.strip(),
                "来源": source.strip(),
                "落点": target.strip(),
                "优先级": priority,
                "状态": "未开工",
            }
        )
    return out


def query_examples(rows: list[dict]) -> list[str]:
    ex = []
    p0 = [r["编号"] for r in rows if r["优先级"] == "P0"]
    ex.append(f"Q1 · 优先级=P0 的今天能开项（{len(p0)} 个）: {', '.join(p0)}")
    rf = [r["编号"] for r in rows if "RF" in r["落点"] or "ESP" in r["落点"]]
    ex.append(f"Q2 · 落点含 RF/ESP 的项（{len(rf)} 个）: {', '.join(rf)}")
    material = [r["编号"] for r in rows if r["线"] == "材料"]
    ex.append(f"Q3 · 材料线（陆墨，{len(material)} 个）: {', '.join(material)}")
    return ex


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="授粉矩阵结构化")
    ap.add_argument("matrix", help="UPGRADE-PROJECTS-*.md 路径")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认同 matrix 目录）")
    args = ap.parse_args(argv)

    p = Path(args.matrix)
    rows = parse_matrix(p.read_text(encoding="utf-8", errors="replace"))
    out_dir = Path(args.out_dir) if args.out_dir else p.parent

    (out_dir / "授粉矩阵-结构化.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "授粉矩阵-结构化.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["编号", "线", "项目", "来源", "落点", "优先级", "状态"])
        w.writeheader()
        w.writerows(rows)

    print(f"matrix: 解析 {len(rows)} 项 -> 授粉矩阵-结构化.json / .csv")
    for q in query_examples(rows):
        print("  " + q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
