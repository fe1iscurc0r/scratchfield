"""语义网补层 · SPARQL 查询服务（Phase 2）

对 rdflib Graph 跑 SPARQL，把结果统一成 {变量: 字符串} 绑定列表，
供上层（engine.query / 桥接层）直接消费。URI 给完整 URI，字面量给值。
"""
from __future__ import annotations

from rdflib import Graph


def run_query(graph: Graph, sparql: str) -> list[dict]:
    """跑一条 SPARQL，返回绑定列表。

    SELECT → [{var: str}, ...]（一行一个 dict）
    ASK   → [{"result": True}] / [{"result": False}]
    """
    qres = graph.query(sparql)

    # ASK 查询 rdflib 直接返回 bool
    if isinstance(qres, bool):
        return [{"result": qres}]
    if getattr(qres, "type", None) == "ASK":
        return [{"result": bool(qres.askAnswer)}]

    # SELECT：一行 → {变量名: 字符串}
    rows: list[dict] = []
    for row in qres:
        rows.append({var: str(val) for var, val in row.asdict().items()})
    return rows
