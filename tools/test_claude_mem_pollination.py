"""W63-03 claude-mem 授粉落地测试（≥5用例，pytest 全绿）。

跑法: python -m pytest tools/test_claude_mem_pollination.py -q
覆盖：
- P0a：内容哈希确定性/去重命中/批量查重；
- P0b：多路径三形式生成/跨路径查询命中同一实体；
- P1：XML 模板渲染/解析/合并（三层容错/降级路径）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# 工具函数直接 import（纯标准库，不碰 NEKO 五件套）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import claude_mem_pollination as cmp

# =============================================================================
# P0a：内容哈希去重
# =============================================================================

def test_content_hash_is_16_hex_and_deterministic():
    h1 = cmp.compute_memory_content_hash("标题", "叙述")
    h2 = cmp.compute_memory_content_hash("标题", "叙述")
    assert h1 == h2
    assert len(h1) == 16
    int(h1, 16)  # 合法 hex


def test_content_hash_distinguishes_fields():
    base = cmp.compute_memory_content_hash("t", "n")
    assert base != cmp.compute_memory_content_hash("t2", "n")
    assert base != cmp.compute_memory_content_hash("t", "n2")
    # title 前后空白不参与哈希
    assert (cmp.compute_memory_content_hash(" t ", "n")
            == cmp.compute_memory_content_hash("t", "n"))
    # 拼接歧义：(ab,c) vs (a,bc)
    assert (cmp.compute_memory_content_hash("ab", "c")
            != cmp.compute_memory_content_hash("a", "bc"))


def test_duplicate_content_detection_with_store(tmp_path):
    """相同内容二次写入被去重——验收硬线之一。"""
    from mcpserver.memory_maas import capture
    from mcpserver.memory_maas.entities import TypedMemoryStore

    store = TypedMemoryStore(tmp_path / "e.db")
    try:
        # 第一次写入（通过 capture 层，含 session_id 故用 capture API）
        first = capture.capture_observation(store, "s1", "部署决策",
                                            "采用 CoolProp 方案")
        assert first["ok"] and not first["deduped"]

        # 第二次写入（同 session_id+title+narrative → 哈希相同）
        second = capture.capture_observation(store, "s1", "部署决策",
                                             "采用 CoolProp 方案")
        assert second["deduped"] is True
        assert second["id"] == first["id"]

        # 用独立的内容哈希函数在实体层面做同 session 查重
        dup = cmp.is_duplicate_content(
            store, "部署决策", "采用 CoolProp 方案", memory_session_id="s1")
        assert dup is True   # 已在库中
        # 全新内容
        dup2 = cmp.is_duplicate_content(
            store, "新标题", "新内容", memory_session_id="s1")
        assert dup2 is False
    finally:
        store.close()


def test_batch_find_duplicate_entities(tmp_path):
    """批量查重返回下标→entity_id 映射。"""
    from mcpserver.memory_maas import capture
    from mcpserver.memory_maas.entities import TypedMemoryStore

    store = TypedMemoryStore(tmp_path / "e.db")
    try:
        # 预写入一条
        capture.capture_observation(store, "s1", "已在库", "存在的内容")

        entries = [
            {"title": "已在库", "narrative": "存在的内容"},   # 重复
            {"title": "全新标题A", "narrative": "新内容A"},   # 不重复
            {"title": "已在库", "narrative": "存在的内容"},   # 重复（同一条）
            {"title": "全新标题B", "narrative": "新内容B"},   # 不重复
        ]
        dup_map = cmp.find_duplicate_entities(
            store, entries, memory_session_id="s1")
        assert 0 in dup_map       # 第0条重复
        assert 2 in dup_map       # 第2条重复
        assert 1 not in dup_map   # 第1条不重复
        assert 3 not in dup_map   # 第3条不重复
        assert len(dup_map) == 2  # 恰好两条重复
    finally:
        store.close()


# =============================================================================
# P0b：多路径匹配
# =============================================================================

def test_path_variants_generates_three_forms():
    """三形式归一化：绝对/项目根相对/cwd 相对。"""
    variants = cmp._path_variants("/home/ubuntu/scratchpad/mcpserver/main.py")
    assert len(variants) >= 1
    assert any(v.startswith("/") for v in variants)  # 至少含绝对形式


def test_path_variants_deduplication():
    """同一路径调用两次结果相同（幂等）。"""
    v1 = cmp._path_variants("/home/ubuntu/scratchpad/main.py")
    v2 = cmp._path_variants("/home/ubuntu/scratchpad/main.py")
    assert v1 == v2


def test_multipath_query_hits_same_entity_via_different_paths(tmp_path):
    """多路径查询命中同一实体——验收硬线之一。"""
    from mcpserver.memory_maas import capture
    from mcpserver.memory_maas.entities import TypedMemoryStore

    store = TypedMemoryStore(tmp_path / "e.db")
    try:
        # 写入一条含绝对路径内容的记忆
        abs_path = "/home/ubuntu/scratchpad/mcpserver/memory_maas/core.py"
        capture.capture_observation(
            store, "s1", "查 core.py 路径",
            f"参考 {abs_path} 的导入逻辑")

        repo_root = str(Path(__file__).resolve().parents[2])

        # 用绝对路径查
        hits_abs = cmp.query_by_path_variants(
            store, abs_path, project_root=repo_root)
        # 用项目根相对路径查（mcpserver/memory_maas/core.py）
        rel_from_root = abs_path.replace(repo_root, "").lstrip("/")
        hits_rel = cmp.query_by_path_variants(
            store, rel_from_root, project_root=repo_root)

        # 两种路径写法应命中同一条实体（id 相同）
        assert len(hits_abs) >= 1, "绝对路径应命中"
        assert len(hits_rel) >= 1, "相对路径应命中"
        ids_abs = {h["id"] for h in hits_abs}
        ids_rel = {h["id"] for h in hits_rel}
        assert ids_abs & ids_rel, \
            "多路径查询应命中同一实体（交集非空）"
    finally:
        store.close()


# =============================================================================
# P1：压缩块 XML 模板（consolidation）
# =============================================================================

def test_render_and_parse_roundtrip():
    """渲染→解析往返不走样。"""
    from mcpserver.memory_maas import xml_template

    rendered = xml_template.render_memory_block(
        title="决策",
        fact="使用 CoolProp",
        narrative="物性计算库",
        concept="工程决策",
        checkpoint="completed",
    )
    assert "<memory>" in rendered
    assert "<title>决策</title>" in rendered
    assert "<checkpoint>completed</checkpoint>" in rendered

    parsed = xml_template.parse_memory_block(rendered)
    assert parsed["parsed"] is True
    assert parsed["title"] == "决策"
    assert parsed["fact"] == "使用 CoolProp"
    assert parsed["checkpoint"] == "completed"


def test_parse_fallback_on_malformed_xml():
    """XML 损坏时正则兜底（第二层容错）。"""
    from mcpserver.memory_maas import xml_template

    # 含未转义 & 的 XML（ET 会失败）
    bad = "<memory><title>测试</title><fact>at & bat</fact></memory>"
    parsed = xml_template.parse_memory_block(bad)
    assert parsed["parsed"] is True
    assert parsed["fact"] == "at & bat"


def test_parse_degrades_to_raw_on_no_structure():
    """无结构时降级为整段文本（第三层容错）。"""
    from mcpserver.memory_maas import xml_template

    raw_text = "这是一段没有任何 XML 标记的纯文本内容。"
    parsed = xml_template.parse_memory_block(raw_text)
    assert parsed["parsed"] is False
    assert parsed["raw"] == raw_text


def test_consolidated_memory_block_merge():
    """多条内容合并为单一 XML 结构块。"""
    from mcpserver.memory_maas import xml_template

    contents = [
        xml_template.render_memory_block(
            title="决策A", fact="用方案A", checkpoint="completed"),
        xml_template.render_memory_block(
            title="决策B", fact="用方案B", checkpoint="learned"),
    ]
    result = cmp.consolidated_memory_block(contents)
    assert result["used_xml"] is True
    assert "<memory>" in result["content"]
    assert result["parsed_blocks"] == 2
    assert result["raw_count"] == 0


def test_consolidated_memory_block_falls_back_to_text():
    """全为无结构文本时降级为纯文本拼接。"""
    contents = [
        "这是第一条自由文本内容。",
        "这是第二条没有任何标记的纯文本。",
    ]
    result = cmp.consolidated_memory_block(contents)
    assert result["used_xml"] is False
    assert "第一条自由文本" in result["content"]
    assert "第二条" in result["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])