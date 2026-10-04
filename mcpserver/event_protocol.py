# -*- coding: utf-8 -*-
"""NagaAgent 事件即消息协议（W64-02 · 事件回传 + 五态状态机 + wait/prompt）。

依据 docs/buzz-herdr-消息与运行时-授粉报告.md §四：
  - 结构化事件：task_id / kind（exec_done/exec_blocked/exec_metric）/ status / output_ref / sig
  - 五态状态机 pending/running/blocked/done/failed + wait(prompt, until, timeout)
  - 事件流可被 Hermes 决策层消费；审计链（哈希链）留接口

纯标准库。运行：python -m mcpserver.event_protocol
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

# 五态
STATES = ("pending", "running", "blocked", "done", "failed")
# 合法迁移表
TRANSITIONS = {
    "pending": {"running", "failed"},
    "running": {"done", "failed", "blocked"},
    "blocked": {"running", "failed", "done"},
    "done": set(),
    "failed": set(),
}


@dataclass
class Event:
    """结构化事件（可 JSON 序列化）。"""
    task_id: str
    kind: str          # exec_done / exec_blocked / exec_metric
    status: str = "pending"
    output_ref: str = ""
    sig: str = ""      # 审计链哈希（签名占位）

    def compute_sig(self, salt: str = "") -> str:
        """审计链：对事件内容做哈希（哈希链留接口）。"""
        payload = f"{salt}:{self.task_id}:{self.kind}:{self.status}:{self.output_ref}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "kind": self.kind,
            "status": self.status, "output_ref": self.output_ref, "sig": self.sig,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            task_id=d["task_id"], kind=d["kind"], status=d.get("status", "pending"),
            output_ref=d.get("output_ref", ""), sig=d.get("sig", ""),
        )


def serialize(e: Event) -> str:
    return json.dumps(e.to_dict(), ensure_ascii=False)


def deserialize(s: str) -> Event:
    return Event.from_dict(json.loads(s))


class StateMachine:
    """五态状态机：合法迁移校验。"""
    def __init__(self, initial: str = "pending") -> None:
        self.state = initial

    def transition(self, to: str) -> bool:
        if to in TRANSITIONS.get(self.state, set()):
            self.state = to
            return True
        return False


def wait(prompt: str, until_state: str, timeout: float,
         poll: callable) -> dict | None:
    """wait 原语：轮询 until 状态，超时返回 None（诚实降级：本地同步轮询 mock）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = poll()
        if result is not None and result.get("status") == until_state:
            return result
        time.sleep(0.01)
    return None


if __name__ == "__main__":
    e = Event("t1", "exec_done", status="done", output_ref="out://1")
    e.sig = e.compute_sig()
    s = serialize(e)
    print("往返一致:", deserialize(s).to_dict() == e.to_dict())
    sm = StateMachine()
    print("pending→running:", sm.transition("running"), "→done:", sm.transition("done"), "→running(非法):", sm.transition("running"))
