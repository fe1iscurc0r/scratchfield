# -*- coding: utf-8 -*-
"""Unit tests for main_logic.memory_snapshot — 记忆层快照/回滚旁路（N-02）。

覆盖（≥6）：
  1. 快照创建：snapshot() 落盘 JSON 快照 + 内容/元数据正确
  2. 列表：list_snapshots() 返回快照元数据
  3. 恢复点标记：label 写入 restore_point/label
  4. 回滚前备份：restore() 回写前强制备份当前态
  5. 坏快照报错：sha256 不一致 / JSON 损坏 → SnapshotError，且目标不被改动
  6. 目录隔离：快照落 snapshot_dir 不污染源目录；拒绝路径穿越
  7. 二进制往返：SQLite .db 按 base64 无损还原
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from main_logic.memory_snapshot import (
    SnapshotError,
    list_snapshots,
    restore,
    snapshot,
)
from main_logic.memory_snapshot.snap import _SNAPSHOT_PREFIX


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot_file(snapshot_dir: Path) -> Path:
    return next(snapshot_dir.glob(f"{_SNAPSHOT_PREFIX}*.json"))


# ---------------------------------------------------------------------------
# 1. 快照创建
# ---------------------------------------------------------------------------
def test_snapshot_creates_json(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", '{"a": 1}')
    _write(src / "persona.json", '{"name": "nico"}')
    snaps = tmp_path / "snaps"

    meta = snapshot(src, snaps, label="baseline", note="first")

    out = _snapshot_file(snaps)
    assert out.is_file()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == "memory_snapshot/1"
    assert doc["file_count"] == 2
    assert set(doc["files"]) == {"facts.json", "persona.json"}
    assert doc["files"]["facts.json"]["content"] == '{"a": 1}'
    assert doc["files"]["facts.json"]["encoding"] == "utf-8"
    assert doc["files"]["facts.json"]["sha256"]
    assert meta["id"] == doc["id"]
    assert meta["file_count"] == 2


# ---------------------------------------------------------------------------
# 2. 列表
# ---------------------------------------------------------------------------
def test_list_snapshots(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", "{}")
    snaps = tmp_path / "snaps"
    snapshot(src, snaps)
    snapshot(src, snaps, label="v2")

    metas = list_snapshots(snaps)
    assert len(metas) == 2
    # 按创建时间倒序
    assert metas[0]["created_at"] >= metas[1]["created_at"]
    assert {m["id"] for m in metas} == {
        s.name[len(_SNAPSHOT_PREFIX):-len(".json")] for s in snaps.glob(f"{_SNAPSHOT_PREFIX}*.json")
    }


def test_list_empty_dir(tmp_path: Path):
    assert list_snapshots(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# 3. 恢复点标记
# ---------------------------------------------------------------------------
def test_restore_point_marker(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", "{}")
    snaps = tmp_path / "snaps"

    meta = snapshot(src, snaps, label="golden")
    assert meta["restore_point"] is True
    assert meta["label"] == "golden"

    metas = list_snapshots(snaps)
    assert metas[0]["restore_point"] is True
    assert metas[0]["label"] == "golden"


# ---------------------------------------------------------------------------
# 4. 回滚前备份
# ---------------------------------------------------------------------------
def test_restore_backs_up_before_write(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", '{"version": 1}')
    snaps = tmp_path / "snaps"
    snapshot(src, snaps, label="v1")

    # 改动现状，模拟记忆漂移
    _write(src / "facts.json", '{"version": 2}')
    _write(src / "extra.json", "drift")

    result = restore(next(iter(list_snapshots(snaps)))["id"], snaps, src)

    backup_dir = Path(result["backup_dir"])
    assert backup_dir.is_dir()
    # 备份里应保留回滚前的当前态（version 2 + extra.json）
    assert (backup_dir / "facts.json").read_text(encoding="utf-8") == '{"version": 2}'
    assert (backup_dir / "extra.json").read_text(encoding="utf-8") == "drift"
    # 目标已还原到快照态
    assert (src / "facts.json").read_text(encoding="utf-8") == '{"version": 1}'
    assert result["restored_files"] == 1


# ---------------------------------------------------------------------------
# 5. 坏快照报错
# ---------------------------------------------------------------------------
def test_restore_sha256_mismatch_raises(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", '{"version": 1}')
    snaps = tmp_path / "snaps"
    snapshot(src, snaps, label="v1")

    out = _snapshot_file(snaps)
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["files"]["facts.json"]["content"] = '{"tampered": true}'
    out.write_text(json.dumps(doc), encoding="utf-8")

    # 目标先写个新值，确认坏快照不会碰它
    _write(src / "facts.json", '{"version": 99}')

    with pytest.raises(SnapshotError, match="sha256"):
        restore(next(iter(list_snapshots(snaps)))["id"], snaps, src)
    # 校验失败不应回写
    assert (src / "facts.json").read_text(encoding="utf-8") == '{"version": 99}'


def test_restore_bad_json_raises(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", "{}")
    snaps = tmp_path / "snaps"
    meta = snapshot(src, snaps)
    _snapshot_file(snaps).write_text("{ not json", encoding="utf-8")

    with pytest.raises(SnapshotError, match="JSON"):
        restore(meta["id"], snaps, src)


def test_restore_path_traversal_rejected(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", "{}")
    snaps = tmp_path / "snaps"
    snapshot(src, snaps)

    out = _snapshot_file(snaps)
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["files"]["../../escape.txt"] = {
        "sha256": "0" * 64,
        "size": 0,
        "encoding": "utf-8",
        "content": "pwned",
    }
    out.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(SnapshotError, match="穿越"):
        restore(next(iter(list_snapshots(snaps)))["id"], snaps, src)


# ---------------------------------------------------------------------------
# 6. 目录隔离
# ---------------------------------------------------------------------------
def test_snapshot_does_not_pollute_source(tmp_path: Path):
    src = tmp_path / "memory"
    _write(src / "facts.json", "{}")
    snaps = tmp_path / "snaps"

    snapshot(src, snaps)

    # 源目录只含原始文件，不含快照文件
    assert sorted(p.name for p in src.iterdir()) == ["facts.json"]
    assert list(src.glob(f"{_SNAPSHOT_PREFIX}*.json")) == []
    # 快照确实落在 snaps 目录
    assert list(snaps.glob(f"{_SNAPSHOT_PREFIX}*.json"))


# ---------------------------------------------------------------------------
# 7. 二进制往返（SQLite）
# ---------------------------------------------------------------------------
def test_binary_sqlite_roundtrip(tmp_path: Path):
    src = tmp_path / "memory"
    src.mkdir()
    db = src / "time_indexed.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (k TEXT, v INTEGER)")
    conn.execute("INSERT INTO t VALUES ('x', 1)")
    conn.commit()
    conn.close()
    _write(src / "facts.json", '{"x": 1}')
    snaps = tmp_path / "snaps"

    snapshot(src, snaps, label="with-db")

    # 破坏现状
    db.unlink()
    _write(src / "facts.json", '{"x": 2}')

    restore(next(iter(list_snapshots(snaps)))["id"], snaps, src)

    assert db.is_file()
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT v FROM t WHERE k='x'").fetchone() == (1,)
    conn.close()
    assert (src / "facts.json").read_text(encoding="utf-8") == '{"x": 1}'
