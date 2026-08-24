"""语义网补层 · 包初始化。

在 GRAG（summer_memory）之上补"确定性语义推理"：
GRAG 五元组 → RDF 化 → rdflib 图 → RDFS 规则推理 → 新推三元组 → 回补查询。

设计原则（照 SEMANTIC-WEB-SPEC-v1.md 二）：
- 协议无关：语义层只认 RDF 三元组 + SPARQL，底层是 rdflib 内存图还是 pyoxigraph 不关心。
- 先接口后实现：Phase 0 定死四个方法签名，实现随便换。
- 旁路接入：只读 GRAG，不动 summer_memory 写路径；本模块挂了，GRAG 原样照跑。

模块：schemas / rdf_mapper / engine / reasoner / sparql_service / bridge。
"""
from __future__ import annotations

from mcpserver.adapters.semantic_web.engine import SemanticEngine

__all__ = ["SemanticEngine", "bridge", "rdf_mapper", "reasoner", "schemas", "sparql_service"]
