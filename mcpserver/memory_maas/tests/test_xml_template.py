"""03-03 压缩块 XML 模板验收测试（claude-mem 授粉）。

跑法: python -m pytest mcpserver/memory_maas/tests/test_xml_template.py -q
覆盖：模板渲染/roundtrip / checkpoint 词表校验 / 三层解析容错（ET→正则→
整段降级）/ consolidate 升级（XML 合并块 + 自由文本降级旧行为）/ 模板可配置。
"""
from __future__ import annotations

import pytest

from mcpserver.memory_maas import maintenance
from mcpserver.memory_maas.entities import TypedMemoryStore
from mcpserver.memory_maas.xml_template import (
    CHECKPOINTS,
    TEMPLATE_MODES,
    get_template,
    merge_contents,
    parse_memory_block,
    render_memory_block,
)


@pytest.fixture
def store(tmp_path):
    s = TypedMemoryStore(tmp_path / "e.db")
    yield s
    s.close()


# ---------------------------------------------------------------- 渲染

def test_render_standard_block():
    xml = render_memory_block(title="T", fact="F", narrative="N",
                              concept="C", checkpoint="learned")
    assert xml.startswith("<memory>")
    assert "<title>T</title>" in xml and "<fact>F</fact>" in xml
    assert "<narrative>N</narrative>" in xml and "<concept>C</concept>" in xml
    assert "<checkpoint>learned</checkpoint>" in xml
    assert xml.rstrip().endswith("</memory>")


def test_render_escapes_xml_specials():
    xml = render_memory_block(fact="a < b & c", checkpoint="notes")
    assert "a &lt; b &amp; c" in xml


def test_render_rejects_invalid_checkpoint():
    for bad in ("", "unknown", "DONE"):
        with pytest.raises(ValueError):
            render_memory_block(checkpoint=bad)


def test_checkpoints_vocabulary():
    assert CHECKPOINTS == ("investigated", "learned", "completed",
                           "next_steps", "notes")


# ---------------------------------------------------------------- 解析容错

def test_parse_roundtrip():
    xml = render_memory_block(title="结论", fact="FTS5 可用", narrative="过程",
                              concept="检索", checkpoint="completed")
    got = parse_memory_block(xml)
    assert got["parsed"] is True
    assert got["title"] == "结论" and got["fact"] == "FTS5 可用"
    assert got["checkpoint"] == "completed"


def test_parse_tolerates_missing_fields():
    got = parse_memory_block("<memory><title>只有标题</title></memory>")
    assert got["parsed"] is True
    assert got["title"] == "只有标题"
    assert got["fact"] == "" and got["narrative"] == ""
    assert got["checkpoint"] == "notes"  # 缺省兜底


def test_parse_tolerates_invalid_checkpoint():
    got = parse_memory_block(
        "<memory><fact>x</fact><checkpoint>啥也不是</checkpoint></memory>")
    assert got["parsed"] is True
    assert got["checkpoint"] == "notes"


def test_parse_tolerates_noise_around_block():
    src = '前置说明\n<memory>\n  <title>T</title>\n</memory>\n后缀说明'
    got = parse_memory_block(src)
    assert got["parsed"] is True and got["title"] == "T"


def test_parse_regex_fallback_on_broken_xml():
    # 块内字段含未转义 & → ET 解析失败，正则层兜住
    src = "<memory><fact>A & B</fact><checkpoint>learned</checkpoint></memory>"
    got = parse_memory_block(src)
    assert got["parsed"] is True
    assert got["fact"] == "A & B"
    assert got["checkpoint"] == "learned"


def test_parse_degrades_plain_text_to_raw():
    src = "完全没结构的自由文本蒸馏结果"
    got = parse_memory_block(src)
    assert got == {"parsed": False, "raw": src}


def test_parse_never_raises():
    for weird in ("", None, "<memory><title>未闭合", "<<>>", 12345):
        got = parse_memory_block(weird)  # type: ignore[arg-type]
        assert isinstance(got, dict)


# ---------------------------------------------------------------- 合并内核

def test_merge_xml_blocks():
    blocks = [
        render_memory_block(title="T1", fact="F1", narrative="N1",
                            concept="C1", checkpoint="investigated"),
        render_memory_block(title="T2", fact="F1", narrative="N2",
                            concept="C1", checkpoint="investigated"),
    ]
    out = merge_contents(blocks)
    assert out["used_xml"] is True
    assert "<memory>" in out["content"]
    assert "T1" in out["content"] and "T2" in out["content"]
    assert out["content"].count("F1") == 1  # 重复 fact 去重
    assert "<checkpoint>investigated</checkpoint>" in out["content"]


