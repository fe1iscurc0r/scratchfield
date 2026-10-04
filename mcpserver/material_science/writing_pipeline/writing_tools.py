"""写作管线 MCP 工具注册（SPEC-02 Phase 4）。

工具签名统一 fn(params: dict) -> dict，与 academic_tools/duckdb_tools 同构。
"""
from __future__ import annotations

from typing import Any

from . import bibtex, pipeline


def _tool_bibtex_add(params: dict) -> dict[str, Any]:
    """新增文献条目：key/title/authors/year 必填，journal/doi/entry_type 可选。"""
    missing = [k for k in ("key", "title", "authors", "year") if not params.get(k)]
    if missing:
        return {"success": False, "error": f"缺参数: {', '.join(missing)}"}
    return bibtex.add_entry(
        params["key"], params["title"], params["authors"], params["year"],
        journal=params.get("journal", ""), doi=params.get("doi", ""),
        entry_type=params.get("entry_type", "article"))


def _tool_bibtex_search(params: dict) -> dict[str, Any]:
    """按关键词检索文献库。"""
    kw = params.get("keyword", "")
    if not kw:
        return {"success": False, "error": "缺参数: keyword"}
    hits = bibtex.find_entries(kw)
    return {"success": True, "keyword": kw, "count": len(hits),
            "entries": [{k: v for k, v in h.items()} for h in hits]}


def _tool_writing_draft(params: dict) -> dict[str, Any]:
    """选题→初稿一条龙（demo 入口）：topic 必填，csv_path 可选。"""
    topic = params.get("topic", "")
    if not topic:
        return {"success": False, "error": "缺参数: topic"}
    return pipeline.run_pipeline(topic, csv_path=params.get("csv_path"),
                                 authors=params.get("authors", "Lumo (陆墨) 与研究者"))


def register_writing_tools(agent) -> None:
    """注入写作管线工具到 agent.tools。"""
    agent.tools["writing_bibtex_add"] = _tool_bibtex_add
    agent.tools["writing_bibtex_search"] = _tool_bibtex_search
    agent.tools["writing_draft"] = _tool_writing_draft
