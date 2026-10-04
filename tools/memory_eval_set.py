# -*- coding: utf-8 -*-
"""记忆评测集 + 召回率回归（W62-03 · 防检索退化）。

依据 docs/Agent-Memory-Techniques-选型地图.md 的 P1 缺口：建 30 条「查询 → 应
召回条目」用例做回归，覆盖 type/project 维度（mock 记忆条目）。提供关键词检索
基线 + recall/precision/MRR 计算，输出基线指标。

纯标准库。运行：python tools/memory_eval_set.py
"""
from __future__ import annotations

import re
from typing import Callable

TYPES = ("decision", "insight", "handoff", "note")
PROJECTS = ("rf", "material", "agent", "neko")


def _build_entries(n: int = 30) -> list[dict]:
    """构造 n 条 mock 记忆条目（type/project 维度 + 唯一 keyword）。"""
    entries = []
    for i in range(n):
        t = TYPES[i % len(TYPES)]
        p = PROJECTS[i % len(PROJECTS)]
        entries.append({
            "id": f"mem-{i:02d}",
            "type": t,
            "project": p,
            "content": f"{p} {t} 记忆条目 keyword-{i:02d} 关于频谱感知与参数调优",
        })
    return entries


def _build_cases(n: int = 30) -> list[tuple[str, str]]:
    """构造 n 条「查询 → 应召回条目 id」用例。"""
    return [(f"keyword-{i:02d}", f"mem-{i:02d}") for i in range(n)]


def keyword_retrieve(query: str, entries: list[dict], top_k: int = 5) -> list[str]:
    """简单关键词检索：按 query 词与 content 的重合度打分，返回 top_k 条目 id。"""
    q_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for e in entries:
        c_terms = set(re.findall(r"[a-z0-9]+", e["content"].lower()))
        score = len(q_terms & c_terms)
        scored.append((score, e["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [eid for _, eid in scored[:top_k]]


def _dcg_hit(retrieved: list[str], expected: str) -> float:
    if expected not in retrieved:
        return 0.0
    return 1.0 / (retrieved.index(expected) + 1)  # MRR 用倒数排名


def compute_metrics(cases: list[tuple[str, str]], entries: list[dict],
                    retrieve: Callable, k: int = 5) -> dict:
    """计算 recall@k / precision@k / MRR。"""
    recall = 0.0
    precision = 0.0
    mrr = 0.0
    for query, expected in cases:
        retrieved = retrieve(query, entries, k)
        recall += 1.0 if expected in retrieved else 0.0
        precision += (1.0 if expected in retrieved else 0.0) / k
        mrr += _dcg_hit(retrieved, expected)
    n = len(cases)
    return {
        "n": n,
        "recall_at_k": round(recall / n, 4),
        "precision_at_k": round(precision / n, 4),
        "mrr": round(mrr / n, 4),
    }


def run_eval(k: int = 5) -> dict:
    entries = _build_entries(30)
    cases = _build_cases(30)
    return compute_metrics(cases, entries, keyword_retrieve, k)


if __name__ == "__main__":
    m = run_eval()
    print(f"[记忆评测基线] recall@5={m['recall_at_k']} precision@5={m['precision_at_k']} mrr={m['mrr']}")
