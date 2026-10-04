"""单赢家认领 + 租约 — multica「DB-backed 分布式租约调度」落地。

唯一键 (task_id, scope)：多实例并发认领只有 1 个赢家，其余 no-op。
租约三件套：heartbeat 续租 / 超时释放 / 显式 release。

实现要点（multica S3）：
- 唯一性由 leases 表 PRIMARY KEY (task_id, scope) 保证，INSERT 冲突即输家。
- 过期租约（expires_at <= now）可被他人窃取（AllowStaleReentry 语义）。
- 并发安全：多实例各自持有连接写同一 SQLite 文件，靠唯一索引 + busy_timeout 仲裁。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from mcpserver.workflow.board import Board


@dataclass
class Lease:
    task_id: str
    scope: str
    owner: str
    expires_at: float
    heartbeat_at: float


def claim(board: Board, task_id: str, scope: str, owner: str,
          ttl_seconds: float = 60.0, trace_id: str | None = None) -> bool:
    """认领任务租约：成功返回 True（唯一赢家），失败返回 False（no-op）。

    - 先清掉该 (task_id, scope) 已过期的租约，允许过期重入。
    - INSERT 撞唯一键 → 已有活跃租约 → 返回 False。
    - 赢家推进任务状态到 in_progress 并发 task_claimed 事件。
    """
    now = time.time()
    with board._lock:  # noqa: SLF001 — 同包内部协作
        try:
            board.conn.execute(
                "DELETE FROM leases WHERE task_id = ? AND scope = ? AND expires_at <= ?",
                (task_id, scope, now),
            )
            board.conn.execute(
                "INSERT INTO leases (task_id, scope, owner, expires_at, heartbeat_at)"
                " VALUES (?,?,?,?,?)",
                (task_id, scope, owner, now + ttl_seconds, now),
            )
            board.conn.commit()
        except sqlite3.IntegrityError:
            board.conn.rollback()
            return False
    # 赢家：推进任务状态 + 发事件
    board.claim_task(task_id, owner, trace_id=trace_id)
    return True


def heartbeat(board: Board, task_id: str, scope: str, owner: str,
              ttl_seconds: float = 60.0) -> bool:
    """续租：仅持租者（owner 匹配）可续，返回是否续租成功。"""
    now = time.time()
    with board._lock:
        row = board.conn.execute(
            "SELECT owner, expires_at FROM leases WHERE task_id = ? AND scope = ?",
            (task_id, scope),
        ).fetchone()
        if row is None or row["owner"] != owner or row["expires_at"] <= now:
            return False
        board.conn.execute(
            "UPDATE leases SET heartbeat_at = ?, expires_at = ? WHERE task_id = ? AND scope = ?",
            (now, now + ttl_seconds, task_id, scope),
        )
        board.conn.commit()
    return True


def release(board: Board, task_id: str, scope: str, owner: str | None = None) -> bool:
    """显式释放租约。owner 为 None 时强制释放；否则仅持租者可释放。"""
    with board._lock:
        if owner is None:
            cur = board.conn.execute(
                "DELETE FROM leases WHERE task_id = ? AND scope = ?",
                (task_id, scope),
            )
        else:
            cur = board.conn.execute(
                "DELETE FROM leases WHERE task_id = ? AND scope = ? AND owner = ?",
                (task_id, scope, owner),
            )
        board.conn.commit()
    return cur.rowcount > 0


def release_expired(board: Board, now: float | None = None) -> list[Lease]:
    """释放全部过期租约（租约超时释放），返回被释放的租约列表。"""
    now = now if now is not None else time.time()
    released: list[Lease] = []
    with board._lock:
        rows = board.conn.execute(
            "SELECT task_id, scope, owner, expires_at, heartbeat_at FROM leases WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        for r in rows:
            released.append(Lease(r["task_id"], r["scope"], r["owner"],
                                  r["expires_at"], r["heartbeat_at"]))
        board.conn.execute("DELETE FROM leases WHERE expires_at <= ?", (now,))
        board.conn.commit()
    return released


def active_lease(board: Board, task_id: str, scope: str) -> Lease | None:
    """查询当前活跃租约（未过期才返回，过期视为不存在）。"""
    now = time.time()
    with board._lock:
        row = board.conn.execute(
            "SELECT task_id, scope, owner, expires_at, heartbeat_at FROM leases"
            " WHERE task_id = ? AND scope = ? AND expires_at > ?",
            (task_id, scope, now),
        ).fetchone()
    if row is None:
        return None
    return Lease(row["task_id"], row["scope"], row["owner"],
                 row["expires_at"], row["heartbeat_at"])
