"""材料科研 GraphRAG（SPEC-02 Phase 2：图谱 + bge-small-zh 向量 + 查询 API）。

用法（MCP 工具）：
1. graphrag_import  vault 笔记 + academic 接口文档 → 图（含向量索引），全量重建幂等
2. graphrag_query   语义检索 → 图谱路径 + 原文摘录 + 社区导航
3. graphrag_stats   图谱规模统计

数据默认 %APPDATA%/Lumo/graphrag/（LUMO_GRAPHRAG_DIR 可覆盖）。
只读旁路：不触碰 SQLite RAG 主链路（硬约束）。
"""
from . import importer, query, store, vector_index
from .graphrag_tools import register_graphrag_tools

__all__ = ["importer", "query", "store", "vector_index", "register_graphrag_tools"]
