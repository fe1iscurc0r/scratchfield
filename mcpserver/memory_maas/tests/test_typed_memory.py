"""X-01 typed 记忆实体模型验收测试。

跑法: python -m pytest mcpserver/memory_maas/tests/test_typed_memory.py -q
覆盖：实体 CRUD / type 校验 / filter / pinned / relations 建立与遍历 /
      向后兼容（无 type 默认 note）/ 非法 type 报错 / 关系循环防护。
"""
from __future__ import annotations

import pytest

from mcpserver.memory_maas.entities import (
    EntityValidationError,
    MemoryEntity,
    MemoryType,
    TypedMemoryStore,
    normalize_type,
)


@pytest.fixture
def store(tmp_path):
    s = TypedMemoryStore(tmp_path / "e.db")
    yield s
    s.close()


# ---------------------------------------------------------------- 枚举 + 校验

def test_memory_type_enum_values():
    assert MemoryType.DECISION.value == "decision"
    assert MemoryType.INSIGHT.value == "insight"
    assert MemoryType.HANDOFF.value == "handoff"
    assert MemoryType.NOTE.value == "note"


def test_normalize_type_defaults_to_note():
    # 向后兼容：不传 / 传空 → note
    assert normalize_type(None) == "note"
    assert normalize_type("") == "note"
    assert normalize_type("note") == "note"
    assert normalize_type("DECISION") == "decision"


def test_normalize_type_invalid_raises():
    with pytest.raises(EntityValidationError):
        normalize_type("memory")
    with pytest.raises(EntityValidationError):
        normalize_type("  ")


def test_memory_entity_dataclass_validation():
    e = MemoryEntity(id="e1", type="insight", content="热物性方案",
                     tags=["物理", "物理"], source_rank=1)
    assert e.type == "insight"
    assert e.tags == ["物理"]  # 去重去空
    with pytest.raises(EntityValidationError):
        MemoryEntity(id="bad", type="nope")


# ---------------------------------------------------------------- CRUD + 兼容

def test_add_and_get_roundtrip(store):
    eid = store.add("决策：用 DSRC 方案 A", type="decision", tags=["射频"])
    got = store.get(eid)
    assert got is not None
    assert got["type"] == "decision"
    assert got["content"] == "决策：用 DSRC 方案 A"
    assert got["tags"] == ["射频"]
    assert got["pinned"] is False
    assert got["source_rank"] == 0
    assert store.count() == 1


def test_add_defaults_to_note_backward_compat(store):
    # 旧格式：不传 type → 默认 note
    eid = store.add("一条纯文本记忆")
    got = store.get(eid)
    assert got["type"] == "note"


def test_illegal_type_raises_on_add(store):
    with pytest.raises(EntityValidationError):
        store.add("内容", type="invalid-type")


def test_delete_entity(store):
    eid = store.add("待删除", type="note")
    assert store.delete(eid) is True
    assert store.get(eid) is None
    assert store.delete("ghost") is False


# ---------------------------------------------------------------- filter

def test_filter_by_type(store):
    store.add("决策 A", type="decision")
    store.add("洞察 B", type="insight")
    store.add("笔记 C", type="note")
    decisions = store.list_entities(type="decision")
    assert len(decisions) == 1 and decisions[0]["content"] == "决策 A"
    notes = store.list_entities(type="note")
    assert len(notes) == 1 and notes[0]["content"] == "笔记 C"


def test_filter_by_tags(store):
    store.add("A", type="note", tags=["x", "y"])
    store.add("B", type="note", tags=["y", "z"])
    store.add("C", type="note", tags=["z"])
    # AND 语义：同时含 x 与 y
    assert len(store.list_entities(tags=["x", "y"])) == 1
    assert len(store.list_entities(tags=["y"])) == 2
    assert len(store.list_entities(tags=["nope"])) == 0


def test_pin_unpin_and_filter(store):
    eid = store.add("重要笔记", type="note", pinned=True)
    store.add("普通笔记", type="note")
    pinned = store.list_entities(pinned=True)
    assert len(pinned) == 1 and pinned[0]["id"] == eid
    assert len(store.list_entities(pinned=False)) == 1
    store.set_pinned(eid, False)
    assert len(store.list_entities(pinned=True)) == 0


# ---------------------------------------------------------------- 关系图谱

def test_relations_establish_and_traverse(store):
    a = store.add("根决策", type="decision")
    b = store.add("子洞察", type="insight")
    c = store.add("孙笔记", type="note")
    store.add_relation(a, b, rel_type="derived")
    store.add_relation(b, c, rel_type="notes")
    rels = store.get_relations(a)
    assert len(rels) == 1 and rels[0]["to_id"] == b
    assert rels[0]["rel_type"] == "derived"
    # 单跳遍历：a → b
    t = store.traverse(a, max_hops=1)
    assert t["visited"] == [a, b]
    assert [n["id"] for n in t["hops"][0]] == [b]


def test_relation_cycle_protection(store):
    a = store.add("节点 A", type="note")
    b = store.add("节点 B", type="note")
    # 自关联拒绝
    with pytest.raises(EntityValidationError):
        store.add_relation(a, a)
    # 两节点环可建立，但遍历必须终止（visited 集合防环）
    store.add_relation(a, b)
    store.add_relation(b, a)
    t = store.traverse(a, max_hops=3)
    assert set(t["visited"]) == {a, b}


# ---------------------------------------------------------------- core 委托

def test_core_add_memory_and_query(tmp_path):
    from mcpserver.memory_maas.core import MemoryMaasCore

    core = MemoryMaasCore(tmp_path / "core_typed")
    core.start()
    try:
        r = core.add_memory("用 CoolProp 算水在 300K 的密度",
                            type="insight", tags=["物理", "CoolProp"])
        assert r["ok"] and r["type"] == "insight"
        q = core.query(type="insight")
        assert q["count"] >= 1
        assert q["entities"][0]["content"] == "用 CoolProp 算水在 300K 的密度"
        # 向后兼容：无 type 默认 note
        r2 = core.add_memory("裸文本")
        assert r2["type"] == "note"
        assert core.query(type="note")["count"] >= 1
    finally:
        core.close()
