"""GraphRAG 查询 API（SPEC-02 Phase 2 任务 2.3：社区导航 + 语义检索融合）。

验收口径："找 XX 材料的制备方法" 5 秒内返回图谱路径 + 原文。
- 路径：命中 section ←mentions→ 相邻 section ←contains← 所属 doc
- 原文：命中节的正文摘录（截断展示）
- 社区：命中节所在社区的文档清单（导航用）
模型只在索引构建/查询编码时加载；查询本体是矩阵乘 + 边遍历，毫秒级。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .store import GraphStore, default_graph_dir
from .vector_index import VectorIndex

_SNIPPET_CHARS = 320


def _snippet(text: str, limit: int = _SNIPPET_CHARS) -> str:
    t = " ".join(text.split())
    return t if len(t) <= limit else t[:limit] + "…"


def graph_query(question: str, top_k: int = 3,
                graph_dir: str | Path | None = None) -> dict[str, Any]:
    """语义检索命中节 → 展开图谱路径与原文。未建图时如实报错。"""
    t0 = time.time()
    if not question or not question.strip():
        return {"success": False, "error": "问题为空"}

    store = GraphStore(graph_dir or default_graph_dir())
    if not store.load():
        return {"success": False,
                "error": "图谱未构建，请先运行 graphrag_import（vault + academic 语料）"}
    index = VectorIndex(store)
    hits = index.search(question, top_k=max(top_k, 1))
    if not hits:
        return {"success": False, "error": "无命中节点（图谱为空或问题无相关词元）"}

    results = []
    for h in hits:
        node = store.nodes.get(h["node_id"])
        if not node:
            continue
        # 图谱路径：命中节 --mentions--> 邻居（≤3）；所属文档经 contains 回溯
        related = []
        for nb in store.neighbors(h["node_id"], relation="mentions")[:3]:
            nn = store.nodes.get(nb["node"])
            if nn:
                related.append({"label": nn["label"], "source": nn["source"],
                                "relation": nb["relation"]})
        doc_labels = []
        for nb in store.neighbors(h["node_id"], relation="contains"):
            dn = store.nodes.get(nb["node"])
            if dn:
                doc_labels.append(dn["label"])
        comm = store.community_of(h["node_id"])
        comm_docs = sorted({
            store.nodes[n]["label"] for n in comm
            if n in store.nodes and store.nodes[n]["type"] == "doc"
        })
        results.append({
            "section": node["label"],
            "source": node["source"],
            "score": h["score"],
            "path": " → ".join(doc_labels + [node["label"]]) or node["label"],
            "snippet": _snippet(node["text"]),
            "related_sections": related,
            "community_docs": comm_docs[:6],
        })

    return {
        "success": True,
        "question": question,
        "backend": hits[0]["backend"],
        "results": results,
        "graph_stats": store.stats(),
        "elapsed_s": round(time.time() - t0, 3),
    }
