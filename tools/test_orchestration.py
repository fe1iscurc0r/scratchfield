"""
tools/test_orchestration.py — W64-01 验收测试（≥6 用例）
验收硬线：
  1. Task DAG 依赖解析顺序正确
  2. Dispatch 可重试但不重复执行
"""
from __future__ import annotations

import pytest

from mcpserver.orchestration.core import (
    DecisionGate,
    Dispatch,
    DispatchStatus,
    GateStatus,
    MessageKind,
    Run,
    Task,
    TaskStatus,
)


class TestTaskDAG:
    """验收硬线 1：Task DAG 依赖解析顺序正确"""

    def test_linear_deps_order(self):
        """线性依赖链：A→B→C，拓扑序必须遵守。"""
        run = Run()
        task_a = run.task_create({"title": "A"}, deps=[], parent_id=None)
        task_b = run.task_create({"title": "B"}, deps=[task_a.task_id], parent_id=None)
        task_c = run.task_create({"title": "C"}, deps=[task_b.task_id], parent_id=None)

        order = run.dag_order()
        idx = {tid: order.index(tid) for tid in [task_a.task_id, task_b.task_id, task_c.task_id]}
        assert idx[task_a.task_id] < idx[task_b.task_id] < idx[task_c.task_id]

    def test_parallel_deps_order(self):
        """并行依赖：A→B, A→C, B→D, C→D，拓扑序 B/C 在 A 后，D 在 B/C 后。"""
        run = Run()
        a = run.task_create({"title": "A"}, deps=[])
        b = run.task_create({"title": "B"}, deps=[a.task_id])
        c = run.task_create({"title": "C"}, deps=[a.task_id])
        d = run.task_create({"title": "D"}, deps=[b.task_id, c.task_id])

        order = run.dag_order()
        idx = {tid: order.index(tid) for tid in [a.task_id, b.task_id, c.task_id, d.task_id]}
        assert idx[a.task_id] < idx[b.task_id]
        assert idx[a.task_id] < idx[c.task_id]
        assert idx[b.task_id] < idx[d.task_id]
        assert idx[c.task_id] < idx[d.task_id]

    def test_empty_deps_ready_immediately(self):
        """无依赖 Task 直接 READY。"""
        run = Run()
        task = run.task_create({"title": "no-deps"})
        assert task.status == TaskStatus.READY

    def test_pending_to_ready_after_deps_complete(self):
        """依赖全完成后 Task 从 PENDING → READY（Orca promoteReadyTasks 逻辑）。"""
        run = Run()
        a = run.task_create({"title": "A"}, deps=[])
        b = run.task_create({"title": "B"}, deps=[a.task_id])
        assert b.status == TaskStatus.PENDING

        run.task_update_status(a.task_id, TaskStatus.COMPLETED)
        assert b.status == TaskStatus.READY

    def test_diamond_deps(self):
        """菱形依赖：A→B, A→C, B→D, C→D。两者都在 A 后，D 在两者后。"""
        run = Run()
        a = run.task_create({"title": "A"}, deps=[])
        b = run.task_create({"title": "B"}, deps=[a.task_id])
        c = run.task_create({"title": "C"}, deps=[a.task_id])
        d = run.task_create({"title": "D"}, deps=[b.task_id, c.task_id])

        order = run.dag_order()
        idx = {tid: order.index(tid) for tid in [a.task_id, b.task_id, c.task_id, d.task_id]}
        assert idx[a.task_id] < idx[b.task_id]
        assert idx[a.task_id] < idx[c.task_id]
        # B and C relative order undefined; only both before D
        assert idx[d.task_id] > idx[b.task_id]
        assert idx[d.task_id] > idx[c.task_id]


class TestDispatch:
    """验收硬线 2：Dispatch 可重试但不重复执行"""

    def test_dispatch_single(self):
        """一次分发：Task DISPATCHED → COMPLETED。"""
        run = Run()
        task = run.task_create({"title": "job"})
        disp = run.dispatch_create(task.task_id, "agent-1")
        assert disp.status == DispatchStatus.PENDING
        assert task.status == TaskStatus.DISPATCHED

    def test_dispatch_retry_on_failure(self):
        """Dispatch 失败可重试，attempt 递增。"""
        run = Run()
        task = run.task_create({"title": "job"})
        d1 = run.dispatch_create(task.task_id, "agent-1")
        assert d1.attempt == 1

        # 模拟失败
        run.dispatch_resolve(d1.dispatch_id, DispatchStatus.FAILED, {"error": "timeout"})

        # 重试 Dispatch 已创建
        active = run.dispatch_find_active(task.task_id)
        assert active is not None
        assert active.attempt == 2

    def test_dispatch_no_duplicate_execution(self):
        """
        验收硬线：Dispatch 可重试但不重复执行。
        有 active Dispatch 时 dispatch_prevent_duplicate_execution 返回 False。
        """
        run = Run()
        task = run.task_create({"title": "job"})

        ok1 = run.dispatch_prevent_duplicate_execution(task.task_id)
        assert ok1 is True

        run.dispatch_create(task.task_id, "agent-1")

        ok2 = run.dispatch_prevent_duplicate_execution(task.task_id)
        assert ok2 is False

    def test_dispatch_circuit_break_at_max_attempts(self):
        """连续失败 max_attempts 次后熔断 CIRCUIT_BROKEN。"""
        run = Run()
        task = run.task_create({"title": "fragile"})
        task.max_attempts = 2  # 修改默认 max_attempts 以便测试

        # 第一次失败 → 重试
        d1 = run.dispatch_create(task.task_id, "agent-1")
        run.dispatch_resolve(d1.dispatch_id, DispatchStatus.FAILED)

        # 第二次失败 → 熔断
        d2 = run.dispatch_find_active(task.task_id)
        assert d2 is not None
        run.dispatch_resolve(d2.dispatch_id, DispatchStatus.FAILED)

        # 第三次不应该再创建新 Dispatch
        assert run.dispatch_find_active(task.task_id) is None
        assert task.status == TaskStatus.FAILED

    def test_dispatch_completion_blocks_further(self):
        """Dispatch COMPLETED 后不可再分发（不重复执行）。"""
        run = Run()
        task = run.task_create({"title": "done-job"})
        d1 = run.dispatch_create(task.task_id, "agent-1")
        run.dispatch_resolve(d1.dispatch_id, DispatchStatus.COMPLETED)

        assert run.dispatch_prevent_duplicate_execution(task.task_id) is False


