#!/usr/bin/env python3
"""逐篇评价表自动化（K03）。

输入 digest markdown → 输出逐篇评价表（内容 + 可利用度）。

Round2 的 44 份 digest 格式异构，本脚本用「arXiv ID 锚点」做容错抽取：
- 用 `\d{4}\.\d{4,5}v\d+` 定位每一篇；
- 表格行按 `|` 切格，非表格行取整行，去掉 ID/序号噪声作为「内容」；
- 「可利用度」按陆墨技术栈关键词命中打分，命中「最有价值/授粉点」段落的额外升一档。

输出：<digest>-eval.md + <digest>-eval.json（默认写到 digest 同目录）。
仅用标准库，无第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5}v\d+)\b")

# 陆墨技术栈关键词（中文 + 英文），命中数映射可利用度
STACK = {
    "RF/无线电": ["spectrum", "sdr", "lora", "radio", "wireless", "interference",
              "channel", "antenna", "signal", "beamforming", "thz", "频谱", "无线电",
              "信道", "干扰", "天线", "信号", "认知无线电"],
    "ESP32/嵌入式": ["esp32", "embedded", "mcu", "fpga", "hardware", "tape-out",
                "rtl", "低功耗", "嵌入式", "微控制器", "sx1278", "唤醒"],
    "材料/生物质": ["material", "polymer", "hydrogel", "biomass", "lignin",
                "cellulose", "mlip", "catalyst", "thermal", "dft", "mol", "材料",
                "水凝胶", "生物质", "木质素", "催化", "热解", "势"],
    "Agent/ML": ["agent", "llm", "transformer", "reinforcement", "diffusion",
             "federated", "neural", "world model", "大模型", "强化学习", "扩散",
             "联邦", "多智能体", "主动学习"],
    "量子": ["quantum", "qubit", "qec", "superconducting", "entanglement", "量子",
           "量子比特", "纠错", "超导", "trotter"],
    "机器人/具身": ["robot", "manipulator", "grasp", "vla", "embodied", "机械臂",
                "抓取", "机器人", "编队"],
}


def _level(score: int) -> str:
    if score >= 4:
        return "P0"
    if score >= 2:
        return "P1"
    if score == 1:
        return "P2"
    return "观察"


def _score(text: str) -> tuple[int, list[str]]:
    t = text.lower()
    hits: list[str] = []
    for cat, kws in STACK.items():
        if any(k in t for k in kws):
            hits.append(cat)
    return len(hits), hits


def extract_papers(text: str) -> list[dict]:
    lines = text.splitlines()
    # 定位「最有价值 / 授粉 / Top」段落，用于加分
    valuable_span = False
    valuable_lines: set[int] = set()
    for i, ln in enumerate(lines):
        if re.search(r"最有价值|授粉|Top 模式|Cross-Domain|Most Valuable|跨领域授粉", ln):
            valuable_span = True
        if valuable_span and re.search(r"^---|^## ", ln) and not re.search(r"最有价值|授粉|Top|Most|Cross", ln):
            valuable_span = False
        if valuable_span:
            valuable_lines.add(i)

    seen: dict[str, dict] = {}
    for i, ln in enumerate(lines):
        for m in ARXIV_RE.finditer(ln):
            aid = m.group(1)
            # 表格行：取 ID 之后的非空单元格作为内容
            if "|" in ln:
                cells = [c.strip() for c in ln.split("|") if c.strip()]
                try:
                    idx = next(j for j, c in enumerate(cells) if aid in c)
                except StopIteration:
                    idx = 0
                content = " | ".join(cells[idx + 1:])
            else:
                content = ln.replace(aid, "", 1).lstrip("- *#0123456789.:()[] ").strip()
            content = re.sub(r"\s+", " ", content)[:220]
            if aid in seen:
                if i in valuable_lines:
                    seen[aid]["content"] = content
                    seen[aid]["valuable"] = True
                continue
            score, cats = _score(content)
            seen[aid] = {
                "id": aid,
                "content": content,
                "score": score,
                "cats": cats,
                "valuable": i in valuable_lines,
            }
    return list(seen.values())


def run(digest: Path) -> int:
    text = digest.read_text(encoding="utf-8", errors="replace")
    papers = extract_papers(text)
    rows = []
    for p in papers:
        score = p["score"] + (1 if p["valuable"] else 0)
        rows.append(
            {
                "id": p["id"],
                "content": p["content"],
                "cats": p["cats"],
                "score": score,
                "level": _level(score),
                "valuable": p["valuable"],
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["id"]))

    base = digest.with_name(digest.stem + "-eval")
    base.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = [f"# {digest.stem} 逐篇评价表", "",
          f"共 {len(rows)} 篇，按可利用度降序。★=命中「最有价值/授粉」段落。", ""]
    md += ["| 可利用度 | ID | 命中 | 内容 |", "|------|-----|------|------|"]
    for r in rows:
        star = "★" if r["valuable"] else ""
        cats = ",".join(r["cats"]) or "-"
        content = r["content"].replace("|", "/")
        md.append(f"| {r['level']}{star} | {r['id']} | {cats} | {content} |")
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"eval: {digest.name} -> {len(rows)} 篇；输出 {base.with_suffix('.md').name} / .json")
    from collections import Counter
    print("   级别分布:", dict(Counter(r["level"] for r in rows)))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="digest 逐篇评价表生成")
    ap.add_argument("digests", nargs="+", help="digest markdown 文件路径")
    args = ap.parse_args(argv)
    for d in args.digests:
        p = Path(d)
        if not p.is_file():
            print(f"跳过（不存在）: {d}", file=sys.stderr)
            continue
        run(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
