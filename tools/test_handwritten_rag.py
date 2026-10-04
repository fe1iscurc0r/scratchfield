"""W69-08 融合测试：无框架手写 RAG。

运行：python -m pytest tools/test_handwritten_rag.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from handwritten_rag import bm25_score, bow_embed, build_vocab, cosine_sim, retrieve

DOCS = [
    "neural networks for spectrum sensing",
    "graph database memory sidecar",
    "materials biomass molecular potential",
    "neural network embedding inversion attack",
]


def test_build_vocab_and_bow_embed():
    vocab = build_vocab(DOCS)
    assert "neural" in vocab
    emb = bow_embed("neural networks", vocab)
    assert emb[vocab.index("neural")] == 1.0
    assert emb[vocab.index("networks")] == 1.0


def test_cosine_similarity_identical_is_one():
    a = bow_embed("a b c", ["a", "b", "c"])
    assert abs(cosine_sim(a, a) - 1.0) < 1e-9


def test_bm25_prefers_matching_terms():
    assert bm25_score("neural", DOCS[0]) > bm25_score("neural", DOCS[2])


def test_retrieve_returns_relevant_doc():
    res = retrieve("neural networks", DOCS, top_k=1)
    assert res[0][0] == 0  # 第 0 篇最相关


def test_retrieve_ranks_descending():
    res = retrieve("neural", DOCS, top_k=4)
    scores = [s for _, s in res]
    assert scores == sorted(scores, reverse=True)
