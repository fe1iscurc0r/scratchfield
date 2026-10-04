"""工单板 — orca「Run 状态库」+ multica「board 工作台」落地。

SQLite 持久化（tasks / leases / reviews 三表），持有任务状态，
所有变更经 state_machine 校验、带 reason code、自动发事件（若注入 EventBus）。

设计约束（硬约束）：
- 纯 Python 标准库 sqlite3，不引外部任务队列服务。
- 兼容现有 BATCH-WORKORDERS 格式：Task 可 to_dict / from_dict 往返导入导出。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from mcpserver.workflow.event_bus import (
    EVENT_REVIEW_APPROVED,
    EVENT_REVIEW_REQUESTED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_CLAIMED,
    EVENT_TASK_CREATED,
    EVENT_TASK_DONE,
    EventBus,
)
from mcpserver.workflow.reason import ReasonCode, is_blocked_code
from mcpserver.workflow.state_machine import TransitionError, validate_transition
from mcpserver.workflow.task import (
    ACTIVE_STATUSES,
    STATUS_BLOCKED,
    STATUS_DISPATCHED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_PENDING,
    STATUS_READY,
    TERMINAL_STATUSES,
    Task,
    utcnow_iso,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    desc TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    assignee TEXT,
    deps TEXT NOT NULL DEFAULT '[]',
    parent TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reason_code TEXT,
    review TEXT
);
CREATE TABLE IF NOT EXISTS leases (
    task_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    owner TEXT NOT NULL,
    expires_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    PRIMARY KEY (task_id, scope)
);
CREATE TABLE IF NOT EXISTS reviews (
    task_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    approved INTEGER NOT NULL,
    conclusion TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_reviews_task ON reviews(task_id);
"""


