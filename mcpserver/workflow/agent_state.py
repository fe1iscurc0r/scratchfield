"""agent 生命周期状态机 — herdr「五态状态机」+ buzz「事件驱动」落地。

状态：idle / working / blocked / waiting_review / done
由事件流推导（fold），可回放重建：状态不是自报的，而是从事件序列折叠出来的事实。

事件 → 状态映射（仅作用于该 agent 的 assignee 事件）：
- task_claimed / task_assigned → working
- task_blocked               → blocked
- review_requested           → waiting_review
- task_done / review_approved → done
"""

from __future__ import annotations

from mcpserver.workflow.event_bus import (
    EVENT_REVIEW_APPROVED,
    EVENT_REVIEW_REQUESTED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_CLAIMED,
    EVENT_TASK_DONE,
    Event,
)

# agent 状态常量（对齐 herdr：blocked/working/done/idle + 本仓审查态 waiting_review）
AGENT_IDLE = "idle"
AGENT_WORKING = "working"
AGENT_BLOCKED = "blocked"
AGENT_WAITING_REVIEW = "waiting_review"
AGENT_DONE = "done"

ALL_AGENT_STATES: tuple[str, ...] = (
    AGENT_IDLE,
    AGENT_WORKING,
    AGENT_BLOCKED,
    AGENT_WAITING_REVIEW,
    AGENT_DONE,
)

# 事件类型 → 该 agent 的目标状态
_EVENT_TO_STATE: dict[str, str] = {
    EVENT_TASK_CLAIMED: AGENT_WORKING,
    EVENT_TASK_ASSIGNED: AGENT_WORKING,
    EVENT_TASK_BLOCKED: AGENT_BLOCKED,
    EVENT_REVIEW_REQUESTED: AGENT_WAITING_REVIEW,
    EVENT_TASK_DONE: AGENT_DONE,
    EVENT_REVIEW_APPROVED: AGENT_DONE,
}


def event_targets_agent(event: Event, agent_id: str) -> bool:
    """判断事件是否作用于指定 agent（以 payload['assignee'] 为准）。"""
    payload = event.payload or {}
    return payload.get("assignee") == agent_id


class AgentStateMachine:
    """单个 agent 的生命周期状态，由事件流增量推导 / 全量回放重建。"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.state = AGENT_IDLE

    def apply(self, event: Event) -> str:
        """应用单条事件，返回最新状态（非本 agent 的事件忽略）。"""
        if not event_targets_agent(event, self.agent_id):
            return self.state
        target = _EVENT_TO_STATE.get(event.event_type)
        if target is not None:
            self.state = target
        return self.state

    def rebuild(self, events: list[Event]) -> str:
        """从事件序列全量回放重建状态（幂等：先复位再逐条 apply）。"""
        self.state = AGENT_IDLE
        for event in events:
            self.apply(event)
        return self.state

    def derive(self, events: list[Event]) -> str:
        """纯函数式推导：不改变实例，返回事件序列折叠出的终态。"""
        state = AGENT_IDLE
        for event in events:
            if not event_targets_agent(event, self.agent_id):
                continue
            target = _EVENT_TO_STATE.get(event.event_type)
            if target is not None:
                state = target
        return state
