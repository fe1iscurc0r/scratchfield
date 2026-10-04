"""B-06 · 数据缓存与离线支持（卷132）。

**为什么用标准库 `sqlite3` 而不是工单写的 `pysqlite3-binary`**：
`pysqlite3-binary` 的 wheel 只有 `manylinux2014_x86_64`（实测 0 个 Windows 轮子），
本机是 Windows，装了也起不来。stdlib `sqlite3` 零依赖、跨平台、随 Python 走。
异步侧由 API 层用 `asyncio.to_thread` 包裹，不引入额外依赖。见偏离说明第 10 条。

**无损存储**：除了解包成列（供 SQL 过滤），每行还存一份完整 `payload` JSON。
列只用于索引与过滤，**读取一律以 payload 还原** —— 这样以后加字段不会因为
"忘了 ALTER TABLE" 而静默丢数据。

**跨线程**：`check_same_thread=False` + 一把 `threading.Lock` 串行化写。
SQLite 是单写者模型，靠锁而不是靠重试。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .models import AlertRule, Event

__all__ = ["CacheStore", "AlertStore", "DEFAULT_DB_NAME", "to_unix"]

DEFAULT_DB_NAME = "events.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    source          TEXT,
    event_type      TEXT,
    lng             REAL,
    lat             REAL,
    severity        TEXT,
    confidence      REAL,
    title           TEXT,
    description     TEXT,
    reported_at     TEXT,
    expires_at      TEXT,
    ts              REAL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_bbox  ON events(lng, lat);
CREATE INDEX IF NOT EXISTS idx_events_src   ON events(source, event_type);

CREATE TABLE IF NOT EXISTS sync_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL,
    action      TEXT NOT NULL DEFAULT 'upsert',
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_created ON sync_queue(created_at);

CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def to_unix(value: Any) -> float | None:
    """datetime / ISO 串 / 数值 → Unix 秒；无法解析返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


