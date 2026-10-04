"""X-02 自维护机制验收测试。

跑法: python -m pytest mcpserver/memory_maas/tests/test_maintenance.py -q
覆盖：sweep 保 pinned / sweep 清低价值 / consolidate 合并相似 /
      快照联动 / status 输出 / 空库不崩。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from mcpserver.memory_maas.entities import TypedMemoryStore
from mcpserver.memory_maas.maintenance import (
    consolidate,
    list_snapshots,
    maintenance_status,
    retention_sweep,
    snapshot,
)

OLD = time.time() - 40 * 86400  # 40 天前


@pytest.fixture
def store(tmp_path):
    # 与 maintenance._open_store 的库文件名保持一致（entities.db）
    s = TypedMemoryStore(tmp_path / "entities.db")
    yield s
    s.close()


# ---------------------------------------------------------------- sweep

def test_sweep_keeps_pinned(store):
    eid = store.add("重要笔记", type="note", pinned=True, created_at=OLD)
    store.add("旧普通笔记", type="note", created_at=OLD)
    r = retention_sweep(store, snapshots_dir=str(store.db_path.parent / "snaps"))
    assert eid not in r["swept"]
    assert store.get(eid) is not None  # pinned 永不删


def test_sweep_clears_low_value(store):
    # 低信任（source_rank≥2）且超龄 → 清
    low = store.add("未验证导入", type="note", source_rank=3, created_at=OLD)
    fresh = store.add("新鲜未验证", type="note", source_rank=3)
    r = retention_sweep(store, snapshots_dir=str(store.db_path.parent / "snaps"))
    assert low in r["swept"]
    assert fresh not in r["swept"]  # 未超龄保留
    assert store.get(low) is None


def test_sweep_keeps_trusted_decision(store):
    # 可信决策即使超龄也不清（decision 优先保留）
    d = store.add("超龄决策", type="decision", source_rank=0, created_at=OLD)
    r = retention_sweep(store, snapshots_dir=str(store.db_path.parent / "snaps"))
    assert d not in r["swept"]
    assert store.get(d) is not None


# ---------------------------------------------------------------- consolidate

def test_consolidate_merges_similar_notes(store):
    a = store.add("短的", type="note", tags=["t"])
    b = store.add("笔记", type="note", tags=["t"])
    r = consolidate(store, snapshots_dir=str(store.db_path.parent / "snaps"))
    assert r["merged_groups"] == 1
    assert store.count() == 1
    base = store.get(r["groups"][0]["base_id"])
    assert base is not None
    # 被吸收 id 列表保留在 relations
    absorbed = r["groups"][0]["absorbed"]
    assert len(absorbed) == 1
    rels = store.get_relations(base["id"])
    assert any(x["rel_type"] == "consolidated_from" for x in rels)


def test_consolidate_does_not_merge_decisions(store):
    store.add("决策 X", type="decision", tags=["d"])
    store.add("决策 Y", type="decision", tags=["d"])
    r = consolidate(store, snapshots_dir=str(store.db_path.parent / "snaps"))
    assert r["merged_groups"] == 0
    assert store.count(type="decision") == 2


# ---------------------------------------------------------------- 快照联动 + status

def test_sweep_creates_snapshot(store, tmp_path):
    store.add("旧笔记", type="note", source_rank=3, created_at=OLD)
    snap_dir = tmp_path / "snaps"
    r = retention_sweep(store, snapshots_dir=str(snap_dir))
    assert r["snapshot"] and r["snapshot"]["ok"]
    assert Path(r["snapshot"]["snapshot_path"]).exists()
    assert list_snapshots(snap_dir)


def test_maintenance_status_output(store):
    store.add("pin", type="note", pinned=True)
    store.add("plain", type="note")
    st = maintenance_status(store.db_path.parent)
    assert st["ok"] and st["entities"] == 2 and st["pinned"] == 1
    assert "snapshots" in st and "last_snapshot" in st


def test_empty_store_no_crash(store):
    # 空库：sweep / consolidate / snapshot 均不崩
    assert retention_sweep(store)["ok"]
    assert consolidate(store)["ok"]
    assert snapshot(store)["ok"]
    assert store.count() == 0
