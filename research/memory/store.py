"""SQLite 四表会话存储 + 前缀增量同步（授粉-C2）。

改编自 ChemGraph memory/store.py（Apache-2.0）。核心语义保留：
``synchronize_messages`` 以「库里已存 message_id 序列是否为传入序列前缀」
做增量判断——是前缀就只补尾部（幂等），否则整体重建。
四表按工单要求：sessions / messages / tasks / events。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    model_name    TEXT NOT NULL DEFAULT '',
    workflow_type TEXT NOT NULL DEFAULT '',
    query_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    tool_name  TEXT,
    timestamp  TEXT NOT NULL,
    ordinal    INTEGER,
    message_id TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_type  TEXT NOT NULL DEFAULT 'python',
    spec_json  TEXT,
    status     TEXT NOT NULL DEFAULT 'pending',
    result     TEXT,
    error_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload    TEXT,
    timestamp  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
"""


@dataclass
class SessionMessage:
    """单条会话消息（对齐 ChemGraph SessionMessage 的可读字段）。"""

    role: str
    content: str
    tool_name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    ordinal: Optional[int] = None
    message_id: Optional[str] = None


class MemoryStore:
    """SQLite 四表会话存储。

    Parameters
    ----------
    db_path : str, optional
        数据库文件路径；缺省放数据目录 ``research_memory.db``。
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = os.path.abspath(os.path.expanduser(db_path or self._default_path()))
        parent = os.path.dirname(self.db_path) or os.curdir
        os.makedirs(parent, exist_ok=True)
        self._init_db()

    @staticmethod
    def _default_path() -> str:
        try:
            from system.config import get_data_dir

            return os.path.join(get_data_dir(), "research_memory.db")
        except Exception:  # noqa: BLE001 - 脱离 apiserver 独立可用
            return os.path.join(os.path.expanduser("~"), ".lumo", "research_memory.db")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._session() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.execute("PRAGMA user_version = 1")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """sqlite3 的 ``with conn`` 只管事务不管关闭，这里显式 commit+close，
        避免 Windows 上连接泄漏导致文件锁。"""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        model_name: str = "",
        workflow_type: str = "",
        title: str = "",
    ) -> None:
        now = datetime.now().isoformat()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, title, model_name, workflow_type,
                     query_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (session_id, title, model_name, workflow_type, now, now),
            )

    def session_count(self) -> int:
        with self._session() as conn:
            return conn.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # messages：追加 + 前缀增量同步
    # ------------------------------------------------------------------

    def save_messages(self, session_id: str, messages: list[SessionMessage]) -> None:
        """追加消息并累计 query_count（human 计数）。"""
        if not messages:
            return
        now = datetime.now().isoformat()
        human_count = sum(1 for m in messages if m.role == "human")
        with self._session() as conn:
            conn.executemany(
                """
                INSERT INTO messages
                    (session_id, role, content, tool_name, timestamp, ordinal, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [self._message_row(session_id, m) for m in messages],
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ?, query_count = query_count + ? "
                "WHERE session_id = ?",
                (now, human_count, session_id),
            )

    def synchronize_messages(
        self, session_id: str, messages: list[SessionMessage]
    ) -> int:
        """以传入序列为权威转录，做前缀增量同步。返回本次新写入条数。

        - 库内 message_id 序列是传入序列的**前缀** → 只补尾部（幂等：
          同一条消息重复同步不产生重复行）
        - 否则（历史被改写/截断重排）→ 删除重建
        """
        now = datetime.now().isoformat()
        with self._session() as conn:
            stored = conn.execute(
                "SELECT message_id FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            stored_ids = [row["message_id"] for row in stored]
            incoming_ids = [m.message_id for m in messages]
            is_prefix = (
                all(stored_ids)
                and len(stored_ids) <= len(incoming_ids)
                and stored_ids == incoming_ids[: len(stored_ids)]
            )
            if is_prefix:
                suffix = messages[len(stored_ids):]
            else:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                suffix = list(messages)

            conn.executemany(
                """
                INSERT INTO messages
                    (session_id, role, content, tool_name, timestamp, ordinal, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [self._message_row(session_id, m) for m in suffix],
            )
            query_count = sum(m.role == "human" for m in messages)
            conn.execute(
                "UPDATE sessions SET query_count = ?, updated_at = ? WHERE session_id = ?",
                (query_count, now, session_id),
            )
            return len(suffix)

    def get_messages(self, session_id: str) -> list[SessionMessage]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [
            SessionMessage(
                role=r["role"],
                content=r["content"],
                tool_name=r["tool_name"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                ordinal=r["ordinal"],
                message_id=r["message_id"],
            )
            for r in rows
        ]

    @staticmethod
    def _message_row(session_id: str, m: SessionMessage) -> tuple:
        return (
            session_id,
            m.role,
            m.content,
            m.tool_name,
            m.timestamp.isoformat(),
            m.ordinal,
            m.message_id,
        )

    # ------------------------------------------------------------------
    # tasks（对接 research.execution 的 TaskSpec）
    # ------------------------------------------------------------------

    def add_task(
        self,
        task_id: str,
        session_id: str,
        task_type: str = "python",
        spec: Any = None,
    ) -> None:
        """登记一条任务；spec 支持 TaskSpec/pydantic/dict，序列化落 JSON。"""
        now = datetime.now().isoformat()
        spec_json = None
        if spec is not None:
            if hasattr(spec, "model_dump"):
                spec = spec.model_dump(exclude={"callable"})
            spec_json = json.dumps(spec, ensure_ascii=False, default=str)
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO tasks
                    (task_id, session_id, task_type, spec_json, status,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status, updated_at = excluded.updated_at
                """,
                (task_id, session_id, task_type, spec_json, now, now),
            )

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._session() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, result = ?, error_text = ?, updated_at = ? "
                "WHERE task_id = ?",
                (status, result, error_text, now, task_id),
            )

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------

    def add_event(
        self, session_id: str, event_type: str, payload: Any = None
    ) -> None:
        now = datetime.now().isoformat()
        payload_json = (
            json.dumps(payload, ensure_ascii=False, default=str)
            if payload is not None
            else None
        )
        with self._session() as conn:
            conn.execute(
                "INSERT INTO events (session_id, event_type, payload, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (session_id, event_type, payload_json, now),
            )

    def get_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]
