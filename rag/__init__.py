"""
RAG 管线模块 - 本地材料科研知识检索
基于 sqlite-vec + bge-small-zh 实现
"""
from rag.rag_service import RAGService, get_rag_service

__all__ = ["RAGService", "get_rag_service"]
