"""sentinel_intel lifecycle — 情报可逆遗忘（降权/回滚/合并）+ 时序索引（L-01）。

设计来源（上游只读参考，实现独立）：
  - ThreatRecall/zettelforge memory_evolver.py（MIT）：apply_evolution 先存
    previous_raw 再改、rollback 恢复并记 evolution_rolled_back——"可逆"模式
    映射为本模块 active↔decayed 状态机 + intel_lifecycle_log 审计轨迹。
  - Reversible Forgetting 论文要点（授粉报告 3.3）：降权 + 时间戳 + 回滚日志，
    误删情报不可恢复 → 只降权（status='decayed'）不 DELETE，restore 可回滚。
  - caura supersedes_id 模式：merge 时低 weight 实体标 superseded +
    superseded_by 指向保留者（不删行）。

与 K 线（schema.py）的契约：
  - 建表职责在 K 线 schema.py（intel_entity/intel_edge/intel_alias）；本模块
    **不重复建表**，只负责 L 线职责：
      1. intel_lifecycle_log 审计表（K 线 schema 不含，本线建）
      2. superseded_by 列：PRAGMA table_info 探测缺失才 ALTER 补列（不重建表）
      3. 时序索引 idx_entity_last_seen / idx_edge_ts（K 已建则幂等 no-op）
  - 时间戳契约对齐 K 线：ISO-8601 UTC 字符串（TEXT），同格式字典序 == 时间序。

License: Apache-2.0。纯 Python + SQLite，零新增依赖；不依赖 LLM（LLM 语义合并
留 TODO，本期规则版降级）。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 状态枚举（对齐 K 线 schema 的 status 字段：active/decayed/revoked + merge 的 superseded）
STATUS_ACTIVE = "active"
STATUS_DECAYED = "decayed"
STATUS_REVOKED = "revoked"
STATUS_SUPERSEDED = "superseded"

# 审计动作枚举（SPEC-09：decay/restore/revoke；merge 为本单扩展）
ACTION_DECAY = "decay"
ACTION_RESTORE = "restore"
ACTION_REVOKE = "revoke"
ACTION_MERGE = "merge"

# 审计日志表：entity_id 对齐 K 线实体 id（TEXT，sha1 稳定 id）
_LOG_DDL = """
CREATE TABLE IF NOT EXISTS intel_lifecycle_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    action    TEXT NOT NULL,
    at        TEXT NOT NULL,
    reason    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_entity ON intel_lifecycle_log(entity_id);
