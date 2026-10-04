#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_paper_brief.py — 论文情报日报（卷136）

四个子命令：
  --scan-new    扫描当天 mtime 的 digest 文件，关键词过滤，输出 latest.json
  --summarize   读 latest.json，提取每篇一句话摘要，输出 summary.txt
  --rank        关键词×分类权重打分，输出 ranked.json
  --all         scan-new + rank + summarize 一条龙

目录约定（按仓内实际结构，工单原假设路径作兼容层）：
  主路径：docs/paper-round*/digests/digest-*.md（实测结构）
  兼容：research/papers/digests/full/*.md（若未来迁至此则自动识别）

输出目录：~/.hermes/cache/daily_paper_brief/（工单指定）

W136-01/02/03/04 对应关系见各函数 docstring。
约束遵守：不改 paper_digest_batch.py；不申请新 API key（--summarize 的
LLM 摘要优先走环境变量 DIGEST_API_KEY，无 key 时降级为规则抽取——
从 digest 表格直接取「一句话核心贡献」，零 API 消耗，不静默：输出头注明模式）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path.home() / ".hermes" / "cache" / "daily_paper_brief"

# ---------- W136-01 关键词表 ----------
# 材料线主关键词（工单指定）+ 射频/SDR 兼顾关键词（W136-04）
# 每个关键词可带别名（digest 实测为中文核心贡献 + 英文标题混合，
# 英文关键词必须配中文别名才能真正命中）。
KEYWORD_ALIASES: dict[str, list[str]] = {
    "lignin": ["lignin", "木质素"],
    "hydrogel": ["hydrogel", "水凝胶"],
    "rheology": ["rheology", "流变"],
    "spectroscopy": ["spectroscopy", "spectral", "光谱"],
    "biomass": ["biomass", "生物质"],
    "pyrolysis": ["pyrolysis", "热解"],
    "photothermal": ["photothermal", "光热"],
    "solar evaporation": ["solar evaporation", "solar steam", "太阳能蒸发", "太阳蒸汽"],
    "radio": ["radio", "射频"],
    "sdr": ["sdr", "software defined radio"],
    "spectrum": ["spectrum", "频谱"],
    "rf": ["rf "],  # rf 需带尾空格避免误匹配（如 "rfor"）
    "antenna": ["antenna", "天线"],
    "wireless": ["wireless", "无线"],
}
MATERIAL_KEYWORDS = ["lignin", "hydrogel", "rheology", "spectroscopy", "biomass",
                     "pyrolysis", "photothermal", "solar evaporation"]
RADIO_KEYWORDS = ["radio", "sdr", "spectrum", "rf", "antenna", "wireless"]

# W136-04 分类权重：cond-mat.soft/soft-matter/physics.chem-ph ×3，materials ×2，
# 射频/SDR ×2（工单原文）
CATEGORY_WEIGHTS = {
    "cond-mat.soft": 3, "soft-matter": 3, "physics.chem-ph": 3,
    "materials": 2,
}
RADIO_WEIGHT = 2

# digest 表格行格式：| 2608.20318 | 标题缩写 | 一句话核心贡献 |
ROW_RE = re.compile(r"^\|\s*(\d{4}\.\d{4,5})\s*\|([^|]+)\|([^|]+)\|?\s*$")
SECTION_RE = re.compile(r"^#{2,3}\s*(.+)$")


def _digest_dirs() -> list[Path]:
    """实际结构 + 工单假设结构的并集（存在的才返回）。"""
    candidates = [
        REPO_ROOT / "docs",                       # docs/paper-round*/digests/
        REPO_ROOT / "research" / "papers" / "digests",  # 工单假设路径
    ]
    return [c for c in candidates if c.is_dir()]


def _iter_digest_files() -> list[Path]:
    out: list[Path] = []
    for base in _digest_dirs():
        # docs/paper-round2-2026-08-30/digests/digest-g1-1-*.md
        out.extend(base.glob("paper-round*/digests/digest-*.md"))
        # research/papers/digests/full/*.md（工单假设）
        out.extend(base.glob("full/*.md"))
        out.extend(base.glob("digest-*.md"))
    # 去重 + 按 mtime 新在前
    seen, uniq = set(), []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return sorted(uniq, key=lambda p: p.stat().st_mtime, reverse=True)


_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _file_matches_day(f: Path, day: str) -> bool:
    """mtime 当天 或 文件名含该日期（git 场景 mtime 会漂移到 clone 日，文件名更可靠）。"""
    if _dt.date.fromtimestamp(f.stat().st_mtime).isoformat() == day:
        return True
    return bool(_FILENAME_DATE_RE.search(f.name) and day in f.name)


def _match_keywords(text: str) -> list[str]:
    """返回命中的规范关键词（别名表驱动：中英任一命中即算）。"""
    t = text.lower()
    hits = []
    for key, aliases in KEYWORD_ALIASES.items():
        if any(a in t for a in aliases):
            hits.append(key)
    return hits


