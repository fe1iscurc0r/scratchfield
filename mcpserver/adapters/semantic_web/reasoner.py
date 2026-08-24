"""语义网补层 · RDFS 规则推理（Phase 2）

rdflib 7.x 已移除 rdflib.plugins.reasoner 插件，这里按 W3C RDF 语义的
RDFS 规则子集手动物化闭包（标准规则，不发明算法）：

  rdfs5  rdfs:subClassOf 传递闭包
  rdfs7  rdfs:subPropertyOf 应用：(s P o) 且 P subPropertyOf Q → (s Q o)
  rdfs9  (x rdf:type C) 且 C subClassOf D → (x rdf:type D)
  rdfs2  P rdfs:domain C 且 (s P o) → (s rdf:type C)
  rdfs3  P rdfs:range  C 且 (s P o) → (o rdf:type C)

本体把 lk:是 声明为 rdf:type 的子属性（见 ontology.ttl），
于是 rdfs7 会把 (X 是 C) 推到 (X rdf:type C)，再经 rdfs9 上溯 subClassOf 链，
最终推出 (木质素NPs, rdf:type, 材料) 这类原图不存在的传递关系。

compute_rdfs_closure() 返回"新增三元组"，不改动入参图；
是否物化回图由调用方（engine）决定，便于旁路降级。
"""
from __future__ import annotations

from rdflib import OWL, RDF, RDFS, Graph, URIRef

from mcpserver.adapters.semantic_web.rdf_mapper import LK


def _apply_rdfs_rules(triples: set) -> set:
    """对当前三元组集合跑一轮 RDFS 规则，返回本轮新增（已在图中的自动跳过）。"""
    added: set = set()

    subclass = [t for t in triples if t[1] == RDFS.subClassOf]
    subprop = [t for t in triples if t[1] == RDFS.subPropertyOf]
    dom: dict = {}
    rng: dict = {}
    for t in triples:
        if t[1] == RDFS.domain:
            dom.setdefault(t[0], []).append(t[2])
        elif t[1] == RDFS.range:
            rng.setdefault(t[0], []).append(t[2])

    def _add(s, p, o) -> None:
        t = (s, p, o)
        if t not in triples and t not in added:
            added.add(t)

    # rdfs5: subClassOf 传递闭包
    for (c1, _, c2) in subclass:
        for (c3, _, c4) in subclass:
            if c2 == c3 and c1 != c4:
                _add(c1, RDFS.subClassOf, c4)

    # rdfs7 / rdfs2 / rdfs3：把 subPropertyOf 索引成 {P: [Q,...]} 便于按谓词查
    subprop_map: dict = {}
    for (pp, _, q) in subprop:
        subprop_map.setdefault(pp, []).append(q)

    for (s, p, o) in list(triples):
        for q in subprop_map.get(p, ()):
            if p != q:
                _add(s, q, o)
        for c in dom.get(p, ()):
            _add(s, RDF.type, c)
        for c in rng.get(p, ()):
            _add(o, RDF.type, c)

    # rdfs9: rdf:type × subClassOf → rdf:type（本轮新加的 type 也参与）
    for (s, p, o) in list(triples) + list(added):
        if p == RDF.type:
            for (c, _, d) in subclass:
                if o == c and o != d:
                    _add(s, RDF.type, d)

    return added


def compute_rdfs_closure(graph: Graph) -> set:
    """跑 RDFS 物化闭包，返回新增三元组（不修改入参 graph）。

    固定点迭代：每轮只加新三元组，直到不再变化。图规模小，够用。
    """
    triples: set = set(graph)
    new: set = set()
    while True:
        added = _apply_rdfs_rules(triples)
        if not added:
            return new
        triples |= added
        new |= added


def infer_facts(graph: Graph, inferred: set) -> list[dict]:
    """把推导出的三元组转成"新增事实"列表（{s, p, o} 字符串形式）。

    呈现规则（对齐 SPEC：本层 lk:是 是 rdf:type 的子属性，是用户视角的实例谓词）：
    - 推导出的 rdf:type，s/o 都是 lk: 资源 → 以 lk:是 呈现；原图已有该 是 事实则跳过；
    - 其余 rdf:type 推导（type owl:Thing、字面量类型）是 RDFS 技术产物，不进入事实；
    - subClassOf 闭包等其余推导原样呈现（终点为 owl:Thing 的纯系统推导跳过）。
    """
    # 原图里已存在的"X 是 Y"（含字面量判等只需 s/o 对）
    known_isa = {(s, o) for (s, _, o) in graph}

    out: list[dict] = []
    for (s, p, o) in inferred:
        if p == RDF.type:
            if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                continue  # 字面量类型推导，跳过
            if not str(o).startswith(str(LK)):
                continue  # owl:Thing 等系统类型，跳过
            if (s, o) in known_isa:
                continue  # 原图已有 是 事实，不算新增
            out.append({"s": str(s), "p": str(LK["是"]), "o": str(o)})
        elif o == OWL.Thing:
            continue  # subClassOf owl:Thing 等系统推导，跳过
        else:
            out.append({"s": str(s), "p": str(p), "o": str(o)})
    return out
