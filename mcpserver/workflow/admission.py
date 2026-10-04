"""准入检查 — multica「Admission ReasonCode」落地。

claim / status 前先校验，返回稳定 reason code（而非自由文本）。
拒绝也可机读：runtime_offline（可等）vs runtime_unusable（不可等）。

返回值约定：
- None            → 放行（调用方可继续）。
- ReasonCode 枚举 → 拒绝，携带稳定语义码。

铁律：代码在决策源头生成，绝不从错误字符串反推。
"""

from __future__ import annotations

from mcpserver.workflow.reason import ReasonCode
from mcpserver.workflow.task import (
    ACTIVE_STATUSES,
    STATUS_DISPATCHED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    Task,
)


def admit_claim(task: Task, agent_id: str, *,
                runtime_online: bool = True,
                runtime_usable: bool = True) -> ReasonCode | None:
    """认领准入：返回 None 放行，或稳定拒绝 reason code。

    判定顺序（multica S4 语义）：
    1. 任务已在活跃态（dispatched/in_progress/in_review）→ already_active
    2. 同一 agent 已在活跃任务上（自触发自己正在跑的任务）→ self_trigger_suppressed
    3. 无 assignee（目标不可达）→ target_unavailable
    4. 机器离线（等待能解决，任务排队）→ runtime_offline（可等）
    5. CLI 不可执行（等待无意义，需人修）→ runtime_unusable（不可等）
    """
    if task.assignee == agent_id and task.status in ACTIVE_STATUSES:
        return ReasonCode.SELF_TRIGGER_SUPPRESSED
    if task.status in ACTIVE_STATUSES:
        return ReasonCode.ALREADY_ACTIVE
    if not task.assignee:
        return ReasonCode.TARGET_UNAVAILABLE
    if not runtime_online:
        return ReasonCode.RUNTIME_OFFLINE
    if not runtime_usable:
        return ReasonCode.RUNTIME_UNUSABLE
    return None


def admit_transition(task: Task, to_status: str,
                     reason_code: str | None = None) -> ReasonCode | None:
    """状态流转准入：先于 state_machine 做语义层校验。

    - 终态不可再迁移 → invocation_not_allowed
    - 进入 blocked 必须带 reason code → invocation_not_allowed（缺失时）
    """
    from mcpserver.workflow.task import STATUS_BLOCKED, TERMINAL_STATUSES

    if task.status in TERMINAL_STATUSES:
        return ReasonCode.INVOCATION_NOT_ALLOWED
    if to_status == STATUS_BLOCKED and not reason_code:
        return ReasonCode.INVOCATION_NOT_ALLOWED
    return None


def admit_runtime(*, online: bool, usable: bool) -> ReasonCode | None:
    """运行时准入：离线 → runtime_offline（可等）；在线但不可用 → runtime_unusable（不可等）。"""
    if not online:
        return ReasonCode.RUNTIME_OFFLINE
    if not usable:
        return ReasonCode.RUNTIME_UNUSABLE
    return None
