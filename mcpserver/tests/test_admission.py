"""G-02 验收：Admission reason code + 审查门。

覆盖（≥6 用例）：
1. reason code 语义稳定（枚举值 = 稳定字符串，非自由文本）
2. 可等 vs 不可等分类
3. admission 拦截（拒绝返回稳定 code）
4. review gate 流程（完成→in_review，人审→done）
5. 非法 code 报错
6. 与 state_machine 集成（blocked 必带 code）
"""

from __future__ import annotations

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
sys.path.insert(0, REPO_ROOT)

from mcpserver.workflow import review_gate
from mcpserver.workflow.admission import admit_claim, admit_transition
from mcpserver.workflow.board import Board
from mcpserver.workflow.reason import (
    NON_WAITABLE_BLOCKED,
    WAITABLE_BLOCKED,
    ReasonCode,
    is_waitable,
    waitability,
)
from mcpserver.workflow.state_machine import TransitionError
from mcpserver.workflow.task import Task


class TestReasonCode(unittest.TestCase):
    def test_reason_code_semantics_stable(self):
        # 枚举值即稳定字符串，可机读、可本地化、不泄露隐私
        self.assertEqual(ReasonCode.RUNTIME_OFFLINE.value, "runtime_offline")
        self.assertEqual(ReasonCode.QUEUED.value, "queued")
        self.assertEqual(ReasonCode.COALESCED.value, "coalesced")

    def test_waitable_vs_non_waitable(self):
        self.assertTrue(is_waitable(ReasonCode.RUNTIME_OFFLINE))
        self.assertFalse(is_waitable(ReasonCode.RUNTIME_UNUSABLE))
        self.assertEqual(waitability(ReasonCode.RUNTIME_OFFLINE), "waitable")
        self.assertEqual(waitability(ReasonCode.RUNTIME_UNUSABLE), "non_waitable")
        # 可等集合不含不可等
        self.assertTrue(WAITABLE_BLOCKED.isdisjoint(NON_WAITABLE_BLOCKED))


class TestAdmission(unittest.TestCase):
    def test_admission_intercepts_active_task(self):
        task = Task(id="T1", status="in_progress", assignee="agent-a")
        code = admit_claim(task, "agent-b")
        self.assertIsInstance(code, ReasonCode)
        self.assertEqual(code, ReasonCode.ALREADY_ACTIVE)

    def test_admission_self_trigger_suppressed(self):
        task = Task(id="T1", status="in_progress", assignee="agent-a")
        self.assertEqual(admit_claim(task, "agent-a"), ReasonCode.SELF_TRIGGER_SUPPRESSED)

    def test_admission_runtime_offline_vs_unusable(self):
        task = Task(id="T1", status="ready", assignee="agent-a")
        self.assertEqual(admit_claim(task, "agent-b", runtime_online=False),
                         ReasonCode.RUNTIME_OFFLINE)
        self.assertEqual(admit_claim(task, "agent-b", runtime_usable=False),
                         ReasonCode.RUNTIME_UNUSABLE)
        self.assertIsNone(admit_claim(task, "agent-b"))

    def test_admit_transition_blocked_requires_code(self):
        task = Task(id="T1", status="in_progress")
        self.assertEqual(admit_transition(task, "blocked", reason_code=None),
                         ReasonCode.INVOCATION_NOT_ALLOWED)


class TestReviewGate(unittest.TestCase):
    def test_review_gate_flow(self):
        b = Board(review_gate_enabled=True)
        b.create(Task(id="T1", status="in_progress", assignee="agent"))
        # 完成 → in_review（不进 done）
        t = review_gate.request_review(b, "T1")
        self.assertEqual(t.status, "in_review")
        # 人审通过 → done，记录审查人/结论
        t = review_gate.review(b, "T1", reviewer="shenyao", approved=True,
                               conclusion="验收通过")
        self.assertEqual(t.status, "done")
        self.assertEqual(t.review["reviewer"], "shenyao")
        self.assertTrue(t.review["approved"])
        self.assertEqual(len(b.list_reviews("T1")), 1)
        b.close()

    def test_review_gate_reject_back(self):
        b = Board(review_gate_enabled=True)
        b.create(Task(id="T1", status="in_progress", assignee="agent"))
        review_gate.request_review(b, "T1")
        t = review_gate.reject(b, "T1", reviewer="shenyao", conclusion="补测试")
        self.assertEqual(t.status, "in_progress")
        self.assertFalse(t.review["approved"])
        b.close()


class TestInvalidCode(unittest.TestCase):
    def test_invalid_blocked_reason_code_raises(self):
        b = Board()
        b.create(Task(id="T1", status="in_progress", assignee="agent"))
        with self.assertRaises(ValueError):
            b.block("T1", "随便写的自由文本")
        # 终态迁移也会被 state_machine 拦截
        b2 = Board()
        b2.create(Task(id="T2", status="done"))
        with self.assertRaises(TransitionError):
            b2.set_status("T2", "blocked", reason_code=ReasonCode.BLOCKED_ENV.value)
        b.close()
        b2.close()


if __name__ == "__main__":
    unittest.main()
