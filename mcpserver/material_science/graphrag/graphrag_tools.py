"""GraphRAG MCP 工具注册（SPEC-02 Phase 2）。

工具与 academic/duckdb/writing 同构：fn(params: dict) -> dict。
"""
from __future__ import annotations

from typing import Any

from . import importer, query
from .store import GraphStore, default_graph_dir
from .vector_index import build_index


def _tool_graphrag_import(params: dict) -> dict[str, Any]:
    """全量重建图谱 + 向量索引（vault 笔记 + academic MODEL_INTERFACE）。

    可选参数：vault_dir / academic_dir（缺省用仓内默认路径）。
    """
    store = GraphStore(params.get("graph_dir"))
    r = importer.import_corpus(store, vault_dir=params.get("vault_dir"),
                               academic_dir=params.get("academic_dir"))
    if not r["success"]:
        return r
    idx = build_index(store)
    return {**r, "vector_index": idx}


def _tool_graphrag_query(params: dict) -> dict[str, Any]:
    """图谱检索：question 必填，top_k 可选（默认 3）。返回路径 + 原文摘录。"""
    question = params.get("question", "")
    if not question:
        return {"success": False, "error": "缺参数: question"}
    return query.graph_query(question, top_k=int(params.get("top_k", 3)),
                             graph_dir=params.get("graph_dir"))


def _tool_graphrag_stats(params: dict) -> dict[str, Any]:
    """图谱规模统计（节点/边/社区）。"""
    store = GraphStore(params.get("graph_dir") or default_graph_dir())
    if not store.load():
        return {"success": False, "error": "图谱未构建，请先运行 graphrag_import"}
    return {"success": True, **store.stats()}


def register_graphrag_tools(agent) -> None:
    """注入 GraphRAG 工具到 agent.tools。"""
    agent.tools["graphrag_import"] = _tool_graphrag_import
    agent.tools["graphrag_query"] = _tool_graphrag_query
    agent.tools["graphrag_stats"] = _tool_graphrag_stats
