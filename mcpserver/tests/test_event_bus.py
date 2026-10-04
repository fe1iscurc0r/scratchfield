"""G-03 验收：事件总线 + 生命周期状态机。

覆盖（≥7 用例）：
1. pub/sub（订阅者收到事件）
2. 事件持久化（回放读回）
3. 回放重建 agent 状态
4. 订阅过滤（按事件类型）
5. trace_id 贯穿（同一逻辑链共享 trace_id）
6. 坏事件容错（坏行跳过，不中断回放）
7. 与 workflow 集成（任务状态变更自动发事件 + 事件流推导 agent 状态）
8. 退订（附加）
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
sys.path.insert(0, REPO_ROOT)

from mcpserver.workflow.agent_state import (
    AGENT_BLOCKED,
    AGENT_DONE,
    AGENT_WAITING_REVIEW,
    AGENT_WORKING,
    AgentStateMachine,
)
from mcpserver.workflow.board import Board
from mcpserver.workflow.claim import claim
from mcpserver.workflow.event_bus import (
    EVENT_REVIEW_APPROVED,
    EVENT_REVIEW_REQUESTED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_CLAIMED,
    EVENT_TASK_CREATED,
    EVENT_TASK_DONE,
    Event,
    EventBus,
    new_trace_id,
)
from mcpserver.workflow.reason import ReasonCode
from mcpserver.workflow.task import Task


class TestPubSub(unittest.TestCase):
    def test_pub_sub(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EVENT_TASK_CLAIMED, received.append)
        ev = bus.publish(EVENT_TASK_CLAIMED, "s", {"task_id": "T1"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].id, ev.id)

    def test_subscription_filter(self):
        bus = EventBus()
        got: list[str] = []
        bus.subscribe(EVENT_TASK_CLAIMED, lambda e: got.append(e.event_type))
        bus.publish(EVENT_TASK_CREATED, "s")
        bus.publish(EVENT_TASK_CLAIMED, "s")
        self.assertEqual(got, [EVENT_TASK_CLAIMED])

    def test_unsubscribe(self):
        bus = EventBus()
        got: list[int] = []
        unsub = bus.subscribe(EVENT_TASK_DONE, lambda e: got.append(1))
        bus.publish(EVENT_TASK_DONE, "s")
        unsub()
        bus.publish(EVENT_TASK_DONE, "s")
        self.assertEqual(len(got), 1)


class TestPersistence(unittest.TestCase):
    def test_event_persistence_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "events.jsonl")
            bus = EventBus(log)
            bus.publish(EVENT_TASK_CREATED, "s", {"task_id": "A"})
            bus.publish(EVENT_TASK_ASSIGNED, "s", {"task_id": "A", "assignee": "golf"})
            events = bus.replay()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].event_type, EVENT_TASK_CREATED)
            self.assertEqual(events[1].event_type, EVENT_TASK_ASSIGNED)

    def test_trace_id_throughput(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "events.jsonl")
            bus = EventBus(log)
            trace = new_trace_id()
            bus.publish(EVENT_TASK_ASSIGNED, "s", {"assignee": "golf"}, trace_id=trace)
            bus.publish(EVENT_TASK_CLAIMED, "s", {"assignee": "golf"}, trace_id=trace)
            bus.publish(EVENT_TASK_DONE, "s", {"assignee": "golf"}, trace_id=trace)
            traced = bus.replay(trace_id=trace)
            self.assertEqual(len(traced), 3)
            self.assertTrue(all(e.trace_id == trace for e in traced))

    def test_bad_event_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "events.jsonl")
            bus = EventBus(log)
            bus.publish(EVENT_TASK_CREATED, "s", {"task_id": "A"})
            bus.publish(EVENT_TASK_CREATED, "s", {"task_id": "B"})
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("not-valid-json{{{\n")
                fh.write('{"id":"orphan"}\n')  # 缺 event_type → 容错跳过
            events = bus.replay()
            self.assertEqual(len(events), 2)


class TestAgentState(unittest.TestCase):
    def _seq(self):
        return [
            Event(event_type=EVENT_TASK_ASSIGNED, source="s", payload={"assignee": "golf"}),
            Event(event_type=EVENT_TASK_CLAIMED, source="s", payload={"assignee": "golf"}),
            Event(event_type=EVENT_TASK_BLOCKED, source="s", payload={"assignee": "golf"}),
            Event(event_type=EVENT_REVIEW_REQUESTED, source="s", payload={"assignee": "golf"}),
            Event(event_type=EVENT_REVIEW_APPROVED, source="s", payload={"assignee": "golf"}),
        ]

    def test_replay_rebuild_agent_state(self):
        sm = AgentStateMachine("golf")
        final = sm.rebuild(self._seq())
        self.assertEqual(final, AGENT_DONE)

    def test_derive_ignores_other_agents(self):
        events = [
            Event(event_type=EVENT_TASK_BLOCKED, source="s", payload={"assignee": "other"}),
            Event(event_type=EVENT_TASK_CLAIMED, source="s", payload={"assignee": "golf"}),
        ]
        self.assertEqual(AgentStateMachine("golf").derive(events), AGENT_WORKING)


class TestWorkflowIntegration(unittest.TestCase):
    def test_task_state_changes_emit_events_and_rebuild_agent_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "events.jsonl")
            bus = EventBus(log)
            board = Board(":memory:", event_bus=bus, source="golf")

            board.create(Task(id="T1", status="ready", assignee="agent-golf"))
            board.assign("T1", "agent-golf")
            self.assertTrue(claim(board, "T1", "s", "agent-golf", ttl_seconds=30))
            board.block("T1", ReasonCode.RUNTIME_OFFLINE.value)
            board.set_status("T1", "in_progress")  # 解除阻塞
            board.complete("T1")                   # → in_review
            board.approve("T1", reviewer="shenyao", conclusion="通过")

            types = [e.event_type for e in bus.replay()]
            self.assertIn(EVENT_TASK_CREATED, types)
            self.assertIn(EVENT_TASK_ASSIGNED, types)
            self.assertIn(EVENT_TASK_CLAIMED, types)
            self.assertIn(EVENT_TASK_BLOCKED, types)
            self.assertIn(EVENT_REVIEW_REQUESTED, types)
            self.assertIn(EVENT_REVIEW_APPROVED, types)

            sm = AgentStateMachine("agent-golf")
            final = sm.rebuild(bus.replay())
            self.assertEqual(final, AGENT_DONE)
            board.close()


if __name__ == "__main__":
    unittest.main()
