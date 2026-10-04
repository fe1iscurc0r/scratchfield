# -*- coding: utf-8 -*-
"""工单 phase/gate 状态机 + 审批门（W66-03 · 不可逆 action 需显式批准）。

- 状态机 in_review → (gate.resolved | revision_requested)，gate 永不自动 resolve
- 工单模板 approval_gates: [] 字段；不可逆 action 返回 PENDING_APPROVAL
- 循环检测 + BREAK-LOOP：同一 tool+意图 3 轮无进展 → 注入破环指令

纯标准库。运行：python tools/workorder_state_machine.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

PENDING_APPROVAL = "PENDING_APPROVAL"


@dataclass
class WorkOrder:
    id: str
    approval_gates: list[str] = field(default_factory=list)
    resolved_gates: set[str] = field(default_factory=set)
    status: str = "in_review"
    _loop_counter: dict[str, int] = field(default_factory=dict)

    def all_gates_resolved(self) -> bool:
        return set(self.approval_gates) <= self.resolved_gates

    def resolve_gate(self, gate: str, token: str) -> bool:
        """显式批准令牌才 resolve gate（永不自动 resolve）。"""
        if token != "APPROVED":
            return False
        self.resolved_gates.add(gate)
        return True

    def try_advance(self) -> str:
        """不可逆 action 前检查：gate 未全批 → PENDING_APPROVAL。"""
        if self.status != "in_review":
            return self.status
        if not self.all_gates_resolved():
            return PENDING_APPROVAL
        self.status = "gate.resolved"
        return self.status

    def request_revision(self) -> None:
        self.status = "revision_requested"


@dataclass
class LoopDetector:
    """BREAK-LOOP：同一 tool+意图 3 轮无进展 → 注入破环指令。"""
    max_rounds: int = 3
    _counts: dict[str, int] = field(default_factory=dict)

    def track(self, tool: str, intent: str) -> str | None:
        """记录一轮；达阈值返回破环指令，否则 None。"""
        key = f"{tool}:{intent}"
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] >= self.max_rounds:
            return f"BREAK-LOOP: {tool} 意图 {intent} 已 {self._counts[key]} 轮无进展，请更换策略"
        return None


if __name__ == "__main__":
    wo = WorkOrder("w1", approval_gates=["gate-a"])
    print("未批准推进:", wo.try_advance())
    wo.resolve_gate("gate-a", "APPROVED")
    print("批准后推进:", wo.try_advance())
    d = LoopDetector()
    for _ in range(3):
        print("破环?", d.track("tool-x", "意图-y"))
