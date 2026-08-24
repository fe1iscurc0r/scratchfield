"""SPEC-03 Phase1.3 — 会话血统（旁路）。

父会话 ID + 分支标记，支持 fork/trace/branches。机制参考 openclaw 的
parentSessionKey → forkSessionFromParent（vendor/openclaw/src/auto-reply/
reply/session.ts:481-513）：子会话继承父 key、父上下文过大时拒 fork。
本模块为独立 SQLite 实现，不接入 openclaw 网关，不触 NEKO 现有会话表。
License: MIT（机制同源 openclaw/MIT；实现独立）。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    parent_id TEXT,
    branch_label TEXT NOT NULL DEFAULT 'main',
    summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lin_parent ON sessions(parent_id);
"""

MAX_FORK_CONTEXT_CHARS = 40_000  # 对齐 openclaw parentForkMaxTokens 思想：过大拒 fork


class LineageError(ValueError):
    pass


class SessionLineage:
    def __init__(self, db_path: str | Path):
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def register(self, session_id: str, parent_id: str | None = None,
                 branch_label: str = "main", summary: str = "",
                 parent_context_chars: int = 0) -> dict:
        """登记会话；带父时校验：祖先链存在、无环、父上下文不超限。"""
        if parent_id:
            if not self._exists(parent_id):
                raise LineageError(f"父会话不存在: {parent_id}")
            chain = self.trace(parent_id)
            if session_id in [s["session_id"] for s in chain]:
                raise LineageError("检测到血统环")
            if parent_context_chars > MAX_FORK_CONTEXT_CHARS:
                raise LineageError(
                    f"父上下文 {parent_context_chars} 字符超过 fork 上限 {MAX_FORK_CONTEXT_CHARS}，拒绝分支（防线程化）"
                )
        self.db.execute(
            "INSERT OR REPLACE INTO sessions(session_id, parent_id, branch_label, summary, created_at)"
            " VALUES (?,?,?,?,?)",
            (session_id, parent_id, branch_label, summary, time.time()),
        )
        self.db.commit()
        return self.get(session_id)

    def get(self, session_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT session_id, parent_id, branch_label, summary, created_at FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return {"session_id": row[0], "parent_id": row[1], "branch_label": row[2],
                "summary": row[3], "created_at": row[4]}

    def trace(self, session_id: str) -> list[dict]:
        """从该会话上溯到根（含自身），顺序 [根..自身]。血统可追溯验收点。"""
        chain, cur, seen = [], session_id, set()
        while cur and cur not in seen:
            seen.add(cur)
            node = self.get(cur)
            if not node:
                break
            chain.append(node)
            cur = node["parent_id"]
        chain.reverse()
        return chain

    def children(self, session_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT session_id, parent_id, branch_label, summary, created_at FROM sessions"
            " WHERE parent_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [{"session_id": r[0], "parent_id": r[1], "branch_label": r[2],
                 "summary": r[3], "created_at": r[4]} for r in rows]

    def branches_under(self, root_id: str) -> dict[str, list[str]]:
        """root 下的分支树：{branch_label: [session_id...]}（BFS）。"""
        out: dict[str, list[str]] = {}
        frontier = [root_id]
        while frontier:
            nxt = []
            for sid in frontier:
                for ch in self.children(sid):
                    out.setdefault(ch["branch_label"], []).append(ch["session_id"])
                    nxt.append(ch["session_id"])
            frontier = nxt
        return out

    def _exists(self, sid: str) -> bool:
        return self.get(sid) is not None

    def close(self) -> None:
        self.db.close()
