"""LightRAG 轻量图索引最小原型（W73-04 · 图增强检索）。

依据 docs/lightrag-图检索-评估.md：在向量/关键词检索之上加一个「实体-关系
轻量图」索引层，多跳问答时用图检索补充，比全量 GraphRAG 便宜。

原型（纯 stdlib，无依赖）：
  - 实体抽取：大写词/名词短语启发式（诚实降级，无 NLP 依赖）
  - 共现建边：同一文档内共现实体连边（权重累加）
  - graph_retrieve(query)：查询实体 → 邻居扩展 → 返回相关文档（多跳）

运行：
  python tools/lightrag_graph.py
"""
from __future__ import annotations

import re
from collections import defaultdict

_STOP = {"THE", "A", "AN", "AND", "OR", "OF", "IN", "ON", "TO", "FOR", "WITH", "IS", "ARE"}


def extract_entities(text: str) -> set[str]:
    """启发式实体抽取：连续首字母大写的词（或已知专名），去停用词。"""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]+", text)
    ents = set()
    buf: list[str] = []
    for t in tokens:
        if t[0].isupper() and t.upper() not in _STOP:
            buf.append(t)
        else:
            if buf:
                ents.add(" ".join(buf))
                buf = []
    if buf:
        ents.add(" ".join(buf))
    return ents or {t for t in tokens if t.upper() not in _STOP}


class LightGraphIndex:
    """轻量实体-关系图索引。"""

    def __init__(self) -> None:
        self.edges: dict[tuple[str, str], set[str]] = defaultdict(set)  # (a,b) -> 文档集合
        self.doc_entities: dict[str, set[str]] = {}

    def add_document(self, doc_id: str, text: str) -> None:
        ents = extract_entities(text)
        self.doc_entities[doc_id] = ents
        lst = sorted(ents)
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                self.edges[(lst[i], lst[j])].add(doc_id)

    def neighbors(self, entity: str) -> set[str]:
        out = set()
        for (a, b) in self.edges:
            if a == entity:
                out.add(b)
            elif b == entity:
                out.add(a)
        return out

    def graph_retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """查询实体 → 一跳邻居扩展 → 按共享实体数排序返回文档。"""
        q_ents = extract_entities(query)
        scores: dict[str, int] = defaultdict(int)
        for e in q_ents:
            # 直接命中
            for (a, b), docs in self.edges.items():
                if e in (a, b):
                    for d in docs:
                        scores[d] += 2
            # 一跳邻居
            for nb in self.neighbors(e):
                for (a, b), docs in self.edges.items():
                    if nb in (a, b):
                        for d in docs:
                            scores[d] += 1
        if not scores:
            # 回退：按文档与查询实体的交集
            for doc_id, ents in self.doc_entities.items():
                scores[doc_id] = len(ents & q_ents)
        return [d for d, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:top_k]


if __name__ == "__main__":
    idx = LightGraphIndex()
    idx.add_document("d1", "Alice works at Google and uses TensorFlow.")
    idx.add_document("d2", "Bob develops PyTorch at Meta.")
    idx.add_document("d3", "Google and Meta collaborate on AI.")
    print("graph_retrieve('Google TensorFlow'):", idx.graph_retrieve("Google TensorFlow"))
