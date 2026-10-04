"""状态迁移校验 — orca 状态机 + multica 自循环/重复 enqueue 抑制。

只做「允许 / 不允许」的确定性判断，不持有任务状态（状态在 Board / Task）。
三件硬性语义：
1. 合法跳转：只允许 TRANSITIONS 表中的边；其余一律抛 TransitionError。
2. 自循环抑制：from_status == to_status 视为无操作，抛 TransitionError 阻止空转。
3. blocked 必须携带 reason code：进入 blocked 无 code 时抛 TransitionError（G-02 集成）。
"""

from __future__ import annotations

from mcpserver.workflow.task import (
    STATUS_BLOCKED,
    STATUS_DISPATCHED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_PENDING,
    STATUS_READY,
)


class TransitionError(Exception):
    """状态迁移不合法时抛出。message 为稳定英文原因，不承载自由文本决策。"""


# 允许的状态迁移表：from → 可到达的 to 集合
# pending/ready/dispatched/in_progress/blocked/in_review/done/failed
# （待处理/就绪/已派发/进行中/阻塞/评审中/完成/失败）
TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PENDING: frozenset(
        {STATUS_READY, STATUS_DISPATCHED, STATUS_FAILED}
    ),
    STATUS_READY: frozenset(
        {STATUS_DISPATCHED, STATUS_IN_PROGRESS, STATUS_FAILED}
    ),
    STATUS_DISPATCHED: frozenset(
        {STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_FAILED}
    ),
    STATUS_IN_PROGRESS: frozenset(
        {STATUS_BLOCKED, STATUS_IN_REVIEW, STATUS_FAILED}
    ),
    STATUS_BLOCKED: frozenset(
        {STATUS_READY, STATUS_IN_PROGRESS, STATUS_FAILED}
    ),
    STATUS_IN_REVIEW: frozenset(
        {STATUS_DONE, STATUS_IN_PROGRESS}
    ),
    # 终态不可再迁移
    STATUS_DONE: frozenset(),
    STATUS_FAILED: frozenset(),
}

# 进入 blocked 必须携带 reason code（G-02 集成：blocked 必带 code）
_BLOCKED_REQUIRES_REASON = STATUS_BLOCKED


def can_transition(from_status: str, to_status: str) -> bool:
    """判断一次迁移是否合法（不含自循环 / reason code 约束）。"""
    allowed = TRANSITIONS.get(from_status)
    return allowed is not None and to_status in allowed


def next_allowed(from_status: str) -> frozenset[str]:
    """返回某状态可迁移到的目标集合（供 CLI / 调度器决策）。"""
    return TRANSITIONS.get(from_status, frozenset())


def validate_transition(from_status: str, to_status: str,
                        reason_code: str | None = None) -> None:
    """校验一次状态迁移，非法则抛 TransitionError。

    - 自循环抑制：from == to → 抛错（空转被抑制）。
    - 非法跳转：不在 TRANSITIONS 表中 → 抛错。
    - blocked 必带 code：to == blocked 且 reason_code 为空 → 抛错。
    """
    if from_status == to_status:
        raise TransitionError(f"self-loop suppressed: {from_status} -> {from_status}")

    allowed = TRANSITIONS.get(from_status)
    if allowed is None or to_status not in allowed:
        raise TransitionError(f"illegal transition: {from_status} -> {to_status}")

    if to_status == _BLOCKED_REQUIRES_REASON and not reason_code:
        raise TransitionError("blocked transition requires a reason code")
