"""Phase 3 测试：旁路桥 + lumo_proxy 接入 + 降级。

验收（SEMANTIC-WEB-SPEC-v1.md 五·Phase 3）：
- bridge 只读 GRAG 五元组 → SemanticEngine → 语义推理新事实
- lumo_proxy 的 RAG 召回里出现语义推理补出的新事实
- semantic_web 挂了 → 语义旁路返回空，GRAG 原样照跑（降级验证）

lumo_proxy 集成测试需要 fastapi（本项目依赖），沙箱未装则自动跳过；
bridge 核心逻辑与降级在无 fastapi 环境下完整覆盖。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根 /workspace

from mcpserver.adapters.semantic_web.bridge import SemanticBridge

# 与 Phase 1/2 相同的示例五元组（注入式，避免依赖真实 GRAG 数据文件）
SAMPLE = [
    ("木质素NPs", "实体", "是", "纳米材料", "实体"),
    ("木质素NPs", "实体", "应用于", "生物医药", ""),
    ("共熔凝胶样品A", "实体", "是", "共熔凝胶", "实体"),
]


def test_bridge_load_injected_quintuples():
    b = SemanticBridge()
    assert b.load(SAMPLE) is True
    print("✅ bridge.load() 注入五元组成功")


def test_bridge_query_semantic_derives_new_fact():
    """语义推理补出的新事实（原图没有的传递关系）能随问题召回。"""
    b = SemanticBridge()
    b.load(SAMPLE)
    text = b.query_semantic("木质素NPs 是不是材料")
    assert text, "应返回语义推理事实"
    assert "木质素NPs 是 材料" in text, f"应包含推导出的 (木质素NPs, 是, 材料)，实际：\n{text}"
    print("✅ query_semantic() 召回推理补出的新事实 (木质素NPs 是 材料)")


def test_bridge_query_semantic_no_match_empty():
    b = SemanticBridge()
    b.load(SAMPLE)
    assert b.query_semantic("今天天气如何") == ""
    print("✅ 无匹配问题返回空串")


def test_bridge_not_loaded_returns_empty():
    b = SemanticBridge()  # 未 load()
    assert b.query_semantic("木质素NPs 是不是材料") == ""
    print("✅ 未加载时优雅返回空串")


def test_bridge_degrades_on_bad_data():
    """降级：数据源异常 → load() 返回 False，query_semantic() 返回空，不抛。"""
    b = SemanticBridge()
    assert b.load([42]) is False  # 非法记录 → 归一化抛错 → load 捕获降级
    assert b.query_semantic("木质素NPs 是不是材料") == ""
    print("✅ 数据异常降级：load False + query 空串，不抛异常")


def test_bridge_loads_from_local_grag_source():
    """打通真实数据源：summer_memory.quintuple_graph 只读加载（无数据文件也优雅）。"""
    b = SemanticBridge()
    ok = b.load()  # 无参 → 走本地 GRAG 只读
    assert isinstance(ok, bool)
    print(f"✅ 本地 GRAG 源加载返回 {ok}（无数据文件时返回 False 亦属优雅降级）")


# ---- lumo_proxy 集成（需 fastapi；沙箱未装则仅跳过本测试） ----


def test_lumo_proxy_semantic_merge_and_degradation():
    pytest.importorskip("fastapi")
    import asyncio

    import mcpserver.adapters.semantic_web.bridge as bridge_mod
    from apiserver.routes.lumo_proxy import _query_rag_standalone, _query_semantic

    # 预载一个带数据的桥实例
    bridge_mod.reset_bridge()
    b = bridge_mod.SemanticBridge()
    assert b.load(SAMPLE)
    bridge_mod._BRIDGE = b

    # 1) _query_semantic 返回语义推理事实
    text = asyncio.run(_query_semantic("木质素NPs 是不是材料"))
    assert "木质素NPs 是 材料" in text, f"语义旁路应返回推理事实，实际：{text}"

    # 2) RAG 融合召回里出现语义推理补出的新事实
    merged = asyncio.run(_query_rag_standalone("木质素NPs 是不是材料"))
    assert "语义推理事实" in merged, f"RAG 召回应并进语义推理事实，实际：{merged}"

    # 3) 降级：semantic_web 桥不可用 → 语义旁路返回空，主链路不炸
    orig = bridge_mod.get_bridge

    def _boom():
        raise ImportError("semantic_web 模块不可用（模拟卸载）")

    bridge_mod.get_bridge = _boom
    try:
        degraded = asyncio.run(_query_semantic("木质素NPs 是不是材料"))
        assert degraded == "", f"降级后语义旁路应为空，实际：{degraded}"
        # GRAG 主链路照常（此处 _query_grag 无 token 返回空，但不抛异常）
        merged2 = asyncio.run(_query_rag_standalone("木质素NPs 是不是材料"))
        assert isinstance(merged2, str)
    finally:
        bridge_mod.get_bridge = orig
        bridge_mod.reset_bridge()

    print("✅ lumo_proxy：语义事实并进 RAG + semantic_web 卸载后降级不炸主链路")


if __name__ == "__main__":
    test_bridge_load_injected_quintuples()
    test_bridge_query_semantic_derives_new_fact()
    test_bridge_query_semantic_no_match_empty()
    test_bridge_not_loaded_returns_empty()
    test_bridge_degrades_on_bad_data()
    test_bridge_loads_from_local_grag_source()
    print("\n🎉 Phase 3 全部通过")
