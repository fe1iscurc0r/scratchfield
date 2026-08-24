"""语义网补层 · GRAG 五元组 → RDF 三元组映射（Phase 1）

映射规则严格照 SEMANTIC-WEB-SPEC-v1.md 3.1：

| 五元组字段 | RDF 侧 |
|-----------|--------|
| S（主语）    | lk:{slug(S)}，URI 资源 |
| P（谓词）    | lk:{slug(P)}，URI 属性 |
| O（宾语）    | 字面量（^^xsd:string）或 lk:{slug(O)}（若 O 是实体） |
| S_type / O_type | rdf:type lk:{slug(type)} |

实体 vs 字面量判定：O_type 非空 → 实体（URI）；O_type 为空 → 字面量。主语永远 URI。

命名空间：
- lk:  = http://lumo.local/knowledge#（本地知识）
- rdf/rdfs/owl/xsd = W3C 标准命名空间

slug()：把中文/空格/特殊字符转成合法的 RDF 本地名（保留中文字符，
RDF 1.1 支持 Unicode 本地名），保证标签可逆还原。
"""
from __future__ import annotations

import unicodedata

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

LK = Namespace("http://lumo.local/knowledge#")
"""本地知识命名空间（SPEC 3.1）。"""


def slug(text: str) -> str:
    """实体/谓词标签 → RDF 本地名。

    保留中英文、数字、下划线；空白压成单个下划线；
    其余字符按 NFC 归一化后若仍非法则用 Unicode 码点转义（_uXXXX_）。
    RDF 1.1 Turtle 本地名允许大部分 Unicode，但为稳妥统一转义。
    """
    if not text:
        return "_"
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    for ch in text.strip():
        if ch.isalnum() or ch == "_":
            out.append(ch)
        elif ch.isspace():
            out.append("_")
        else:
            out.append(f"_u{ord(ch):04X}_")
    name = "".join(out).strip("_") or "_"
    # 本地名不能以数字开头
    if name[0].isdigit():
        name = "_" + name
    return name


def uri(label: str) -> URIRef:
    """标签 → lk: 命名空间 URI。"""
    return LK[slug(label)]


def node_for(label: str, o_type: str) -> URIRef | Literal:
    """按 SPEC 3.1 判定宾语是实体还是字面量。

    o_type 非空 → 实体 URI；为空 → xsd:string 字面量。
    """
    if o_type:
        return uri(label)
    return Literal(label, datatype=XSD.string)


def map_quintuple(q, graph: Graph | None = None) -> list[tuple]:
    """把一条 GRAG 五元组映射为 RDF 三元组列表（不含 rdf:type 则只返回主三元组）。

    Args:
        q: Quintuple（或 (S, S_type, P, O, O_type) 形态）。
        graph: 可选，非 None 时直接把三元组写进图。

    Returns:
        [(s, p, o), ...] RDF 三元组列表（rdflib 术语）。
    """
    from mcpserver.adapters.semantic_web.schemas import Quintuple, quintuple_from_raw

    if not isinstance(q, Quintuple):
        q = quintuple_from_raw(q)

    s_uri = uri(q.s)
    p_uri = uri(q.p)
    o_node = node_for(q.o, q.o_type)

    triples: list[tuple] = [(s_uri, p_uri, o_node)]
    if q.s_type:
        triples.append((s_uri, RDF.type, uri(q.s_type)))
    if q.o_type and q.o:
        triples.append((o_node, RDF.type, uri(q.o_type)))  # type: ignore[arg-type]

    if graph is not None:
        for t in triples:
            graph.add(t)
    return triples


def map_quintuples(quintuples, graph: Graph | None = None) -> list[tuple]:
    """批量映射：五元组列表 → 扁平 RDF 三元组列表。"""
    out: list[tuple] = []
    for q in quintuples:
        out.extend(map_quintuple(q, graph=graph))
    return out
