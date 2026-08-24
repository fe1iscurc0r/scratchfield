# tests/test_lifecycle.py — L-01 可逆遗忘（降权/回滚/合并）+ 时序索引 单元测试
#
# 对齐 K 线 schema.py 契约：id 为 TEXT（sha1 稳定 id），时间戳为 ISO-8601 UTC
# 字符串（同格式字典序 == 时间序）。建表走 schema.connect（不重复建表），
# lifecycle.ensure_lifecycle_schema 只做 L 线职责（审计表/补列/时序索引）。
#
# 8 用例（工单点名）：
#   1. decay 超龄实体 → status 变 decayed
#   2. decay 后行数不变（COUNT 前后相等，只改 status）
#   3. decay 不碰活跃实体（最近活跃/高 weight 的不动）
#   4. restore_entity → status 回 active
#   5. restore 后 log 有 restore 记录
#   6. merge_entities → 低者 superseded、高者保留
#   7. merge 幂等（重复 merge 不炸）
#   8. 索引存在（PRAGMA index_list 含 idx_entity_last_seen / idx_edge_ts）
# 补充 3 用例：
#   9. 无 decay 日志的非 decayed 实体拒绝回滚
#  10. ensure_lifecycle_schema 幂等重入（不炸、不重建表、审计表在）
#  11. K 线旧库（无 superseded_by 列）→ 幂等 ALTER 补列不重建表、数据保留
# 运行：python -m pytest mcpserver/sentinel_intel/tests/test_lifecycle.py -q
"""Tests for sentinel_intel.lifecycle (aligned with K-line schema.py contract)."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # worktree 根（含 mcpserver/）
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.sentinel_intel import lifecycle, schema  # noqa: E402

# 固定基准时间（ISO-8601 UTC，可注入，测试确定性；字典序 == 时间序）
NOW_ISO = "2027-01-15T00:00:00+00:00"
DAY = 86400.0


def _iso_ago(days: float) -> str:
    """now 往前 days 天的 ISO 时间戳（对齐 K 线 ISO 契约）。"""
    base = datetime.fromisoformat(NOW_ISO)
    return (base - timedelta(days=days)).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    """K 线 schema 建三表（intel_entity/intel_edge/intel_alias）+ L 线迁移。"""
    conn = schema.connect(":memory:")
    lifecycle.ensure_lifecycle_schema(conn)
    return conn


def _add_entity(conn, value, canonical_id, weight=0.5, last_seen_offset_days=0.0,
                status="active", etype="infra"):
    entity_id = schema.entity_id(etype, value)
    conn.execute(
        "INSERT INTO intel_entity(id, etype, value, canonical_id, properties_json,"
        " created_at, last_seen_at, weight, status) VALUES (?,?,?,?,?,?,?,?,?)",
        (entity_id, etype, value, canonical_id, "{}", _iso_ago(0),
         _iso_ago(last_seen_offset_days), weight, status),
    )
    conn.commit()
    return entity_id


def _status(conn, entity_id):
    return conn.execute(
        "SELECT status FROM intel_entity WHERE id = ?", (entity_id,)
    ).fetchone()[0]


# ---------------------------------------------------------------- decay
class TestDecay:
    def test_decay_marks_stale_entity(self):
        """用例 1：超龄实体 → status='decayed'，log 记 decay。"""
        conn = _connect()
        stale_id = _add_entity(conn, "10.20.30.40", "c2-host", weight=0.9,
                               last_seen_offset_days=400)
        n = lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.3, now=NOW_ISO)
        assert n == 1
        assert _status(conn, stale_id) == "decayed"
        logs = lifecycle.get_lifecycle_log(conn, stale_id)
        assert len(logs) == 1 and logs[0]["action"] == "decay"
        assert "stale" in logs[0]["reason"]
        conn.close()

    def test_decay_keeps_row_count_no_delete(self):
        """用例 2：decay 后行数不变（只改 status，绝不 DELETE）。"""
        conn = _connect()
        ids = [
            _add_entity(conn, f"host-{i}", f"c-{i}", weight=0.1) for i in range(3)
        ]
        before = conn.execute("SELECT COUNT(*) FROM intel_entity").fetchone()[0]
        lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.3, now=NOW_ISO)
        after = conn.execute("SELECT COUNT(*) FROM intel_entity").fetchone()[0]
        assert before == after == 3
        assert all(_status(conn, i) == "decayed" for i in ids)
        # 行还在且可查回 value（可逆前提：数据未丢）
        values = {r[0] for r in conn.execute("SELECT value FROM intel_entity")}
        assert values == {f"host-{i}" for i in range(3)}
        conn.close()

    def test_decay_spares_active_entities(self):
        """用例 3：最近活跃且高 weight 的实体不动（decay 条件是 OR 语义）。"""
        conn = _connect()
        fresh_id = _add_entity(conn, "bg5gxo-20m", "bg5gxo", weight=0.5,
                               last_seen_offset_days=1)
        heavy_recent_id = _add_entity(conn, "solid-tool", "tool-x", weight=0.9,
                                      last_seen_offset_days=10)  # 双条件都不满足
        low_fresh_id = _add_entity(conn, "fresh-but-noise", "noise", weight=0.1,
                                   last_seen_offset_days=1)  # 最近但低权 → 应降
        stale_heavy_id = _add_entity(conn, "old-but-solid", "tool-y", weight=0.9,
                                     last_seen_offset_days=700)  # 超龄但高权 → OR 语义仍降
        n = lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.3, now=NOW_ISO)
        assert n == 2  # low_fresh（低权）+ stale_heavy（超龄）
        assert _status(conn, fresh_id) == "active"
        assert _status(conn, heavy_recent_id) == "active"
        assert _status(conn, low_fresh_id) == "decayed"
        assert _status(conn, stale_heavy_id) == "decayed"
        conn.close()


# ---------------------------------------------------------------- restore
class TestRestore:
    def test_restore_returns_entity_to_active(self):
        """用例 4：decay 后 restore_entity → status 回 active（可逆遗忘核心）。"""
        conn = _connect()
        entity_id = _add_entity(conn, "1.2.3.4", "c2-ip", weight=0.1)
        lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.3, now=NOW_ISO)
        assert _status(conn, entity_id) == "decayed"
        assert lifecycle.restore_entity(conn, entity_id, now=NOW_ISO) is True
        assert _status(conn, entity_id) == "active"
        conn.close()

    def test_restore_writes_log_record(self):
        """用例 5：restore 后 intel_lifecycle_log 有 action='restore' 记录。"""
        conn = _connect()
        entity_id = _add_entity(conn, "5.6.7.8", "c2-ip-2", weight=0.05)
        lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.3, now=NOW_ISO)
        lifecycle.restore_entity(conn, entity_id, now=NOW_ISO)
        logs = lifecycle.get_lifecycle_log(conn, entity_id)
        actions = [l["action"] for l in logs]
        assert actions == ["decay", "restore"]
        assert "rollback" in logs[-1]["reason"]
        conn.close()

    def test_restore_rejects_without_decay_log(self):
        """补充 9：无 decay 日志的非 decayed 实体拒绝回滚（审计一致性）。"""
        conn = _connect()
        entity_id = _add_entity(conn, "9.9.9.9", "clean", weight=0.9)
        assert lifecycle.restore_entity(conn, entity_id, now=NOW_ISO) is False
        assert _status(conn, entity_id) == "active"
        conn.close()


# ---------------------------------------------------------------- merge
class TestMerge:
    def test_merge_supersedes_low_weight_side(self):
        """用例 6：低 weight 组全部标 superseded + superseded_by 指向高者，高者保留。"""
        conn = _connect()
        high_id = _add_entity(conn, "BG5GXO 主台", "radio:bg5gxo", weight=0.9)
        low_id = _add_entity(conn, "bg5gxo 旧记录", "radio:bg5gxo-dup", weight=0.2)
        result = lifecycle.merge_entities(conn, "radio:bg5gxo", "radio:bg5gxo-dup", now=NOW_ISO)
        assert result["ok"] is True and result["skipped"] is False
        assert result["kept"] == "radio:bg5gxo"
        assert _status(conn, high_id) == "active"          # 高者保留
        assert _status(conn, low_id) == "superseded"       # 低者标 superseded（不删）
        superseded_by = conn.execute(
            "SELECT superseded_by FROM intel_entity WHERE id = ?", (low_id,)
        ).fetchone()[0]
        assert superseded_by == high_id
        logs = lifecycle.get_lifecycle_log(conn, low_id)
        assert logs and logs[-1]["action"] == "merge"
        # 行数不变（merge 是标 superseded 不是删）
        assert conn.execute("SELECT COUNT(*) FROM intel_entity").fetchone()[0] == 2
        conn.close()

    def test_merge_idempotent_rerun_safe(self):
        """用例 7：重复 merge 不炸（幂等重入，状态无二次变更）。"""
        conn = _connect()
        _add_entity(conn, "canonical-a 记录", "can-a", weight=0.8)
        _add_entity(conn, "canonical-b 记录", "can-b", weight=0.3)
        first = lifecycle.merge_entities(conn, "can-a", "can-b", now=NOW_ISO)
        assert first["ok"] is True and first["skipped"] is False
        second = lifecycle.merge_entities(conn, "can-a", "can-b", now=NOW_ISO)  # 重入
        assert second["ok"] is True and second["skipped"] is True  # 不炸，标记跳过
        # merge 日志只有一份（重入不重复写）
        merge_logs = conn.execute(
            "SELECT COUNT(*) FROM intel_lifecycle_log WHERE action = 'merge'"
        ).fetchone()[0]
        assert merge_logs == 1
        conn.close()


# ---------------------------------------------------------------- 索引/迁移
class TestSchemaAndIndexes:
    def test_temporal_indexes_exist(self):
        """用例 8：PRAGMA index_list 含 idx_entity_last_seen / idx_edge_ts。"""
        conn = _connect()
        entity_indexes = {
            r[1] for r in conn.execute("PRAGMA index_list(intel_entity)").fetchall()
        }
        edge_indexes = {
            r[1] for r in conn.execute("PRAGMA index_list(intel_edge)").fetchall()
        }
        assert "idx_entity_last_seen" in entity_indexes
        assert "idx_edge_ts" in edge_indexes
        conn.close()

    def test_ensure_schema_idempotent_rerun(self):
        """补充 10：迁移幂等——重复 ensure 不炸、不重建表、审计表在。"""
        conn = _connect()
        # 三表由 K 线 schema 建，本线 ensure 不得重建/覆盖
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"intel_entity", "intel_edge", "intel_alias"} <= tables
        conn.execute(
            "INSERT INTO intel_entity(id, etype, value, canonical_id, properties_json,"
            " created_at, last_seen_at, weight, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (schema.entity_id("infra", "keep-me"), "infra", "keep-me", "c-keep",
             "{}", _iso_ago(0), _iso_ago(0), 0.5, "active"))
        conn.commit()
        lifecycle.ensure_lifecycle_schema(conn)  # 二次执行 no-op
        lifecycle.ensure_lifecycle_schema(conn)  # 三次仍 no-op
        cols = {r[1] for r in conn.execute("PRAGMA table_info(intel_entity)").fetchall()}
        assert "superseded_by" in cols
        assert conn.execute("SELECT COUNT(*) FROM intel_entity").fetchone()[0] == 1
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='intel_lifecycle_log'").fetchone() is not None
        conn.close()

    def test_kline_schema_without_superseded_by_migrated(self):
        """补充 11：K 线库（schema.connect 建表，本无 superseded_by）→ ensure 补列不重建。"""
        conn = schema.connect(":memory:")  # K 线 SCHEMA_SQL 建表，无 superseded_by
        entity_id = schema.entity_id("infra", "legacy-host")
        conn.execute(
            "INSERT INTO intel_entity(id, etype, value, canonical_id, properties_json,"
            " created_at, last_seen_at, weight, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (entity_id, "infra", "legacy-host", "can-old", "{}",
             _iso_ago(0), _iso_ago(0), 0.4, "active"))
        conn.commit()
        assert "superseded_by" not in {
            r[1] for r in conn.execute("PRAGMA table_info(intel_entity)").fetchall()
        }
        lifecycle.ensure_lifecycle_schema(conn)  # 幂等迁移
        cols = {r[1] for r in conn.execute("PRAGMA table_info(intel_entity)").fetchall()}
        assert "superseded_by" in cols
        # 旧数据仍在（未重建表）
        assert conn.execute("SELECT COUNT(*) FROM intel_entity").fetchone()[0] == 1
        # 迁移后全功能可用（低权触发 decay，TEXT id + ISO 时间戳）
        n = lifecycle.decay_entities(conn, max_age_days=365, min_weight=0.99, now=NOW_ISO)
        assert n == 1
        assert _status(conn, entity_id) == "decayed"
        conn.close()
