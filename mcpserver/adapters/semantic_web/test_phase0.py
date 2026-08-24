"""Phase 0 测试：接口协议 + 骨架。

验收（SEMANTIC-WEB-SPEC-v1.md 3.3 / 五·Phase 0）：
- `from mcpserver.adapters.semantic_web.engine import SemanticEngine` 可 import
- 四个方法（load / query / is_a / infer）签名与 SPEC 3.3 完全一致
- 到 Phase 2 实现落地：空引擎优雅降级（query/infer 空、is_a False）
- schemas.Quintuple / Triple 字段与 SPEC 3.1 映射规则一致
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根 /workspace

from mcpserver.adapters.semantic_web.engine import SemanticEngine
from mcpserver.adapters.semantic_web.schemas import Quintuple, Triple, quintuple_from_raw


def test_import():
    assert SemanticEngine is not None
    print("✅ SemanticEngine 可 import")


def test_method_signatures():
    """四方法签名必须与 SPEC 3.3 逐字段一致。"""
    sig_load = inspect.signature(SemanticEngine.load)
    assert list(sig_load.parameters) == ["self", "quintuples", "ontology_ttl"], list(sig_load.parameters)
    # from __future__ import annotations 会把 -> None 变成字符串。
    assert sig_load.return_annotation in (None, "None"), f"load() 应无返回，实际={sig_load.return_annotation!r}"

    sig_query = inspect.signature(SemanticEngine.query)
    assert list(sig_query.parameters) == ["self", "sparql"], list(sig_query.parameters)

    sig_is_a = inspect.signature(SemanticEngine.is_a)
    assert list(sig_is_a.parameters) == ["self", "entity", "cls"], list(sig_is_a.parameters)

    sig_infer = inspect.signature(SemanticEngine.infer)
    assert list(sig_infer.parameters) == ["self"], list(sig_infer.parameters)
    print("✅ 四方法签名与 SPEC 3.3 一致")


def test_phase0_contract_implemented():
    """Phase 0 骨架已被 Phase 1-2 实现替换：四方法不再抛 NotImplementedError。

    Phase 0 验收是"空实现抛 NotImplementedError"，到 Phase 2 实现落地后
    该前提作废；这里改验"接口已实现 + 空引擎优雅降级"，签名约束不变。
    """
    eng = SemanticEngine()
    # 未加载时 query / infer 优雅返回空列表，不抛
    assert eng.query("SELECT * WHERE { ?s ?p ?o }") == []
    assert eng.infer() == []
    # 空图 is_a 返回 False，不抛
    assert eng.is_a("木质素纳米颗粒", "材料") is False
    print("✅ 四方法已实现（非 NotImplementedError），空引擎优雅降级")


def test_quintuple_schema_fields():
    """Quintuple 字段与 SPEC 3.1 映射规则一致：S/S_type/P/O/O_type。"""
    q = Quintuple(s="木质素NPs", s_type="实体", p="是", o="纳米材料", o_type="实体")
    assert q.to_tuple() == ("木质素NPs", "实体", "是", "纳米材料", "实体")
    # 兼容三元组形态：O_type 缺省为空 → 宾语当字面量
    q2 = quintuple_from_raw(("木质素NPs", "是", "纳米材料"))
    assert q2.o_type == "" and q2.s == "木质素NPs"
    print("✅ Quintuple schema 字段与 SPEC 3.1 一致")


def test_triple_schema_fields():
    t = Triple(s="http://lumo.local/knowledge#木质素NPs", p="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
               o="http://lumo.local/knowledge#材料", is_uri=True)
    assert t.to_tuple() == (t.s, t.p, t.o)
    print("✅ Triple schema 字段可正常构造")


if __name__ == "__main__":
    test_import()
    test_method_signatures()
    test_phase0_contract_implemented()
    test_quintuple_schema_fields()
    test_triple_schema_fields()
    print("\n🎉 Phase 0 全部通过")
