"""语义网补层 · SemanticEngine（Phase 2：推理 + SPARQL 落地）

Phase 1 已落地 load()/is_a()；Phase 2 补 query()/infer()，并让 load() 物化 RDFS 闭包。
- _graph 保持"原始图"（五元组 + 本体），Phase 1 的三元组计数断言不破；
- 推理闭包单独存 _inferred / 惰性建 _full 图，query()/is_a() 在物化图上跑。
"""
from __future__ import annotations

from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef

from mcpserver.adapters.semantic_web.rdf_mapper import LK, uri


def _is_ttl_content(text: str) -> bool:
    """判定 ontology_ttl 是 Turtle 内容还是文件路径。

    我们自己的 ontology.ttl 用 @prefix 开头；路径字符串不含换行且不像 Turtle。
    """
    return (
        "\n" in text
        or text.lstrip().startswith(("@prefix", "@base"))
        or "<" in text
    )


class SemanticEngine:
    """确定性语义推理引擎：RDF 化 + 本体规则推理 + SPARQL 查询。"""

    def __init__(self) -> None:
        # 原始图（五元组 RDF 化 + 本体），推理闭包不入此图
        self._graph: Graph = Graph()
        # 推理出的新增事实（infer() 的返回），load() 时算一次
        self._inferred: list[dict] | None = None
        # 物化图（原始 + 推理闭包），query/is_a 用，惰性构建
        self._full: Graph | None = None

    # ---- 内部 ----

    def _load_ontology(self, ontology_ttl: str) -> None:
        """把本体灌进图。ontology_ttl 可以是 Turtle 内容或 .ttl 文件路径。"""
        if _is_ttl_content(ontology_ttl):
            self._graph.parse(data=ontology_ttl, format="turtle")
        else:
            path = Path(ontology_ttl)
            if not path.is_file():
                raise FileNotFoundError(f"本体文件不存在: {ontology_ttl}")
            self._graph.parse(str(path), format="turtle")

    def _run_inference(self) -> None:
        """跑一次 RDFS 推理，记录新增事实并让物化图失效重建。"""
        from mcpserver.adapters.semantic_web.reasoner import compute_rdfs_closure, infer_facts

        inferred = compute_rdfs_closure(self._graph)
        self._inferred = infer_facts(self._graph, inferred)
        self._full = None  # 数据变了，旧物化图作废

    def _full_graph(self) -> Graph:
        """物化图 = 原始图 + 推理闭包，惰性构建并缓存。"""
        if self._full is None:
            from mcpserver.adapters.semantic_web.reasoner import compute_rdfs_closure

            g = Graph()
            for t in self._graph:
                g.add(t)
            for t in compute_rdfs_closure(self._graph):
                g.add(t)
            self._full = g
        return self._full

    def _graph_triple_count(self) -> int:
        return len(self._graph)

    # ---- SPEC 3.3 接口 ----

    def load(self, quintuples: list[dict], ontology_ttl: str) -> None:
        """清空图 → 灌入五元组（RDF 化）+ 本体 → 跑一次推理。

        Args:
            quintuples: GRAG 五元组列表（(S, S_type, P, O, O_type) 结构）。
            ontology_ttl: 本体 Turtle 文件路径或内容。
        """
        from mcpserver.adapters.semantic_web.rdf_mapper import map_quintuples

        # 清空图
        self._graph = Graph()
        # 本体先灌（含 subClassOf 链 / 子属性声明）
        self._load_ontology(ontology_ttl)
        # 五元组 RDF 化
        map_quintuples(quintuples, graph=self._graph)
        # 跑一次推理（物化 RDFS 闭包，结果只进 _inferred，不污染原始图）
        self._run_inference()

    def query(self, sparql: str) -> list[dict]:
        """通用 SPARQL 查询，返回绑定列表（在物化闭包图上跑）。"""
        from mcpserver.adapters.semantic_web.sparql_service import run_query

        return run_query(self._full_graph(), sparql)

    def is_a(self, entity: str, cls: str) -> bool:
        """语义判断：entity 是否是 cls 的实例/子类（走推理闭包）。

        用 SPARQL 属性路径 (subClassOf | rdf:type | lk:是)* 在物化图上走闭包：
        - 类级：木质素纳米颗粒 → subClassOf → 纳米材料 → subClassOf → 材料
        - 实例级：木质素NPs → rdf:type → 纳米材料 → subClassOf → 材料
        """
        e = uri(entity)
        c = uri(cls)
        sub = URIRef(RDFS.subClassOf)
        typ = URIRef(RDF.type)
        isa = URIRef(LK["是"])
        sparql = (
            "ASK { "
            f"<{e}> (<{sub}>|<{typ}>|<{isa}>)* <{c}> "
            "}"
        )
        qres = self._full_graph().query(sparql)
        return bool(qres)

    def infer(self) -> list[dict]:
        """跑 RDFS 规则推理，返回新推出的三元组列表（{s, p, o}）。"""
        if self._inferred is None:
            self._run_inference()
        return self._inferred
