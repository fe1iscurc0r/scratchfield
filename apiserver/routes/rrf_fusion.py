"""RRF 融合模块（SPEC-05 S1）—— 多路召回融合排序，替代字符串拼接。

设计要点（SPEC-05 第三节）：
- 每路召回返回 top-k 条目，各自带 rank（0 = 最相关）
- RRF score = sum(1/(k + rank))，k=60（经典 Reciprocal Rank Fusion 常数）
- 同一文本多路命中只留一次，score 累加（去重增强）
- 融合后按 score 降序，附来源标签，截断 max_chars
- 纯函数、零依赖，可独立单测；旁路（语义推理/化学计算）不进排序，由调用方附加

用法（lumo_proxy._query_rag_standalone）：
    items = fuse_ranked([grag_items, vector_items], source_labels={"grag": "知识图谱", "vector": "研究笔记"})
    result = items + ("\n\n" + semantic_str if semantic_str else "")
"""
from __future__ import annotations

RRF_K = 60  # RRF 常数（经典值，mem0/graphite 同款）

MAX_CHARS_DEFAULT = 2000

# 来源中文标签（默认）
DEFAULT_LABELS = {
    "grag": "知识图谱",
    "vector": "研究笔记",
}


def rrf_score(rank: int, k: int = RRF_K) -> float:
    """单条目 RRF 得分：1/(k + rank)，rank 从 0 起（0 最佳）。"""
    if rank < 0:
        raise ValueError(f"rank 不能为负: {rank}")
    return 1.0 / (k + rank)


def _normalize_ranked_lists(ranked_lists):
    """输入规范化：支持 list[list[dict]] 或 list[dict]。

    每路 dict 至少含 'text' 与 'rank'（rank 从 0 起）；可选 'source'。
    返回统一的 list[list[dict]]，缺省 source 由调用方标签补。
    """
    if not ranked_lists:
        return []
    # 单路直接传 list[dict] 的情况
    if all(isinstance(item, dict) for item in ranked_lists):
        return [ranked_lists]
    return ranked_lists


def fuse_ranked(
    ranked_lists,
    k: int = RRF_K,
    max_chars: int = MAX_CHARS_DEFAULT,
    source_labels: dict | None = None,
) -> str:
    """RRF 融合多路召回，返回按 score 降序的 markdown 字符串。

    Args:
        ranked_lists: list[list[dict]]，每路 [{text, rank, source?}, ...]；或单路 list[dict]
        k: RRF 常数
        max_chars: 输出截断长度（按字符计）
        source_labels: source key → 中文标签，如 {"grag": "知识图谱"}
    Returns:
        融合后的字符串；空输入返回 ""。
    """
    labels = {**DEFAULT_LABELS, **(source_labels or {})}
    lists = _normalize_ranked_lists(ranked_lists)
    if not lists:
        return ""

    # 聚合：text(去空白) → {score, source, text}
    acc: dict[str, dict] = {}
    for path in lists:
        for item in path:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            rank = item.get("rank", 0)
            src = item.get("source", "")
            key = text  # 去重键：同文本多路命中只留一次
            if key not in acc:
                acc[key] = {"score": 0.0, "source": src, "text": text}
            acc[key]["score"] += rrf_score(rank, k)

    if not acc:
        return ""

    # 按 score 降序
    ordered = sorted(acc.values(), key=lambda x: x["score"], reverse=True)

    lines = []
    total = 0
    truncated = False
    for entry in ordered:
        label = labels.get(entry["source"], entry["source"] or "检索")
        line = f"- [来源:{label}] {entry['text']}"
        total += len(line) + 1
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    body = "\n".join(lines)
    if truncated:
        body += "\n...[截断]"
    return body
