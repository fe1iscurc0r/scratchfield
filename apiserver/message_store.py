"""统一会话存储（卷110 W110-05 B 方案）。

与 NEKO 侧 ``utils/llm_client/history.SQLChatMessageHistory`` 同构的
SQLite ``message_store`` 表，陆墨后端在保存会话时双写到这里，使
NEKO↔Lumo 两侧可以共享同一份会话消息历史（NEKO 的 timeindex/memory
可直接按同 schema 读取）。

表结构（与 NEKO 完全一致）：

    id          INTEGER PRIMARY KEY AUTOINCREMENT
    session_id  TEXT
    message     TEXT  -- JSON: {"type": ..., "data": {"content": ...}}

双写失败只记日志，绝不影响主链路（save_conversation_and_logs 的
try/except 已兜底）。temporary 会话不写入统一存储。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


def _default_db_path() -> Path:
    """统一存储 DB 路径：数据目录下 message_store.db（与 sessions/ 同级）。"""
    try:
        from system.config import get_data_dir
        return Path(get_data_dir()) / "message_store.db"
    except Exception:
        return Path.home() / ".lumo" / "message_store.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS message_store ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " session_id TEXT,"
        " message TEXT)"
    )
    return conn


def serialize_message(role: str, content: str, reasoning: str | None = None) -> str:
    """与 NEKO _serialize(BaseMessage) 同形状的 JSON 序列化。

    额外携带 data.reasoning（思考链，可选）——键为增量添加，NEKO 侧读取
    data.content 的既有逻辑不受影响。
    """
    data: dict[str, Any] = {"content": content}
    if reasoning and str(reasoning).strip():
        data["reasoning"] = str(reasoning)
    return json.dumps({"type": role, "data": data}, ensure_ascii=False)


def append_message(session_id: str, role: str, content: str,
                   reasoning: str | None = None, db_path: Path | None = None) -> None:
    """追加一条消息到统一存储（参数化 SQL，无拼接）。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO message_store (session_id, message) VALUES (?, ?)",
            (session_id, serialize_message(role, content, reasoning)),
        )
        conn.commit()
    finally:
        conn.close()


def query_session(session_id: str, limit: int | None = None, db_path: Path | None = None) -> list[dict[str, Any]]:
    """按会话读回消息（按 id 升序），返回已反序列化的消息列表。

    limit 传正数时返回最新 N 条（仍按时间升序回放）。
    """
    conn = _connect(db_path)
    try:
        if limit is None:
            rows = conn.execute(
                "SELECT message FROM message_store WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT message FROM message_store WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, int(limit)),
            ).fetchall()
            rows.reverse()  # 最新 N 条，仍按时间升序回放
    finally:
        conn.close()
    messages: list[dict[str, Any]] = []
    for (raw,) in rows:
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return messages
