#!/usr/bin/env python3
"""授粉点格式统一迁移（K05）。

扫描 digest 目录 → 抽「授粉 / Cross-Domain Pollination」段落 → 归一化为
统一模板（来源|流向|用途|优先级）→ 输出 授粉点-统一.json / .md。

格式异构，采用「段落定位 + 子点切分 + 关键词推断」的容错策略。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5}v\d+)\b")

SECTION_RE = re.compile(r"授粉|Cross-Domain Pollination|Cross-domain Pollination|Pollination", re.I)
POINT_HEAD_RE = re.compile(
    r"^(?:#{2,6}\s*)?(?:\S*\s*)?(?:授粉点?\s*[A-C0-9]?|Point\s*\d+|🔌?\s*授粉\s*\d+)\s*[:：]",
)
NUM_ITEM_RE = re.compile(r"^\d+\.\s")

FLOW_KW = {
    "RF": ["频谱", "sdr", "无线电", "rf", "lora", "信道", "天线", "信号", "认知无线电", "波束"],
    "ESP": ["esp32", "嵌入式", "低功耗", "固件", "mcu", "唤醒", "sx1278", "端侧"],
    "材料": ["材料", "生物质", "水凝胶", "木质素", "催化", "陆墨", "polymer", "hydrogel", "biomass", "mlip"],
    "Agent": ["agent", "llm", "多智能体", "记忆", "大模型", "世界模型", "联邦"],
    "安全": ["安全", "攻击", "防护", "隐私", "信任", "投毒", "侧信道"],
    "量子": ["量子", "quantum", "qubit", "超导", "qec"],
}


def _infer_flow(text: str) -> str:
    t = text.lower()
    for flow, kws in FLOW_KW.items():
        if any(k in t for k in kws):
            return flow
    return "其他"


def _infer_priority(text: str) -> str:
    if re.search(r"\bP0\b", text):
        return "P0"
    if re.search(r"\bP1\b", text):
        return "P1"
    if re.search(r"\bP2\b", text):
        return "P2"
    if re.search(r"直接迁移|直接移植|可直接抄|可抄|落地|直接参考|现成", text):
        return "P1"
    if re.search(r"远期|观察|跟踪|里程碑|观察笔记", text):
        return "P2"
    return "P2"


def _extract_section(text: str) -> str:
    """定位授粉段落：从首个授粉标题到文末（授粉通常是最后一节）。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("#") and SECTION_RE.search(ln):
            start = i
            break
    if start is None:
        # 兜底：找正文里含「授粉」的标题或行
        for i, ln in enumerate(lines):
            if SECTION_RE.search(ln) and ln.strip().startswith(("#", "Point")):
                start = i
                break
    if start is None:
        return ""
    return "\n".join(lines[start:])


def _split_points(section: str) -> list[str]:
    lines = section.splitlines()
    points: list[str] = []
    cur: list[str] = []
    for ln in lines:
        is_head = bool(POINT_HEAD_RE.match(ln.strip())) or bool(NUM_ITEM_RE.match(ln.strip()))
        if is_head and cur:
            points.append("\n".join(cur).strip())
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        points.append("\n".join(cur).strip())
    # 若没切出多个点，整段作为单点
    if len(points) <= 1:
        return [section.strip()] if section.strip() else []
    return [p for p in points if ARXIV_RE.search(p) or len(p) > 20]


def migrate(digest: Path) -> list[dict]:
    text = digest.read_text(encoding="utf-8", errors="replace")
    section = _extract_section(text)
    if not section:
        return []
    out: list[dict] = []
    for idx, pt in enumerate(_split_points(section), 1):
        ids = sorted(set(ARXIV_RE.findall(pt)))
        purpose = re.sub(r"\s+", " ", pt)
        purpose = re.sub(r"^#{2,6}\s*", "", purpose)
        purpose = purpose[:200]
        out.append(
            {
                "编号": f"{digest.stem.replace('digest-', '')}.{idx}",
                "来源": digest.name,
                "arxiv_ids": ids,
                "流向": _infer_flow(pt),
                "用途": purpose,
                "优先级": _infer_priority(pt),
            }
        )
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="授粉点格式统一迁移")
    ap.add_argument("digest_dir", help="digest 目录")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 digest 目录）")
    args = ap.parse_args(argv)

    d = Path(args.digest_dir)
    out_dir = Path(args.out_dir) if args.out_dir else d
    records: list[dict] = []
    for f in sorted(d.glob("digest-*.md")):
        records.extend(migrate(f))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "授粉点-统一.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = ["# 授粉点统一表", "", f"共 {len(records)} 条。", "",
          "| 编号 | 来源 | 流向 | 优先级 | 用途 |",
          "|------|------|------|--------|------|"]
    for r in records:
        purpose = r["用途"].replace("|", "/")
        md.append(f"| {r['编号']} | {r['来源']} | {r['流向']} | {r['优先级']} | {purpose} |")
    (out_dir / "授粉点-统一.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"migrate: {len(records)} 条授粉点 -> {out_dir}/授粉点-统一.md / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