def test_merge_checkpoint_conflict_falls_back_notes():
    blocks = [
        render_memory_block(fact="a", checkpoint="completed"),
        render_memory_block(fact="b", checkpoint="learned"),
    ]
    out = merge_contents(blocks)
    assert out["used_xml"] is True
    assert "<checkpoint>notes</checkpoint>" in out["content"]


def test_merge_degrades_when_any_member_is_plain_text():
    blocks = [
        render_memory_block(title="T", fact="a", checkpoint="learned"),
        "纯自由文本成员",
    ]
    out = merge_contents(blocks)
    assert out["used_xml"] is False          # 降级为纯文本拼接
    assert "<memory>" not in out["content"]  # 不产出半结构 XML 混排
    assert "title: T" in out["content"]      # 可解析块摊平为字段行
    assert "fact: a" in out["content"]
    assert "纯自由文本成员" in out["content"]  # 内容不丢


# ---------------------------------------------------------------- 模板可配置

def test_template_modes_configurable():
    assert "default" in TEMPLATE_MODES and "compact" in TEMPLATE_MODES
    compact = get_template("compact")
    assert compact.fields == ("title", "fact", "checkpoint")
    xml = render_memory_block(title="T", fact="F", narrative="不渲染",
                              concept="不渲染", checkpoint="learned",
                              config=compact)
    assert "<narrative>" not in xml and "<concept>" not in xml


def test_get_template_unknown_mode_raises():
    with pytest.raises(ValueError):
        get_template("haiku")


# ---------------------------------------------------------------- consolidate 升级

def _seed_xml_note(store, tags, fact, checkpoint="learned"):
    return store.add(render_memory_block(
        title=f"关于{tags[0]}", fact=fact, checkpoint=checkpoint), tags=tags)


def test_consolidate_produces_xml_block(store, tmp_path):
    _seed_xml_note(store, ["射频"], "方案 A 可行")
    _seed_xml_note(store, ["射频"], "方案 B 超预算")
    # XML 块自身超默认 120 字符，放宽上限验证模板路
    r = maintenance.consolidate(store, max_content_len=400,
                                snapshots_dir=tmp_path / "snaps")
    assert r["merged_groups"] == 1 and r["xml_merges"] == 1
    merged = store.get(r["groups"][0]["base_id"])
    assert "<memory>" in merged["content"]
    assert "方案 A 可行" in merged["content"] and "方案 B 超预算" in merged["content"]
    # 被吸收条目已删，关系保留 consolidated_from 血统
    assert len(merged["relations"]) == 1
    assert store.count() == 1


def test_consolidate_plain_text_keeps_legacy_behavior(store, tmp_path):
    # 自由文本组：降级为旧行为整段拼接，不产出 <memory>
    store.add("短笔记一", tags=["日常"])
    store.add("短笔记二", tags=["日常"])
    r = maintenance.consolidate(store, snapshots_dir=tmp_path / "snaps")
    assert r["merged_groups"] == 1 and r["xml_merges"] == 0
    merged = store.get(r["groups"][0]["base_id"])
    assert "<memory>" not in merged["content"]
    assert "短笔记一" in merged["content"] and "短笔记二" in merged["content"]


def test_consolidate_mixed_group_degrades(store, tmp_path):
    _seed_xml_note(store, ["混合"], "结构化事实")
    store.add("同标签的自由文本", tags=["混合"])
    r = maintenance.consolidate(store, max_content_len=400,
                                snapshots_dir=tmp_path / "snaps")
    assert r["merged_groups"] == 1 and r["xml_merges"] == 0
    merged = store.get(r["groups"][0]["base_id"])
    assert "<memory>" not in merged["content"]
    assert "fact: 结构化事实" in merged["content"]  # 块摊平为字段行
    assert "同标签的自由文本" in merged["content"]


def test_consolidate_template_mode_validated(store, tmp_path):
    _seed_xml_note(store, ["x"], "事实")
    _seed_xml_note(store, ["x"], "事实2")
    with pytest.raises(ValueError):
        maintenance.consolidate(store, template_mode="haiku",
                                max_content_len=400,
                                snapshots_dir=tmp_path / "snaps")