class TestDecisionGate:
    """Decision Gate 协调者主导的阻塞式决策点"""

    def test_gate_blocks_task(self):
        """Gate 创建后关联 Task 状态为 BLOCKED。"""
        run = Run()
        task = run.task_create({"title": "wait-decision"})
        gate = run.gate_create(task.task_id, "choose path", ["A", "B"])
        assert gate.status == GateStatus.PENDING
        assert task.status == TaskStatus.BLOCKED

    def test_gate_resolve_unblocks_task(self):
        """Gate resolve 后 Task 恢复为 READY。"""
        run = Run()
        task = run.task_create({"title": "wait-decision"})
        gate = run.gate_create(task.task_id, "choose path", ["A", "B"])
        run.gate_resolve(gate.gate_id, "A")
        assert gate.status == GateStatus.RESOLVED
        assert gate.resolution == "A"
        assert task.status == TaskStatus.READY

    def test_gate_resolve_invalid_option_raises(self):
        """Gate resolve 必须从 options 中选择，否则抛 ValueError。"""
        run = Run()
        task = run.task_create({"title": "wait-decision"})
        gate = run.gate_create(task.task_id, "choose path", ["A", "B"])
        with pytest.raises(ValueError):
            run.gate_resolve(gate.gate_id, "C")  # 不在选项中


class TestMessageInbox:
    """消息收件箱（worker_done / escalation / question / heartbeat）"""

    def test_send_and_check_inbox(self):
        """发送消息并按 kind 过滤。"""
        run = Run()
        task = run.task_create({"title": "t"})
        run.send(MessageKind.WORKER_DONE, task.task_id, {"outcome": "ok"})
        run.send(MessageKind.ESCALATION, task.task_id, {"reason": "perm"})
        run.send(MessageKind.QUESTION, task.task_id, {"q": "how?"})

        all_msgs = run.check_inbox()
        assert len(all_msgs) == 3

        done = run.check_inbox(kinds=[MessageKind.WORKER_DONE])
        assert len(done) == 1
        assert done[0].kind == MessageKind.WORKER_DONE

        q = run.check_inbox(kinds=[MessageKind.QUESTION])
        assert len(q) == 1

    def test_inbox_by_task_id(self):
        """按 task_id 过滤收件箱。"""
        run = Run()
        t1 = run.task_create({"title": "t1"})
        t2 = run.task_create({"title": "t2"})
        run.send(MessageKind.WORKER_DONE, t1.task_id)
        run.send(MessageKind.WORKER_DONE, t2.task_id)

        t1_msgs = run.check_inbox(task_id=t1.task_id)
        assert len(t1_msgs) == 1
        assert t1_msgs[0].task_id == t1.task_id


class TestSerialization:
    """State 可序列化 JSON"""

    def test_run_serialize_deserialize(self):
        """Run 可 JSON 序列化/反序列化往返一致。"""
        run = Run(objective="test-obj")
        task = run.task_create({"title": "A"}, deps=[])
        run.dispatch_create(task.task_id, "agent-x")
        run.gate_create(task.task_id, "q", ["a", "b"])

        raw = run.serialize()
        restored = Run.from_dict(__import__("json").loads(raw))
        assert restored.run_id == run.run_id
        assert restored.objective == run.objective
        assert len(restored._tasks) == 1
        assert len(restored._dispatches) == 1
        assert len(restored._gates) == 1


class TestTaskStatusTransitions:
    """Task 状态机合法迁移"""

    def test_valid_transitions(self):
        """合法迁移路径：pending→ready→dispatched→completed"""
        run = Run()
        t = run.task_create({"title": "path"})  # ready (no deps)
        assert t.status == TaskStatus.READY

        d = run.dispatch_create(t.task_id, "agent-1")
        assert t.status == TaskStatus.DISPATCHED

        run.dispatch_resolve(d.dispatch_id, DispatchStatus.COMPLETED)
        assert t.status == TaskStatus.COMPLETED

    def test_failed_transition(self):
        """failed 状态可从 failed 直接结束（不重试）。"""
        run = Run()
        t = run.task_create({"title": "bad"})
        t.max_attempts = 2  # 对齐熔断语义：2 次失败后 FAILED
        d = run.dispatch_create(t.task_id, "agent-1")
        run.dispatch_resolve(d.dispatch_id, DispatchStatus.FAILED)

        active = run.dispatch_find_active(t.task_id)
        assert active is not None
        assert active.attempt == 2  # auto-retry

        d2 = active
        run.dispatch_resolve(d2.dispatch_id, DispatchStatus.FAILED)
        assert t.status == TaskStatus.FAILED