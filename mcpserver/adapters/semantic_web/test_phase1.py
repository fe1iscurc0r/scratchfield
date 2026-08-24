"""Phase 1 测试：RDF 映射 + 本体 + engine.load() / is_a()。

验收（SEMANTIC-WEB-SPEC-v1.md 五·Phase 1）：
- 喂 3 条示例五元组，len(list(graph)) 含五元组映射 + 本体三元组
- is_a("木质素纳米颗粒", "材料") 返回 True（走 subClassOf 链）
- 映射规则 3.1：主语永远 URI；O_type 空 → 字面量；非空 → 实体 URI
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根 /workspace

from rdflib import OWL, RDF, RDFS, XSD, Literal

from mcpserver.adapters.semantic_web.engine import SemanticEngine
from mcpserver.adapters.semantic_web.rdf_mapper import LK, uri

ONTOLOGY_TTL = str(Path(__file__).resolve().parent / "ontology.ttl")

# 3 条示例五元组（SPEC 3.1 结构：S, S_type, P, O, O_type）
SAMPLE_QUINTUPLES = [
    ("木质素NPs", "实体", "是", "纳米材料", "实体"),       # 实体宾语
    ("木质素NPs", "实体", "应用于", "生物医药", ""),       # 字面量宾语（O_type 空）
    ("共熔凝胶样品A", "实体", "是", "共熔凝胶", "实体"),    # 实体宾语
]


def test_load_graph_contains_quintuples_and_ontology():
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    g = eng._graph
    triples = list(g)
    print(f"[triple count] 图内共 {len(triples)} 条三元组（本体 10 + 五元组映射去重后 7，S_type 重复自动去重）")

    # 1) 本体三元组在
    assert (LK["材料"], RDFS.subClassOf, OWL.Thing) in g, "本体：材料 subClassOf owl:Thing 缺失"
    assert (LK["纳米材料"], RDFS.subClassOf, LK["材料"]) in g, "本体：纳米材料 subClassOf 材料 缺失"
    assert (LK["木质素纳米颗粒"], RDFS.subClassOf, LK["纳米材料"]) in g, "本体：木质素纳米颗粒 subClassOf 纳米材料 缺失"

    # 2) 五元组映射在
    # 主三元组：S 永远 URI 资源
    assert (uri("木质素NPs"), uri("是"), uri("纳米材料")) in g, "映射：木质素NPs lk:是 纳米材料 缺失"
    # O_type 空 → 字面量（^^xsd:string）
    assert (uri("木质素NPs"), uri("应用于"), Literal("生物医药", datatype=XSD.string)) in g, "映射：O_type 空应映射为 xsd:string 字面量"
    assert (uri("共熔凝胶样品A"), uri("是"), uri("共熔凝胶")) in g, "映射：共熔凝胶样品A lk:是 共熔凝胶 缺失"
    # S_type / O_type → rdf:type
    assert (uri("木质素NPs"), RDF.type, uri("实体")) in g, "S_type 应映射为 rdf:type"
    assert (uri("纳米材料"), RDF.type, uri("实体")) in g, "O_type 非空应映射为实体 rdf:type"

    # 3) 数量：本体 10 + 映射去重后 7 = 17
    assert len(triples) == 17, f"图内三元组数量应为 17，实际 {len(triples)}"
    print("✅ load() 图含五元组映射 + 本体三元组")


def test_is_a_subclass_chain():
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    assert eng.is_a("木质素纳米颗粒", "材料") is True, "木质素纳米颗粒 → 纳米材料 → 材料（subClassOf 链）应为 True"
    assert eng.is_a("共熔凝胶", "材料") is True, "共熔凝胶 → 水凝胶 → 材料 应为 True"
    assert eng.is_a("共熔凝胶", "纳米材料") is False, "共熔凝胶 与 纳米材料 无 subClassOf 关系，应为 False"
    assert eng.is_a("木质素纳米颗粒", "水凝胶") is False, "木质素纳米颗粒 与 水凝胶 无关，应为 False"
    print("✅ is_a() 走 subClassOf 链判断正确")


def test_is_a_instance_via_isa_predicate():
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    # 实例级：木质素NPs lk:是 纳米材料 + 纳米材料 subClassOf 材料 → 材料
    assert eng.is_a("木质素NPs", "纳米材料") is True, "实例 木质素NPs lk:是 纳米材料 应为 True"
    assert eng.is_a("木质素NPs", "材料") is True, "实例经 subClassOf 链上溯到 材料 应为 True"
    print("✅ is_a() 实例级判断（lk:是 + subClassOf 链）正确")


if __name__ == "__main__":
    test_load_graph_contains_quintuples_and_ontology()
    test_is_a_subclass_chain()
    test_is_a_instance_via_isa_predicate()
    print("\n🎉 Phase 1 全部通过")