class CacheStore:
    """SQLite 事件缓存 + 待同步队列。线程安全（单写者锁）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path(DEFAULT_DB_NAME)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- 生命周期 ----

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:                               # noqa: BLE001
                pass

    def __enter__(self) -> "CacheStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- 写 ----

    def save_events(self, events: Iterable[Event | dict[str, Any]]) -> dict[str, Any]:
        """批量 upsert。返回 `{ok, saved, failed, errors}`；单条坏数据不中断整批。"""
        rows: list[tuple[Any, ...]] = []
        failed = 0
        errors: list[str] = []
        for item in events:
            try:
                ev = item if isinstance(item, Event) else Event.from_feature(item)
                payload = ev.model_dump_json()
                rows.append((
                    ev.id, ev.source.value, ev.event_type.value, ev.lng, ev.lat,
                    ev.severity.value, ev.confidence, ev.title, ev.description,
                    ev.reported_at.isoformat(),
                    ev.expires_at.isoformat() if ev.expires_at else None,
                    to_unix(ev.reported_at), payload,
                ))
            except Exception as exc:                        # noqa: BLE001
                failed += 1
                errors.append(f"{type(exc).__name__}: {exc}")
        if not rows:
            return {"ok": True, "saved": 0, "failed": failed, "errors": errors[:20]}
        with self._lock:
            self._conn.executemany(
                "INSERT INTO events (id, source, event_type, lng, lat, severity,"
                " confidence, title, description, reported_at, expires_at, ts, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " source=excluded.source, event_type=excluded.event_type,"
                " lng=excluded.lng, lat=excluded.lat, severity=excluded.severity,"
                " confidence=excluded.confidence, title=excluded.title,"
                " description=excluded.description, reported_at=excluded.reported_at,"
                " expires_at=excluded.expires_at, ts=excluded.ts, payload=excluded.payload",
                rows)
            self._conn.commit()
        return {"ok": True, "saved": len(rows), "failed": failed, "errors": errors[:20]}

    # ---- 读 ----

    def load_events(self, bbox: tuple[float, float, float, float] | None = None,
                    time_range: Any = None,
                    limit: int = 5000,
                    include_expired: bool = True,
                    source: str | None = None) -> list[Event]:
        """离线可读的事件查询。

        `bbox` = (west, south, east, north)；`time_range` = (起, 止)，
        元素可为 datetime / ISO 串 / 数值，任一端 None 表示不限。
        """
        where: list[str] = []
        args: list[Any] = []
        if bbox is not None:
            w, s, e, n = (float(x) for x in bbox)
            lo, hi = min(w, e), max(w, e)
            so, no = min(s, n), max(s, n)
            where.append("lng BETWEEN ? AND ? AND lat BETWEEN ? AND ?")
            args += [lo, hi, so, no]
        if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
            start, end = to_unix(time_range[0]), to_unix(time_range[1])
            if start is not None:
                where.append("ts >= ?")
                args.append(start)
            if end is not None:
                where.append("ts <= ?")
                args.append(end)
        if source:
            where.append("source = ?")
            args.append(str(source))
        if not include_expired:
            where.append("(expires_at IS NULL OR expires_at > ?)")
            args.append(datetime.now(timezone.utc).isoformat())

        sql = "SELECT payload FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(max(1, int(limit)))

        with self._lock:
            cur = self._conn.execute(sql, args)
            rows = cur.fetchall()

        out: list[Event] = []
        for r in rows:
            try:
                out.append(Event.model_validate_json(r["payload"]))
            except Exception:                               # noqa: BLE001
                continue                                    # 脏行跳过，不拖垮整次查询
        return out

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    # ---- 同步队列 ----

    def sync_queue_add(self, event: Event | dict[str, Any], action: str = "upsert") -> dict[str, Any]:
        """入待同步队列（断网期间本地产生的事件）。"""
        try:
            ev = event if isinstance(event, Event) else Event.from_feature(event)
            payload = ev.model_dump_json()
        except Exception as exc:                            # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        with self._lock:
            self._conn.execute(
                "INSERT INTO sync_queue (event_id, action, payload, created_at)"
                " VALUES (?,?,?,?)",
                (ev.id, str(action), payload, time.time()))
            self._conn.commit()
        return {"ok": True, "event_id": ev.id, "action": action}

    def sync_queue_size(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0])

    def sync_queue_peek(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, event_id, action, payload, created_at, attempts"
                " FROM sync_queue ORDER BY created_at ASC LIMIT ?",
                (max(1, int(limit)),)).fetchall()
        return [dict(r) for r in rows]

    def sync_queue_flush(self, pusher: Callable[[list[dict[str, Any]]], Any] | None = None,
                         limit: int = 200) -> dict[str, Any]:
        """网络恢复后推送队列。

        `pusher` 接收记录列表，返回 `{"ok": True, "accepted": [id...]}` 或
        `{"ok": False, "error": ...}`。**未成功的条目不删**，只累加 attempts ——
        队列只能因"确实送达"而缩短，不能因"试过"而缩短。
        """
        items = self.sync_queue_peek(limit=limit)
        if not items:
            return {"ok": True, "pushed": 0, "remaining": 0, "failed": 0}

        if pusher is None:
            return {"ok": False, "error": "no_pusher_configured",
                    "pushed": 0, "remaining": len(items), "failed": 0}

        try:
            result = pusher(items) or {}
        except Exception as exc:                            # noqa: BLE001
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        accepted = set(result.get("accepted") or [])
        if result.get("ok") and not accepted:
            accepted = {it["event_id"] for it in items}      # 整体成功视为全部收下

        pushed = 0
        if accepted:
            with self._lock:
                for it in items:
                    if it["event_id"] in accepted:
                        self._conn.execute("DELETE FROM sync_queue WHERE id = ?", (it["id"],))
                        pushed += 1
                    else:
                        self._conn.execute(
                            "UPDATE sync_queue SET attempts = attempts + 1, last_error = ?"
                            " WHERE id = ?",
                            (str(result.get("error") or "not_accepted"), it["id"]))
                self._conn.commit()
        else:
            with self._lock:
                for it in items:
                    self._conn.execute(
                        "UPDATE sync_queue SET attempts = attempts + 1, last_error = ?"
                        " WHERE id = ?", (str(result.get("error") or "failed"), it["id"]))
                self._conn.commit()

        return {
            "ok": bool(result.get("ok")) or pushed > 0,
            "pushed": pushed,
            "remaining": self.sync_queue_size(),
            "failed": len(items) - pushed,
            "error": result.get("error"),
        }

    # ---- 状态 ----

    def db_size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "db_path": str(self.path),
            "db_size_bytes": self.db_size_bytes(),
            "events_count": self.count(),
            "pending_sync": self.sync_queue_size(),
        }

    # ---- meta ----

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (k, v) VALUES (?,?)"
                " ON CONFLICT(k) DO UPDATE SET v = excluded.v", (str(key), str(value)))
            self._conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT v FROM meta WHERE k = ?", (str(key),)).fetchone()
        return row["v"] if row else default


class AlertStore:
    """告警规则持久化（F-04 需要 `/api/alerts` CRUD；后端工单 B-07 漏列）。"""

    def __init__(self, store: CacheStore) -> None:
        self.store = store

    def add(self, rule: AlertRule) -> dict[str, Any]:
        with self.store._lock:                              # noqa: SLF001  同一把锁，单写者
            self.store._conn.execute(                        # noqa: SLF001
                "INSERT INTO alerts (id, payload, created_at) VALUES (?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (rule.id, rule.model_dump_json(), time.time()))
            self.store._conn.commit()                        # noqa: SLF001
        return {"ok": True, "id": rule.id}

    def list(self) -> list[AlertRule]:
        with self.store._lock:                               # noqa: SLF001
            rows = self.store._conn.execute(                 # noqa: SLF001
                "SELECT payload FROM alerts ORDER BY created_at ASC").fetchall()
        out: list[AlertRule] = []
        for r in rows:
            try:
                out.append(AlertRule.model_validate_json(r["payload"]))
            except Exception:                                # noqa: BLE001
                continue
        return out

    def get(self, rule_id: str) -> AlertRule | None:
        for rule in self.list():
            if rule.id == rule_id:
                return rule
        return None

    def delete(self, rule_id: str) -> bool:
        with self.store._lock:                               # noqa: SLF001
            cur = self.store._conn.execute("DELETE FROM alerts WHERE id = ?", (rule_id,))
            self.store._conn.commit()                        # noqa: SLF001
            return cur.rowcount > 0

    def evaluate(self, events: Sequence[Event]) -> list[dict[str, Any]]:
        """用全部规则过一遍事件，返回命中列表（供告警触发与 SSE 推送）。"""
        triggers: list[dict[str, Any]] = []
        for rule in self.list():
            for ev in events:
                if rule.matches(ev):
                    triggers.append({"rule_id": rule.id, "rule_name": rule.name,
                                     "event": ev.to_feature()})
        return triggers