"""
# 时序索引：旧情报扫描（decay 按超龄遍历）与边时间线查询。
# K 线 schema.py 已建同名索引，此处幂等 no-op；对旧库/独立库是兜底。
_TS_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_entity_last_seen ON intel_entity(last_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_edge_ts ON intel_edge(ts)",
)


def _now_iso(now: float | str | None = None) -> str:
    """统一时间戳：ISO-8601 UTC（与 K 线 graph._now_iso 同格式，可字典序比较）。

    兼容注入：float/int（epoch 秒）自动转 ISO；str 原样使用（测试传固定基准）。
    """
    if now is None:
        return datetime.now(UTC).isoformat(timespec="seconds")
    if isinstance(now, str):
        return now
    return datetime.fromtimestamp(now, tz=UTC).isoformat(timespec="seconds")


def _log_action(conn: sqlite3.Connection, entity_id: str, action: str,
                at: str, reason: str) -> None:
    """写审计日志（所有生命周期变更必经，保证可追溯/可回滚）。"""
    conn.execute(
        "INSERT INTO intel_lifecycle_log(entity_id, action, at, reason) VALUES (?,?,?,?)",
        (entity_id, action, at, reason),
    )


def ensure_lifecycle_schema(conn: sqlite3.Connection) -> None:
    """幂等迁移（L 线职责，重复调用安全）：

    1. intel_lifecycle_log 审计表（K 线 schema 不含，本线补建）；
    2. superseded_by 列：PRAGMA table_info 探测缺失才 ALTER 补列（不重建表）；
    3. 时序索引 idx_entity_last_seen / idx_edge_ts（幂等）。
    不创建 intel_entity/intel_edge 表——建表职责在 K 线 schema.py（不重复建表）；
    intel_entity 未建（K 线未落）时只建审计表并告警跳过补列/索引。
    """
    conn.executescript(_LOG_DDL)
    has_entity = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='intel_entity'"
    ).fetchone() is not None
    if not has_entity:
        logger.warning(
            "[lifecycle] intel_entity 表不存在（K 线 schema 未建）——"
            "仅建审计表，跳过补列/时序索引")
        conn.commit()
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(intel_entity)").fetchall()}
    if "superseded_by" not in cols:
        conn.execute("ALTER TABLE intel_entity ADD COLUMN superseded_by TEXT")
        logger.info("[lifecycle] intel_entity 幂等补列 superseded_by")
    for ddl in _TS_INDEX_DDL:
        conn.execute(ddl)
    conn.commit()


def decay_entities(
    conn: sqlite3.Connection,
    max_age_days: float = 365.0,
    min_weight: float = 0.3,
    now: float | str | None = None,
) -> int:
    """旧情报自动降权（可逆遗忘——只 UPDATE status，绝不 DELETE）。

    条件（status='active' 的实体，二选一即触发）：
      - 超龄：last_seen_at < now - max_age_days * 86400（ISO 字典序比较）
      - 低权：weight < min_weight
    动作：status='decayed' + intel_lifecycle_log(action='decay', reason=触发原因)。
    幂等：非 active（decayed/revoked/superseded）不重复处理。
    返回本次降权条数。
    """
    ts = _now_iso(now)
    ts_dt = datetime.fromisoformat(ts)
    threshold_iso = (ts_dt - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, last_seen_at, weight FROM intel_entity"
        " WHERE status = ? AND (last_seen_at < ? OR weight < ?)",
        (STATUS_ACTIVE, threshold_iso, min_weight),
    ).fetchall()
    changed = 0
    for entity_id, last_seen_at, weight in rows:
        if last_seen_at < threshold_iso:
            try:
                age_days = (ts_dt - datetime.fromisoformat(last_seen_at)).total_seconds() / 86400.0
            except ValueError:
                age_days = float("nan")
            reason = f"stale: last_seen {age_days:.1f}d > max_age {max_age_days}d"
        else:
            reason = f"low_weight: {weight} < min_weight {min_weight}"
        conn.execute(
            "UPDATE intel_entity SET status = ? WHERE id = ?",
            (STATUS_DECAYED, entity_id),
        )
        _log_action(conn, entity_id, ACTION_DECAY, ts, reason)
        changed += 1
    conn.commit()
    if changed:
        logger.info("[lifecycle] decay_entities: %d 条降权 (max_age=%sd min_weight=%s)",
                    changed, max_age_days, min_weight)
    return changed


def restore_entity(conn: sqlite3.Connection, entity_id: str,
                   now: float | str | None = None) -> bool:
    """回滚降权（可逆遗忘核心）：decayed → active。

    前提：该实体在 intel_lifecycle_log 有 decay 记录（可追溯才可逆）且
    当前 status='decayed'（revoked/superseded 不属于 decay 回滚范围）。
    成功记 log(action='restore')。返回是否恢复。
    """
    cur_status = conn.execute(
        "SELECT status FROM intel_entity WHERE id = ?", (entity_id,)
    ).fetchone()
    if cur_status is None:
        logger.warning("[lifecycle] restore_entity: 实体 %s 不存在", entity_id)
        return False
    if cur_status[0] != STATUS_DECAYED:
        logger.info("[lifecycle] restore_entity: 实体 %s 状态 %s 非 decayed，跳过",
                    entity_id, cur_status[0])
        return False
    # 从日志找最近一次 decay 记录（restore 的依据：有 decay 才谈得上回滚）
    last_decay = conn.execute(
        "SELECT at, reason FROM intel_lifecycle_log"
        " WHERE entity_id = ? AND action = ? ORDER BY at DESC, id DESC LIMIT 1",
        (entity_id, ACTION_DECAY),
    ).fetchone()
    if last_decay is None:
        logger.warning("[lifecycle] restore_entity: 实体 %s 无 decay 日志，拒绝回滚", entity_id)
        return False
    ts = _now_iso(now)
    conn.execute(
        "UPDATE intel_entity SET status = ? WHERE id = ?",
        (STATUS_ACTIVE, entity_id),
    )
    _log_action(conn, entity_id, ACTION_RESTORE, ts,
                f"rollback of decay @ {last_decay[0]} ({last_decay[1]})")
    conn.commit()
    return True


def merge_entities(
    conn: sqlite3.Connection,
    canonical_a: str,
    canonical_b: str,
    now: float | str | None = None,
) -> dict[str, Any]:
    """重复情报合并（不打架）：同两个 canonical_id 的实体组，weight 高者保留为主，
    低组全部实体标 status='superseded' + superseded_by=高组代表 id（不删行）。

    对照 caura supersedes_id：被覆盖方记录"被谁取代"，可追溯、可人工回滚。
    幂等：低组已全部 superseded 时重复 merge 不变更、不再写 log，直接返回现状。
    返回 {"ok": bool, "kept": canonical, "kept_representative": id|None,
          "superseded_entities": [id...], "skipped": bool}
    """
    ts = _now_iso(now)

    def _group_state(canonical: str) -> tuple[tuple[str, float] | None, bool]:
        """该 canonical 组状态：(组代表, 组是否已全部 superseded)。

        组代表 = 最高 weight 的非 superseded 实体；代表 None 且组内有
        superseded 行 → 幂等重入（此前已合并过），无任何行 → 组不存在。
        """
        any_rows = conn.execute(
            "SELECT 1 FROM intel_entity WHERE canonical_id = ? LIMIT 1",
            (canonical,),
        ).fetchone()
        if any_rows is None:
            return None, False  # 组不存在
        rep = conn.execute(
            "SELECT id, weight FROM intel_entity WHERE canonical_id = ?"
            " AND status != ? ORDER BY weight DESC, id LIMIT 1",
            (canonical, STATUS_SUPERSEDED),
        ).fetchone()
        if rep is not None:
            return rep, False
        # 无非 superseded 行但组内有行 → 已全部 superseded（幂等重入）
        return None, True

    rep_a, a_done = _group_state(canonical_a)
    rep_b, b_done = _group_state(canonical_b)
    # 任一组此前已合并（全部 superseded）→ 幂等重入，不炸不重复写 log
    if rep_a is None and a_done:
        return {"ok": True, "kept": canonical_b, "kept_representative": rep_b[0] if rep_b else None,
                "superseded_entities": [], "skipped": True,
                "reason": f"canonical {canonical_a!r} 已全部 superseded（幂等重入）"}
    if rep_b is None and b_done:
        return {"ok": True, "kept": canonical_a, "kept_representative": rep_a[0] if rep_a else None,
                "superseded_entities": [], "skipped": True,
                "reason": f"canonical {canonical_b!r} 已全部 superseded（幂等重入）"}
    if rep_a is None or rep_b is None:
        missing = canonical_a if rep_a is None else canonical_b
        logger.info("[lifecycle] merge_entities: canonical %r 无可合并实体，跳过", missing)
        return {"ok": False, "kept": None, "kept_representative": None,
                "superseded_entities": [], "skipped": True,
                "reason": f"canonical {missing!r} 无实体"}

    # weight 高者保留；并列时 canonical 字典序稳定取胜（结果确定性）
    if (rep_b[1], canonical_b) > (rep_a[1], canonical_a):
        kept_canonical, kept_id = canonical_b, rep_b[0]
        loser_canonical = canonical_a
    else:
        kept_canonical, kept_id = canonical_a, rep_a[0]
        loser_canonical = canonical_b

    # 低组待合并实体 = 非 superseded 的全部行（已 superseded 的跳过 → 幂等）
    losers = conn.execute(
        "SELECT id FROM intel_entity WHERE canonical_id = ? AND status != ?",
        (loser_canonical, STATUS_SUPERSEDED),
    ).fetchall()
    if not losers:
        return {"ok": True, "kept": kept_canonical, "kept_representative": kept_id,
                "superseded_entities": [], "skipped": True,
                "reason": "低组已全部 superseded（幂等重入）"}

    superseded_ids = []
    for (entity_id,) in losers:
        conn.execute(
            "UPDATE intel_entity SET status = ?, superseded_by = ? WHERE id = ?",
            (STATUS_SUPERSEDED, kept_id, entity_id),
        )
        _log_action(conn, entity_id, ACTION_MERGE, ts,
                    f"superseded by canonical {kept_canonical!r} (entity {kept_id},"
                    f" weight {max(rep_a[1], rep_b[1])})")
        superseded_ids.append(entity_id)
    conn.commit()
    logger.info("[lifecycle] merge_entities: %r 胜出，%r 组 %d 条实体标 superseded",
                kept_canonical, loser_canonical, len(superseded_ids))
    # TODO(L+): LLM 辅助语义合并（判断两 canonical 是否真重复）——本期规则版，
    #           调用方以 canonical 归并结果（K 线 alias_resolver）为准传入。
    return {"ok": True, "kept": kept_canonical, "kept_representative": kept_id,
            "superseded_entities": superseded_ids, "skipped": False}


def get_lifecycle_log(conn: sqlite3.Connection, entity_id: str) -> list[dict[str, Any]]:
    """查实体的生命周期审计轨迹（时间升序）。"""
    rows = conn.execute(
        "SELECT entity_id, action, at, reason FROM intel_lifecycle_log"
        " WHERE entity_id = ? ORDER BY at, id",
        (entity_id,),
    ).fetchall()
    return [{"entity_id": r[0], "action": r[1], "at": r[2], "reason": r[3]} for r in rows]


__all__ = [
    "STATUS_ACTIVE", "STATUS_DECAYED", "STATUS_REVOKED", "STATUS_SUPERSEDED",
    "ACTION_DECAY", "ACTION_RESTORE", "ACTION_REVOKE", "ACTION_MERGE",
    "ensure_lifecycle_schema", "decay_entities", "restore_entity",
    "merge_entities", "get_lifecycle_log",
]
