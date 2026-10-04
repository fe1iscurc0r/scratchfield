"""G-01 验收：工单状态机 + 认领/派发。

覆盖（≥8 用例）：
1. 状态机合法跳转
2. 状态机非法跳转拦截
3. 单赢家认领（并发模拟）
4. 重复 enqueue 抑制
5. 自循环抑制
6. 租约超时释放
7. 依赖 DAG 排序
8. 持久化往返
9. blocked 必带 reason code（附加）
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
sys.path.insert(0, REPO_ROOT)

from mcpserver.workflow.board import Board, topological_sort
from mcpserver.workflow.claim import active_lease, claim, release_expired
from mcpserver.workflow.reason import ReasonCode
from mcpserver.workflow.state_machine import TransitionError, validate_transition
from mcpserver.workflow.task import Task


class TestStateMachine(unittest.TestCase):
    def test_legal_transition(self):
        validate_transition("pending", "ready")
        validate_transition("ready", "in_progress")
        validate_transition("in_progress", "in_review")
        validate_transition("in_review", "done")

    def test_illegal_transition_blocked(self):
        with self.assertRaises(TransitionError):
            validate_transition("pending", "done")

    def test_self_loop_suppressed(self):
        with self.assertRaises(TransitionError):
            validate_transition("pending", "pending")

    def test_blocked_requires_reason(self):
        with self.assertRaises(TransitionError):
            validate_transition("in_progress", "blocked", reason_code=None)


class TestBoard(unittest.TestCase):
    def _board(self, path=":memory:"):
        return Board(db_path=path)

    def test_duplicate_enqueue_suppressed(self):
        b = self._board()
        t = Task(id="T1", title="hello")
        created, code = b.enqueue(t)
        self.assertEqual(code, ReasonCode.QUEUED)
        again, code2 = b.enqueue(Task(id="T1", title="hello"))
        self.assertEqual(code2, ReasonCode.COALESCED)
        self.assertEqual(again.id, created.id)
        self.assertEqual(len(b.list()), 1)
        b.close()

    def test_dependency_dag_topological_order(self):
        b = self._board()
        b.create(Task(id="A"))
        b.create(Task(id="B", deps=["A"]))
        b.create(Task(id="C", deps=["A", "B"]))
        order = b.topological_order()
        self.assertEqual(order.index("A"), 0)
        self.assertLess(order.index("A"), order.index("B"))
        self.assertLess(order.index("B"), order.index("C"))
        # 独立函数直接排序
        self.assertEqual(topological_sort(b.list()), order)
        b.close()

    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w.db")
            b = Board(db)
            b.create(Task(id="T1", title="x", status="ready"))
            b.assign("T1", "agent-a")
            b.close()
            b2 = Board(db)
            t = b2.get("T1")
            self.assertEqual(t.title, "x")
            self.assertEqual(t.assignee, "agent-a")
            self.assertEqual(t.status, "ready")
            b2.close()

    def test_blocked_records_reason_code(self):
        b = self._board()
        b.create(Task(id="T1", status="in_progress", assignee="agent"))
        t = b.block("T1", ReasonCode.RUNTIME_OFFLINE.value)
        self.assertEqual(t.status, "blocked")
        self.assertEqual(t.reason_code, "runtime_offline")
        b.close()


class TestClaim(unittest.TestCase):
    def test_single_winner_claim_concurrent(self):
        n = 8
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w.db")
            seed = Board(db)
            seed.create(Task(id="T1", status="ready", assignee="agent"))
            seed.close()

            barrier = threading.Barrier(n)
            results: list[bool] = []

            def worker(i: int):
                b = Board(db)
                barrier.wait()
                results.append(claim(b, "T1", "scope1", f"owner-{i}", ttl_seconds=30))
                b.close()

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()

            self.assertEqual(sum(1 for r in results if r), 1)
            # 终态校验：只有一个活跃租约 + 任务 in_progress
            check = Board(db)
            self.assertIsNotNone(active_lease(check, "T1", "scope1"))
            self.assertEqual(check.get("T1").status, "in_progress")
            check.close()

    def test_lease_timeout_release(self):
        b = Board()
        b.create(Task(id="T1", status="ready", assignee="agent"))
        self.assertTrue(claim(b, "T1", "s", "o1", ttl_seconds=0.05))
        time.sleep(0.1)
        released = release_expired(b)
        self.assertEqual(len(released), 1)
        self.assertIsNone(active_lease(b, "T1", "s"))
        # 过期后可被重新认领
        self.assertTrue(claim(b, "T1", "s", "o2", ttl_seconds=30))
        self.assertEqual(active_lease(b, "T1", "s").owner, "o2")
        b.close()

    def test_heartbeat_extends_lease(self):
        from mcpserver.workflow.claim import heartbeat
        b = Board()
        b.create(Task(id="T1", status="ready", assignee="agent"))
        self.assertTrue(claim(b, "T1", "s", "o1", ttl_seconds=1))
        self.assertTrue(heartbeat(b, "T1", "s", "o1", ttl_seconds=1))
        self.assertFalse(heartbeat(b, "T1", "s", "o2", ttl_seconds=1))  # 非持租者
        b.close()


if __name__ == "__main__":
    unittest.main()
