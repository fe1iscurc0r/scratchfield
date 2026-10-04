"""W69-08 融合 · 无框架手写 RAG（吸收 ai-engineer-notebooks 的「无框架手写」思路，MIT）

手写 embedding（词袋/哈希）、余弦检索、BM25 打分——不用 LangChain/LlamaIndex 等框架，
与「不引新依赖」铁律一致。作为陆墨科研工具链「最小可懂实现」的参考模块。

纯 numpy/stdlib。
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

__all__ = ["build_vocab", "bow_embed", "cosine_sim", "bm25_score", "retrieve"]


def build_vocab(docs: list[str]) -> list[str]:
    """词表（按出现顺序去重）。"""
    vocab: list[str] = []
    for d in docs:
        for w in _tokenize(d):
            if w not in vocab:
                vocab.append(w)
    return vocab


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in text.split() if w.isalnum()]


def bow_embed(text: str, vocab: list[str]) -> np.ndarray:
    """手写词袋 embedding（无框架）。"""
    counts = Counter(_tokenize(text))
    return np.array([counts.get(w, 0) for w in vocab], dtype=float)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def bm25_score(query: str, doc: str, k1: float = 1.5, b: float = 0.75) -> float:
    """手写 BM25（单文档，简化：以全部语料平均长度归一化）。"""
    q = _tokenize(query)
    d = _tokenize(doc)
    doc_counts = Counter(d)
    dl = len(d)
    avgdl = max(dl, 1)  # 简化：单文档场景 avgdl≈dl
    score = 0.0
    for t in q:
        f = doc_counts.get(t, 0)
        if f == 0:
            continue
        idf = math.log(1.0 + 1.0)  # 简化 IDF（单文档语料）
        denom = f + k1 * (1 - b + b * dl / avgdl)
        score += idf * f * (k1 + 1) / denom
    return score


def retrieve(query: str, docs: list[str], top_k: int = 3) -> list[tuple[int, float]]:
    """混合检索：BM25 得分 + 词袋余弦，取 top_k。"""
    vocab = build_vocab(docs)
    qv = bow_embed(query, vocab)
    scored = []
    for i, d in enumerate(docs):
        dv = bow_embed(d, vocab)
        score = bm25_score(query, d) + 0.5 * cosine_sim(qv, dv)
        scored.append((i, score))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]