def topological_sort(tasks: list[Task]) -> list[str]:
    """Kahn 拓扑排序：按 deps 依赖关系返回 task id 顺序，环则抛 ValueError。"""
    ids = {t.id for t in tasks}
    indegree: dict[str, int] = {t.id: 0 for t in tasks}
    dependents: dict[str, list[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        for dep in t.deps:
            if dep in ids:
                indegree[t.id] += 1
                dependents.setdefault(dep, []).append(t.id)

    ready = [tid for tid, deg in indegree.items() if deg == 0]
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for child in dependents.get(node, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)

    if len(order) != len(tasks):
        raise ValueError("task dependency graph contains a cycle")
    return order


class Board:
    """工单板：SQLite 存储 + 状态机校验 + reason code + 事件发布。"""

    def __init__(self, db_path: str | Path = ":memory:",
                 event_bus: EventBus | None = None,
                 source: str = "board",
                 review_gate_enabled: bool = True):
        self._db_path = str(db_path)
        self.event_bus = event_bus
        self.source = source
        self.review_gate_enabled = review_gate_enabled
        self._lock = threading.RLock()

        # check_same_thread=False + 内部锁，允许单实例跨线程 / 多实例共享文件
        self.conn = sqlite3.connect(self._db_path, timeout=10.0,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 10000")
        if self._db_path != ":memory:":
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                pass
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── 内部工具 ──
    def _now(self) -> float:
        return time.time()

    def _emit(self, event_type: str, payload: dict[str, Any],
              trace_id: str | None = None) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(event_type, self.source, payload=payload,
                               trace_id=trace_id)

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            desc=row["desc"],
            status=row["status"],
            assignee=row["assignee"],
            deps=json.loads(row["deps"] or "[]"),
            parent=row["parent"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reason_code=row["reason_code"],
            review=json.loads(row["review"]) if row["review"] else None,
        )

    # ── 查询 ──
    def get(self, task_id: str) -> Task | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def list(self, status: str | None = None,
             assignee: str | None = None) -> list[Task]:
        q = "SELECT * FROM tasks"
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if assignee is not None:
            clauses.append("assignee = ?")
            params.append(assignee)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at ASC, id ASC"
        with self._lock:
            rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    # ── 创建 / 入队 ──
    def create(self, task: Task, trace_id: str | None = None) -> Task:
        """原样插入工单；id 已存在则抛 ValueError。"""
        with self._lock:
            if self.get(task.id) is not None:
                raise ValueError(f"task already exists: {task.id}")
            self.conn.execute(
                """INSERT INTO tasks
                   (id, title, desc, status, assignee, deps, parent,
                    created_at, updated_at, reason_code, review)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (task.id, task.title, task.desc, task.status, task.assignee,
                 json.dumps(task.deps), task.parent,
                 task.created_at, task.updated_at, task.reason_code,
                 json.dumps(task.review) if task.review else None),
            )
            self.conn.commit()
        self._emit(EVENT_TASK_CREATED,
                   {"task_id": task.id, "title": task.title}, trace_id)
        return task

    def enqueue(self, task: Task, trace_id: str | None = None) -> tuple[Task, ReasonCode]:
        """幂等入队：重复 enqueue 抑制。

        - 新 id → 插入，返回 QUEUED
        - id 已存在 → 合并，返回既有任务 + COALESCED（不重复派发）
        """
        existing = self.get(task.id)
        if existing is not None:
            return existing, ReasonCode.COALESCED
        self.create(task, trace_id=trace_id)
        return task, ReasonCode.QUEUED

    # ── 派发 / 认领 / 状态 ──
    def assign(self, task_id: str, assignee: str,
               trace_id: str | None = None) -> Task:
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET assignee = ?, updated_at = ? WHERE id = ?",
                (assignee, utcnow_iso(), task_id),
            )
            self.conn.commit()
        self._emit(EVENT_TASK_ASSIGNED,
                   {"task_id": task_id, "assignee": assignee}, trace_id)
        # 派发即触发（multica assign 语义）：依赖满足的 pending 提升为 ready
        updated = self.get(task_id)
        if updated.status == STATUS_PENDING and self.deps_satisfied(updated):
            self.set_status(task_id, STATUS_READY)
        return self.get(task_id)  # type: ignore[return-value]

    def set_status(self, task_id: str, to_status: str,
                   reason_code: str | None = None,
                   trace_id: str | None = None) -> Task:
        """通用状态迁移（经 state_machine 校验），自动发对应事件。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        validate_transition(task.status, to_status, reason_code=reason_code)
        if to_status == STATUS_BLOCKED and not is_blocked_code(reason_code):
            raise ValueError(f"invalid blocked reason code: {reason_code!r}")

        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET status = ?, reason_code = ?, updated_at = ? WHERE id = ?",
                (to_status, reason_code, utcnow_iso(), task_id),
            )
            self.conn.commit()

        event_type = {
            STATUS_DONE: EVENT_TASK_DONE,
            STATUS_BLOCKED: EVENT_TASK_BLOCKED,
            STATUS_IN_REVIEW: EVENT_REVIEW_REQUESTED,
            STATUS_IN_PROGRESS: EVENT_TASK_CLAIMED,
            STATUS_DISPATCHED: EVENT_TASK_ASSIGNED,
        }.get(to_status)
        if event_type:
            self._emit(event_type,
                       {"task_id": task_id, "assignee": task.assignee,
                        "reason_code": reason_code}, trace_id)
        return self.get(task_id)  # type: ignore[return-value]

    def claim_task(self, task_id: str, owner: str,
                   trace_id: str | None = None) -> Task:
        """认领成功后推进状态到 in_progress（claim.py 单赢家胜出后调用）。

        - 已 in_progress → 幂等返回（租约是持租权威，状态不再空转）。
        - ready / dispatched → 迁移到 in_progress。
        - 其他状态 → 经 state_machine 校验（pending/终态会被拒绝）。
        """
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        if task.status == STATUS_IN_PROGRESS:
            return task
        return self.set_status(task_id, STATUS_IN_PROGRESS, trace_id=trace_id)

    def block(self, task_id: str, reason_code: str,
              trace_id: str | None = None) -> Task:
        """阻塞（blocked 必带合法 reason code）。"""
        return self.set_status(task_id, STATUS_BLOCKED,
                               reason_code=reason_code, trace_id=trace_id)

    def deps_satisfied(self, task: Task) -> bool:
        """依赖 DAG：所有 deps 均为终态（done）才算满足。"""
        for dep in task.deps:
            d = self.get(dep)
            if d is None or d.status != STATUS_DONE:
                return False
        return True

    def promote_ready(self) -> list[Task]:
        """依赖满足的 pending 任务提升为 ready（返回被提升的任务列表）。"""
        promoted: list[Task] = []
        for task in self.list(status=STATUS_PENDING):
            if self.deps_satisfied(task):
                promoted.append(self.set_status(task.id, STATUS_READY))
        return promoted

    # ── 审查门（G-02 集成）──
    def complete(self, task_id: str, trace_id: str | None = None) -> Task:
        """完成：review_gate_enabled 时进 in_review（不进 done），否则直接 done。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        if self.review_gate_enabled:
            return self.set_status(task_id, STATUS_IN_REVIEW, trace_id=trace_id)
        return self.set_status(task_id, STATUS_DONE, trace_id=trace_id)

    def approve(self, task_id: str, reviewer: str, conclusion: str = "",
                trace_id: str | None = None) -> Task:
        """人审通过：in_review → done，记录 review 时间/人/结论。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        validate_transition(task.status, STATUS_DONE)
        self._record_review(task_id, reviewer, approved=True,
                            conclusion=conclusion)
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET status = ?, reason_code = NULL, updated_at = ? WHERE id = ?",
                (STATUS_DONE, utcnow_iso(), task_id),
            )
            self.conn.commit()
        self._emit(EVENT_REVIEW_APPROVED,
                   {"task_id": task_id, "reviewer": reviewer,
                    "assignee": task.assignee}, trace_id)
        return self.get(task_id)  # type: ignore[return-value]

    def reject(self, task_id: str, reviewer: str, conclusion: str = "",
               trace_id: str | None = None) -> Task:
        """人审退回：in_review → in_progress，记录审查结论。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        validate_transition(task.status, STATUS_IN_PROGRESS)
        self._record_review(task_id, reviewer, approved=False,
                            conclusion=conclusion)
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (STATUS_IN_PROGRESS, utcnow_iso(), task_id),
            )
            self.conn.commit()
        self._emit(EVENT_TASK_ASSIGNED,
                   {"task_id": task_id, "assignee": task.assignee,
                    "reviewer": reviewer}, trace_id)
        return self.get(task_id)  # type: ignore[return-value]

    def _record_review(self, task_id: str, reviewer: str,
                       approved: bool, conclusion: str) -> None:
        review = {
            "reviewer": reviewer,
            "approved": bool(approved),
            "conclusion": conclusion,
            "reviewed_at": utcnow_iso(),
        }
        with self._lock:
            self.conn.execute(
                "INSERT INTO reviews (task_id, reviewer, approved, conclusion, reviewed_at)"
                " VALUES (?,?,?,?,?)",
                (task_id, reviewer, int(approved), conclusion, review["reviewed_at"]),
            )
            self.conn.execute(
                "UPDATE tasks SET review = ? WHERE id = ?",
                (json.dumps(review), task_id),
            )
            self.conn.commit()

    def list_reviews(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM reviews WHERE task_id = ? ORDER BY reviewed_at ASC",
                (task_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 依赖 DAG ──
    def topological_order(self) -> list[str]:
        """当前板上全部任务的依赖拓扑序（环则抛 ValueError）。"""
        return topological_sort(self.list())
