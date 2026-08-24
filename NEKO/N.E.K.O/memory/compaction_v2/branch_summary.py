"""SPEC-03 Phase2 — compaction 升级：branch-summarization + confidence 门控（旁路）。

不改动 NEKO memory/recent.py 的 CompressedRecentHistoryManager。提供：
  - summarize_branches：按血统分支逐支摘要，再合并为分层压缩视图
  - should_compress：confidence ≥ 阈值才允许自动压缩（低置信保原文）
  - measure：token 节省率 + 信息完整率（关键词覆盖率口径，启发式）
License: Apache-2.0；机制参考 openclaw commands-compact 分层压缩思想（MIT）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..index_cards.store import heuristic_summary
from ..lineage.model import SessionLineage

# 粗 token 估算：CJK 1 字 ≈ 1 token，拉丁词 ≈ 1.3 token（对齐常见 tokenizer 量级）


def est_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fa5]", text))
    latin_words = len(re.findall(r"[A-Za-z]+", text))
    return cjk + int(latin_words * 1.3)


@dataclass
class BranchView:
    branch_label: str
    session_ids: list[str]
    summary: str
    keywords: list[str]


def summarize_branches(lineage: SessionLineage, root_id: str,
                       turns_by_session: dict[str, list[dict]],
                       summarizer=None) -> list[BranchView]:
    """root 下每个分支（含 root 主干）产一张摘要视图；分支级摘要先于全局合并
    —— 对齐 openclaw 的 branch-summarization 建议（分支隔离摘要，避免跨支污染）。"""
    summarizer = summarizer or heuristic_summary
    branches = lineage.branches_under(root_id)
    views: list[BranchView] = [BranchView("root", [root_id], *reversed(_sum(lineage, root_id, turns_by_session, summarizer)))]

    for label, sids in sorted(branches.items()):
        sids = list(dict.fromkeys(sids))  # 去重保序
        turns = [t for sid in sids for t in turns_by_session.get(sid, [])]
        summary, keywords = summarizer(turns)
        views.append(BranchView(label, sids, summary, keywords))
    return views


def _sum(lineage, sid, turns_by_session, summarizer):
    turns = turns_by_session.get(sid, [])
    return summarizer(turns)


def branch_confidence(views: list[BranchView],
                      turns_by_session: dict[str, list[dict]]) -> float:
    """分支摘要置信度：各支信息量（有内容 turn 占比）× 覆盖广度（有关键词的支占比）。"""
    if not views:
        return 0.0
    total_turns = sum(len(turns_by_session.get(v.branch_label, [])) for v in views) or 1
    per = []
    for v in views:
        turns = [t for sid in v.session_ids for t in turns_by_session.get(sid, [])]
        if not turns:
            per.append(0.0)
            continue
        filled = sum(1 for t in turns if t.get("content", "").strip()) / len(turns)
        kw = 1.0 if v.keywords else 0.4
        per.append(0.6 * filled + 0.4 * kw)
    return round(sum(per) / len(per), 3)


def should_compress(confidence: float, threshold: float = 0.55) -> bool:
    """高置信才自动压缩；低置信保原文（防摘要失真不可逆）。"""
    return confidence >= threshold


def measure(original_texts: list[str], compressed: str,
            keep_keywords: list[str] | None = None) -> dict:
    """压缩收益评估：token 节省率 + 信息完整率（关键词覆盖率，启发式口径）。"""
    orig_tokens = sum(est_tokens(t) for t in original_texts)
    comp_tokens = est_tokens(compressed)
    saved = 1 - comp_tokens / orig_tokens if orig_tokens else 0.0
    if keep_keywords is None:
        keep_keywords = []
        for t in original_texts:
            keep_keywords.extend(w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}|[A-Za-z][A-Za-z0-9_-]{2,}", t)
                                 if w not in t.lower()[:0])  # 全量候选
        keep_keywords = sorted(set(keep_keywords))[:40]
    hit = sum(1 for kw in keep_keywords if kw in compressed)
    completeness = hit / len(keep_keywords) if keep_keywords else 1.0
    return {"original_tokens": orig_tokens, "compressed_tokens": comp_tokens,
            "token_saved_pct": round(saved * 100, 1),
            "info_completeness_pct": round(completeness * 100, 1),
            "keywords_total": len(keep_keywords), "keywords_hit": hit}
