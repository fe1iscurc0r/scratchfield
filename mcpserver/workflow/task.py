"""Task 数据类 — orca「工作项」+ multica「issue 即工作单元」语义。

字段对齐三份授粉报告：
- orca: Task(spec, deps, parent, status)，Task 与 Dispatch 分离
- multica: issue 是工作载体，assignee 归属，生命周期 backlog→active→in_review→done
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any

# 状态常量（与 orca 状态机对齐，扩展 multica 的 in_review 审查门）
STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_DISPATCHED = "dispatched"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_IN_REVIEW = "in_review"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

ALL_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_READY,
    STATUS_DISPATCHED,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_IN_REVIEW,
    STATUS_DONE,
    STATUS_FAILED,
)

# 终态：不再接受任何迁移
TERMINAL_STATUSES: frozenset[str] = frozenset({STATUS_DONE, STATUS_FAILED})

# 活跃态：任务正在推进中（认领/派发/审查），非静止
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {STATUS_DISPATCHED, STATUS_IN_PROGRESS, STATUS_IN_REVIEW}
)


def utcnow_iso() -> str:
    """统一时间戳格式（ISO-8601 UTC），用于 created_at / updated_at。"""
    return datetime.now(UTC).isoformat()


@dataclass
class Task:
    """工单工作单元。

    - deps: 依赖工单 id 列表（Task DAG 边，对应 orca tasks.deps）
    - parent: 父工单 id（对应 orca tasks.parent_id / multica parent_issue_id）
    - reason_code: 进入 blocked 时必须携带的稳定 reason code（G-02 集成）
    - review: 审查结论元数据（G-02 审查门回写）
    """

    id: str
    title: str = ""
    desc: str = ""
    status: str = STATUS_PENDING
    assignee: str | None = None
    deps: list[str] = field(default_factory=list)
    parent: str | None = None
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)
    reason_code: str | None = None
    review: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "desc": self.desc,
            "status": self.status,
            "assignee": self.assignee,
            "deps": list(self.deps),
            "parent": self.parent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason_code": self.reason_code,
            "review": self.review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            desc=data.get("desc", ""),
            status=data.get("status", STATUS_PENDING),
            assignee=data.get("assignee"),
            deps=list(data.get("deps") or []),
            parent=data.get("parent"),
            created_at=data.get("created_at") or utcnow_iso(),
            updated_at=data.get("updated_at") or utcnow_iso(),
            reason_code=data.get("reason_code"),
            review=data.get("review"),
        )
