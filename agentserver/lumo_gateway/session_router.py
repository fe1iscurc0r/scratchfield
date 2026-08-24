"""会话路由：{platform}:{user_id} → 陆墨 session_id 映射，SQLite 持久化。

设计要点：
  - 路由键（内部）用 "{platform}:{user_id}"，语义清晰
  - 陆墨 session_id 必须满足 lumo_proxy 校验 ^[a-zA-Z0-9_-]{1,64}$（冒号非法），
    因此做确定性映射：冒号→下划线；超长/非法则 sha1 截断（保证合法且可复现）
  - SQLite 持久化 gateway/data/sessions.db，重启不丢映射
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

from .models import SessionMap

logger = logging.getLogger("lumo_gateway.session_router")

# 与 apiserver/routes/lumo_proxy.py 的 ChatCompletionRequest.session_id 校验一致
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    route_key   TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""


def make_session_id(route_key: str) -> str:
    """把路由键映射为 lumo_proxy 合法的 session_id（确定性，重启可复现）。"""
    sid = route_key.replace(":", "_")
    if _SESSION_ID_RE.match(sid):
        return sid
    # 超长或含非法字符 → sha1 摘要截断，确定性且满足 ^[a-zA-Z0-9_-]{1,64}$
    digest = hashlib.sha1(route_key.encode("utf-8")).hexdigest()
    return digest[:32]


class SessionRouter:
    """SQLite 持久化会话映射。asyncio 单事件循环下同步 sqlite3 调用（本地快速）。"""

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get_or_create(self, platform: str, user_id: str) -> SessionMap:
        """路由键 {platform}:{user_id} → 陆墨 session_id；不存在则创建并持久化。"""
        route_key = f"{platform}:{user_id}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row = self._conn.execute(
            "SELECT route_key, session_id, created_at, updated_at FROM sessions WHERE route_key = ?",
            (route_key,),
        ).fetchone()
        if row:
            return SessionMap(*row)
        sid = make_session_id(route_key)
        self._conn.execute(
            "INSERT OR IGNORE INTO sessions (route_key, session_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (route_key, sid, now, now),
        )
        self._conn.commit()
        return SessionMap(route_key, sid, now, now)

    def get(self, platform: str, user_id: str) -> SessionMap | None:
        """查询映射；不存在返回 None（不创建）。"""
        route_key = f"{platform}:{user_id}"
        row = self._conn.execute(
            "SELECT route_key, session_id, created_at, updated_at FROM sessions WHERE route_key = ?",
            (route_key,),
        ).fetchone()
        return SessionMap(*row) if row else None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
