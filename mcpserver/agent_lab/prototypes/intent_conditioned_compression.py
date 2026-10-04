"""A57 · Paritok-4B 意图条件上下文压缩原型（来源 2608.24188）

论文核心：编码 Agent 每轮把大文件读取/工具输出原样重发给前沿 LLM；
Paritok-4B 小模型按「当前意图」条件化地做选择性压缩。

原型（规则版替代 4B 小模型，显式标注）：
  - 上下文 = 分块列表（工具输出/文件行）；意图 = 当前任务描述
  - 分块得分 = 与意图的词元重叠度（Jaccard 归一）
  - 预算内保留高分块（保持原顺序），对照基线 = 头部截断
评估：30% 预算下关键证据召回 > 头部截断基线。

运行：python -m mcpserver.agent_lab.prototypes.intent_conditioned_compression
"""
from __future__ import annotations

import re

import numpy as np


def tokenize(text: str) -> set[str]:
    """词元化：英文按词（关键证据用英文词，避免中文连写不分词问题）"""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_chunks(chunks: list[str], intent: str) -> np.ndarray:
    """意图条件打分：块与意图的词元重叠 / 几何归一（cosine 风格的集合相似）"""
    itok = tokenize(intent)
    scores = []
    for c in chunks:
        ctok = tokenize(c)
        if not ctok or not itok:
            scores.append(0.0)
            continue
        scores.append(len(itok & ctok) / np.sqrt(len(itok) * len(ctok)))
    return np.asarray(scores)


def compress(chunks: list[str], intent: str, budget: float = 0.3) -> list[int]:
    """意图条件压缩：保留得分最高的 budget 比例分块，按原顺序返回索引"""
    scores = score_chunks(chunks, intent)
    k = max(1, int(len(chunks) * budget))
    keep = np.argsort(scores)[::-1][:k]
    return sorted(int(i) for i in keep)


def head_baseline(chunks: list[str], budget: float = 0.3) -> list[int]:
    """基线：头部截断（Agent 默认全量前缀截断的常见做法）"""
    k = max(1, int(len(chunks) * budget))
    return list(range(k))


def mock_context(seed: int = 9, n: int = 40) -> tuple[list[str], list[int]]:
    """mock 上下文：n 个分块，其中 6 个含意图关键证据（deadlock/mutex 词，显式标注无真实数据）"""
    rng = np.random.default_rng(seed)
    fillers = ["log flush ok", "cache hit ratio normal", "config loaded",
               "heartbeat ok", "gc pause short", "index rebuild done"]
    chunks: list[str] = []
    crit: list[int] = []
    crit_pos = set(int(i) for i in rng.choice(n, size=6, replace=False))
    for i in range(n):
        if i in crit_pos:
            chunks.append(f"chunk{i} worker thread deadlock detected mutex deadlock wait timeout")
            crit.append(i)
        else:
            chunks.append(f"chunk{i} {fillers[i % len(fillers)]}")
    return chunks, crit


def evaluate(seed: int = 9, budget: float = 0.3) -> dict:
    """对比：意图条件压缩 vs 头部截断，在关键证据上的召回率"""
    chunks, crit = mock_context(seed)
    intent = "find deadlock root cause in worker mutex wait"
    kept = set(compress(chunks, intent, budget))
    head = set(head_baseline(chunks, budget))
    crit_set = set(crit)
    return dict(
        recall_intent=len(kept & crit_set) / len(crit_set),
        recall_head=len(head & crit_set) / len(crit_set),
        budget=budget,
        n_kept=len(kept),
        n_chunks=len(chunks),
    )


if __name__ == "__main__":
    r = evaluate()
    print(f"意图条件压缩：预算 {r['budget']:.0%}（保留 {r['n_kept']}/{r['n_chunks']} 块），"
          f"关键证据召回 {r['recall_intent']:.3f} vs 头部截断 {r['recall_head']:.3f}")
