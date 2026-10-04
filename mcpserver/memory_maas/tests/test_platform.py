"""03-04 platform_source 归一化验收测试（claude-mem 授粉）。

跑法: python -m pytest mcpserver/memory_maas/tests/test_platform.py -q
覆盖：枚举与别名归一 / 三端写时打标（weixin/qqbot/cli/local）/
      provenance 必填四字段（source/ts/confidence/origin_rank）/
      平台过滤查询 / 打标写后不可改 / 旧库迁移默认 local / core 集成。
"""
from __future__ import annotations

import sqlite3

import pytest

from mcpserver.memory_maas.core import MemoryMaasError
from mcpserver.memory_maas.entities import (
    EntityValidationError,
    PlatformSource,
    TypedMemoryStore,
    normalize_platform,
)


@pytest.fixture
def store(tmp_path):
    s = TypedMemoryStore(tmp_path / "e.db")
    yield s
    s.close()


# ---------------------------------------------------------------- 枚举 + 归一

def test_platform_enum_values():
    assert PlatformSource.WEIXIN.value == "weixin"
    assert PlatformSource.QQBOT.value == "qqbot"
    assert PlatformSource.CLI.value == "cli"
    assert PlatformSource.LOCAL.value == "local"


def test_normalize_platform_aliases():
    assert normalize_platform("qq") == "qqbot"      # lumo_gateway 用 "qq"
    assert normalize_platform("wechat") == "weixin"
    assert normalize_platform("wx") == "weixin"
    assert normalize_platform("terminal") == "cli"
    assert normalize_platform("QQ") == "qqbot"      # 大小写归一


def test_normalize_platform_defaults_local():
    assert normalize_platform(None) == "local"
    assert normalize_platform("") == "local"
    assert normalize_platform("  ") == "local"
    assert normalize_platform("local") == "local"


def test_normalize_platform_invalid_raises():
    with pytest.raises(EntityValidationError):
        normalize_platform("telegram")
    with pytest.raises(EntityValidationError):
        normalize_platform(123)


# ---------------------------------------------------------------- 写时打标

def test_three_platforms_tagged_at_write(store):
    ids = {}
    for p in ("weixin", "qqbot", "cli", "local"):
        ids[p] = store.add(f"来自 {p} 的记忆", platform=p)
    for p, eid in ids.items():
        got = store.get(eid)
        assert got["platform_source"] == p
        assert got["provenance"]["source"] == p


def test_qqbot_alias_tagged_via_normalize(store):
    eid = store.add("QQ 群里的问答", platform="qq")  # 三端透传走别名归一
    assert store.get(eid)["platform_source"] == "qqbot"


def test_invalid_platform_rejected_at_write(store):
    with pytest.raises(EntityValidationError):
        store.add("脏标记忆", platform="tiktok")
    assert store.count() == 0  # fail-fast，不留脏标


def test_platform_immutable_after_write(store):
    eid = store.add("写时定标", platform="weixin")
    with pytest.raises(EntityValidationError):  # 供应链铁律：不后改
        store.update(eid, platform_source="qqbot")
    assert store.get(eid)["platform_source"] == "weixin"


# ---------------------------------------------------------------- provenance 必填

def test_provenance_always_present_with_four_fields(store):
    got = store.get(store.add("默认 local 写入"))
    prov = got["provenance"]
    assert got["platform_source"] == "local"
    assert set(prov) == {"source", "ts", "confidence", "origin_rank"}
    assert prov["source"] == "local"
    assert prov["ts"] == pytest.approx(got["created_at"])
    assert prov["origin_rank"] == got["source_rank"]
    assert prov["confidence"] == 0.9  # rank 0 → 0.9


def test_provenance_confidence_maps_source_rank(store):
    for rank, conf in ((0, 0.9), (1, 0.7), (2, 0.4), (3, 0.2)):
        got = store.get(store.add(f"rank {rank}", source_rank=rank))
        assert got["provenance"]["confidence"] == conf
        assert got["provenance"]["origin_rank"] == rank


# ---------------------------------------------------------------- 查询过滤

def test_platform_filter_query(store):
    wx = store.add("微信记忆", platform="weixin")
    store.add("QQ 记忆", platform="qq")   # 落库为 qqbot
    store.add("本地记忆")
    hits = store.list_entities(platform="weixin")
    assert [e["id"] for e in hits] == [wx]
    hits = store.list_entities(platform="qq")  # 别名过滤同样归一
    assert len(hits) == 1 and hits[0]["platform_source"] == "qqbot"
    hits = store.list_entities(platform="local")
    assert len(hits) == 1
    assert len(store.list_entities()) == 3  # 不过滤时全量


def test_platform_filter_composes_with_type(store):
    store.add("微信洞察", type="insight", platform="weixin")
    store.add("微信笔记", type="note", platform="weixin")
    hits = store.list_entities(type="insight", platform="weixin")
    assert len(hits) == 1 and hits[0]["type"] == "insight"


# ---------------------------------------------------------------- 旧库迁移

def test_legacy_db_migration_defaults_local(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))  # 手造 03-04 之前的旧 schema
    conn.executescript(
        """
        CREATE TABLE memory_entities (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]', pinned INTEGER NOT NULL DEFAULT 0,
            source_rank INTEGER NOT NULL DEFAULT 0,
            isolation INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
        INSERT INTO memory_entities (id, type, content, created_at)
        VALUES ('old1', 'note', '历史记忆', 0.0);
        """)
    conn.commit()
    conn.close()
    s = TypedMemoryStore(db)  # 打开即迁移
    try:
        got = s.get("old1")
        assert got["platform_source"] == "local"  # 历史行默认 local
        assert got["provenance"]["source"] == "local"
        eid = s.add("迁移后新写", platform="cli")  # 迁移后可正常打标
        assert s.get(eid)["platform_source"] == "cli"
    finally:
        s.close()


# ---------------------------------------------------------------- core 集成

def test_core_add_memory_platform_roundtrip(tmp_path):
    from mcpserver.memory_maas.core import MemoryMaasCore
    core = MemoryMaasCore(tmp_path)
    try:
        r = core.add_memory("用户在微信里说的方案", type="note",
                            platform="wechat")
        entity = r["entity"]
        assert entity["platform_source"] == "weixin"
        assert entity["provenance"]["source"] == "weixin"
        # 过滤面
        hits = core.query(platform="weixin")["entities"]
        assert [e["id"] for e in hits] == [r["id"]]
        with pytest.raises(MemoryMaasError):
            core.add_memory("非法平台", platform="tiktok")
    finally:
        core.close()


def test_core_capture_observation_platform_roundtrip(tmp_path):
    from mcpserver.memory_maas.core import MemoryMaasCore
    core = MemoryMaasCore(tmp_path)
    try:
        r = core.capture_observation("s1", "标题", "叙述", platform="qqbot")
        assert r["entity"]["platform_source"] == "qqbot"
        # 哈希去重不受 platform 影响（同内容幂等语义保持）
        r2 = core.capture_observation("s1", "标题", "叙述", platform="qqbot")
        assert r2["deduped"] and r2["id"] == r["id"]
    finally:
        core.close()