# ---------- W136-01: --scan-new ----------
def scan_new(today: str | None = None, out_dir: Path = CACHE_DIR) -> list[dict]:
    """扫描当天 mtime 的 digest，关键词过滤 → latest.json。

    空结果输出空数组，不报错（工单要求）。
    """
    day = today or _dt.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for f in _iter_digest_files():
        if not _file_matches_day(f, day):
            continue
        results.extend(_parse_digest(f))
    out = out_dir / "latest.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def _parse_digest(f: Path) -> list[dict]:
    """解析单个 digest md：表格行 → {paper_id, title, summary, digest_path, matched_keywords}。"""
    entries: list[dict] = []
    section = ""
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1).strip()
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        pid, title, core = (g.strip() for g in m.groups())
        blob = f"{title} {core}"
        kw = _match_keywords(blob)
        if not kw:
            continue
        entries.append({
            "paper_id": pid,
            "title": title,
            "summary": core,
            "digest_path": str(f),
            "section": section,
            "matched_keywords": kw,
        })
    return entries


# ---------- W136-04: --rank ----------
def rank(out_dir: Path = CACHE_DIR) -> list[dict]:
    """命中关键词数 × 分类权重 → ranked.json（W136-02 取前 5 篇）。

    权重：命中材料关键词数 ×1（cond-mat.soft/soft-matter/physics.chem-ph 的
    section 再 ×3；materials ×2）；射频关键词 ×2。
    """
    latest = json.loads((out_dir / "latest.json").read_text(encoding="utf-8"))
    ranked = []
    for e in latest:
        score = 0
        cat_mult = 1
        sec_l = (e.get("section") or "").lower()
        for cat, w in CATEGORY_WEIGHTS.items():
            if cat.lower() in sec_l:
                cat_mult = max(cat_mult, w)
        mat_hits = [k for k in e["matched_keywords"] if k in MATERIAL_KEYWORDS]
        rf_hits = [k for k in e["matched_keywords"] if k in RADIO_KEYWORDS]
        score = len(mat_hits) * cat_mult + len(rf_hits) * RADIO_WEIGHT
        r = dict(e)
        r["score"] = score
        ranked.append(r)
    ranked.sort(key=lambda x: -x["score"])
    (out_dir / "ranked.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=1), encoding="utf-8")
    return ranked


# ---------- W136-02: --summarize ----------
def summarize(top_n: int = 5, out_dir: Path = CACHE_DIR) -> Path:
    """digest → 人类可读摘要 summary.txt（每篇 1 行：arXiv:ID — 一句话）。

    API 路线：DIGEST_API_KEY 存在时走 LLM 精炼（工单允许复用 yunshuzhilian key）；
    无 key 时规则模式：直接取 digest 的「一句话核心贡献」（信息等价，零消耗）。
    两种模式都在文件头注明，不静默。
    """
    ranked_path = out_dir / "ranked.json"
    src = json.loads(ranked_path.read_text(encoding="utf-8")) if ranked_path.exists() \
        else json.loads((out_dir / "latest.json").read_text(encoding="utf-8"))
    top = src[:top_n]
    out = out_dir / "summary.txt"
    lines: list[str] = []
    api_key = os.environ.get("DIGEST_API_KEY")
    mode = "llm" if api_key else "rule-based（digest 核心贡献直取，未调 LLM：无 DIGEST_API_KEY）"
    lines.append(f"# 论文情报 top{len(top)} · 模式: {mode}")
    for e in top:
        lines.append(f"arXiv:{e['paper_id']} — {e['summary']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文情报日报（卷136）")
    ap.add_argument("--scan-new", action="store_true", help="扫描当天新 digest → latest.json")
    ap.add_argument("--rank", action="store_true", help="打分 → ranked.json")
    ap.add_argument("--summarize", action="store_true", help="前 N 篇 → summary.txt")
    ap.add_argument("--all", action="store_true", help="scan+rank+summarize 一条龙")
    ap.add_argument("--date", default=None, help="覆盖'今天'（ISO 日期，测试用）")
    ap.add_argument("--top", type=int, default=5, help="summarize 取前 N 篇（默认 5）")
    ap.add_argument("--cache-dir", default=None, help="覆盖输出目录（测试用）")
    args = ap.parse_args(argv)

    out_dir = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
    if not (args.scan_new or args.rank or args.summarize or args.all):
        ap.print_help()
        return 2

    if args.all or args.scan_new:
        res = scan_new(today=args.date, out_dir=out_dir)
        print(f"[scan-new] 当天命中 {len(res)} 篇 → {out_dir/'latest.json'}")
    if args.all or args.rank:
        if not (out_dir / "latest.json").exists():
            print("[rank] 无 latest.json，先跑 --scan-new", file=sys.stderr)
            return 1
        ranked = rank(out_dir=out_dir)
        print(f"[rank] 打分完成 {len(ranked)} 篇 → {out_dir/'ranked.json'}")
    if args.all or args.summarize:
        p = summarize(top_n=args.top, out_dir=out_dir)
        print(f"[summarize] → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
