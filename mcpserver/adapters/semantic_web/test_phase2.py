"""Phase 2 测试：RDFS 推理 + SPARQL 查询。

验收（SEMANTIC-WEB-SPEC-v1.md 五·Phase 2）：
- infer() 推出 (木质素NPs, 是, 材料) —— 原图没有，靠 subClassOf 链推出来
- query() 跑 SELECT ?x WHERE { ?x rdfs:subClassOf lk:材料 }
  返回含 lk:纳米材料 和 lk:木质素纳米颗粒（subClassOf 传递闭包）
- 回归：Phase 1 的 is_a / 原始图三元组数量不破
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根 /workspace

from rdflib import RDFS

from mcpserver.adapters.semantic_web.engine import SemanticEngine
from mcpserver.adapters.semantic_web.rdf_mapper import LK, uri

ONTOLOGY_TTL = str(Path(__file__).resolve().parent / "ontology.ttl")
MATERIAL = f"<{LK['材料']!s}>"

# 与 Phase 1 相同的 3 条示例五元组
SAMPLE_QUINTUPLES = [
    ("木质素NPs", "实体", "是", "纳米材料", "实体"),       # 实体宾语
    ("木质素NPs", "实体", "应用于", "生物医药", ""),       # 字面量宾语
    ("共熔凝胶样品A", "实体", "是", "共熔凝胶", "实体"),    # 实体宾语
]


def _fact_pairs(eng: SemanticEngine) -> set[tuple[str, str, str]]:
    return {(f["s"], f["p"], f["o"]) for f in eng.infer()}


def test_infer_derives_isa_chain():
    """验收 1：infer() 推出 (木质素NPs, 是, 材料)。"""
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    target = (str(uri("木质素NPs")), str(LK["是"]), str(uri("材料")))
    pairs = _fact_pairs(eng)
    assert target in pairs, f"infer() 应推出 {target}，实际 {sorted(pairs)}"

    # 原图已有的 (木质素NPs, 是, 纳米材料) 不算"新增事实"，不应重复出现
    dup = (str(uri("木质素NPs")), str(LK["是"]), str(uri("纳米材料")))
    assert dup not in pairs, "已存在事实不应重复出现在 infer() 结果里"

    print("✅ infer() 推出 (木质素NPs, 是, 材料)，且不重复已有事实")


def test_query_subclass_closure():
    """验收 2：query() 返回 subClassOf 传递闭包成员。"""
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    rows = eng.query(f"SELECT ?x WHERE {{ ?x rdfs:subClassOf {MATERIAL} }}")
    xs = {r["x"] for r in rows}
    assert str(uri("纳米材料")) in xs, f"应含 lk:纳米材料，实际 {xs}"
    assert str(uri("木质素纳米颗粒")) in xs, f"传递闭包应含 lk:木质素纳米颗粒，实际 {xs}"
    print(f"✅ query() subClassOf 闭包返回 {len(xs)} 个子类")


def test_infer_returns_subclass_closure_fact():
    """infer() 也应带出 subClassOf 传递闭包（木质素纳米颗粒 subClassOf 材料）。"""
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    pair = (str(uri("木质素纳米颗粒")), str(RDFS.subClassOf), str(uri("材料")))
    assert pair in _fact_pairs(eng), "infer() 应带出 subClassOf 传递闭包"
    print("✅ infer() 带出 subClassOf 传递闭包")


def test_phase1_regression():
    """回归：load() 后原始图仍是 17 条，is_a 语义判断不破。"""
    eng = SemanticEngine()
    eng.load(SAMPLE_QUINTUPLES, ONTOLOGY_TTL)

    assert len(list(eng._graph)) == 17, "原始图应保持 17 条三元组（物化不入 _graph）"
    assert eng.is_a("木质素纳米颗粒", "材料") is True
    assert eng.is_a("木质素NPs", "材料") is True
    assert eng.is_a("共熔凝胶", "纳米材料") is False
    print("✅ Phase 1 回归：原始图 17 条 + is_a 判断保持")


def test_query_before_load_returns_empty():
    """未 load() 时 query() 优雅返回空列表，不抛异常。"""
    eng = SemanticEngine()
    assert eng.query(f"SELECT ?x WHERE {{ ?x rdfs:subClassOf {MATERIAL} }}") == []
    assert eng.infer() == []
    print("✅ 未加载时 query()/infer() 优雅降级为空")


if __name__ == "__main__":
    test_infer_derives_isa_chain()
    test_query_subclass_closure()
    test_infer_returns_subclass_closure_fact()
    test_phase1_regression()
    test_query_before_load_returns_empty()
    print("\n🎉 Phase 2 全部通过")
