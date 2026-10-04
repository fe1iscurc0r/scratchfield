# test_event_protocol.py — NagaAgent 事件即消息协议验证用例
# W64-02 验收硬线：pytest 全绿 ≥5 用例，断言「事件序列化往返一致」「五态状态机合法迁移」

import json
import time

import pytest
from event_protocol import (
    Event,
    EventBus,
    EventConsumer,
    EventKind,
    InvalidTransitionError,
    Task,
    TaskStatus,
    WaitTimeoutError,
    create_task,
    format_event,
    get_event_bus,
    get_task,
    is_final_status,
    validate_transition,
    wait,
    wait_for_status,
    wait_until_done,
)
from event_protocol import (
    wait as wait_fn,
)

# ─────────────────────────── 测试五态状态机 ────────────────────────────

class TestTaskStatusTransitions:
    """测试五态状态机合法迁移。"""

    def test_valid_transitions(self):
        # pending → running
        validate_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        # running → done
        validate_transition(TaskStatus.RUNNING, TaskStatus.DONE)
        # running → blocked
        validate_transition(TaskStatus.RUNNING, TaskStatus.BLOCKED)
        # running → failed
        validate_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        # blocked → running
        validate_transition(TaskStatus.BLOCKED, TaskStatus.RUNNING)
        # blocked → failed
        validate_transition(TaskStatus.BLOCKED, TaskStatus.FAILED)
        # 自身到自身（幂等）
        for s in TaskStatus:
            validate_transition(s, s)

    def test_invalid_transition_pending_to_done(self):
        with pytest.raises(InvalidTransitionError, match="PENDING.*DONE"):
            validate_transition(TaskStatus.PENDING, TaskStatus.DONE)

    def test_invalid_transition_pending_to_blocked(self):
        with pytest.raises(InvalidTransitionError, match="PENDING.*BLOCKED"):
            validate_transition(TaskStatus.PENDING, TaskStatus.BLOCKED)

    def test_invalid_transition_done_to_running(self):
        with pytest.raises(InvalidTransitionError, match="DONE.*RUNNING"):
            validate_transition(TaskStatus.DONE, TaskStatus.RUNNING)

    def test_invalid_transition_failed_to_done(self):
        with pytest.raises(InvalidTransitionError, match="FAILED.*DONE"):
            validate_transition(TaskStatus.FAILED, TaskStatus.DONE)

    def test_invalid_transition_blocked_to_done(self):
        with pytest.raises(InvalidTransitionError, match="BLOCKED.*DONE"):
            validate_transition(TaskStatus.BLOCKED, TaskStatus.DONE)


class TestTaskStateMachine:
    """测试 Task 实体的五态状态机。"""

    def test_initial_state_is_pending(self):
        task = Task(task_id="t1", name="编译固件")
        assert task.status == TaskStatus.PENDING

    def test_mark_done_transitions_correctly(self):
        task = Task(task_id="t2", name="测试")
        task.transition_to(TaskStatus.RUNNING)
        evt = task.mark_done(output_inline="all tests passed")
        assert task.status == TaskStatus.DONE
        assert evt.kind == EventKind.EXEC_DONE
        assert task.output_inline == "all tests passed"

    def test_mark_failed_transitions_correctly(self):
        task = Task(task_id="t3", name="编译")
        task.transition_to(TaskStatus.RUNNING)
        evt = task.mark_failed(output_inline="compile error")
        assert task.status == TaskStatus.FAILED
        assert evt.kind == EventKind.EXEC_METRIC

    def test_block_and_unblock(self):
        task = Task(task_id="t4", name="等待审批")
        task.transition_to(TaskStatus.RUNNING)
        assert task.status == TaskStatus.RUNNING
        evt = task.block(reason="需要人工审批")
        assert task.status == TaskStatus.BLOCKED
        assert evt.kind == EventKind.EXEC_BLOCKED
        assert evt.metadata["block_reason"] == "需要人工审批"
        evt2 = task.unblock()
        assert task.status == TaskStatus.RUNNING
        assert evt2.kind == EventKind.TASK_SPAWN

    def test_cannot_transition_from_done(self):
        task = Task(task_id="t5", name="done task")
        task.transition_to(TaskStatus.RUNNING)
        task.mark_done()
        with pytest.raises(InvalidTransitionError):
            task.transition_to(TaskStatus.RUNNING)

    def test_cannot_transition_from_failed(self):
        task = Task(task_id="t6", name="failed task")
        task.transition_to(TaskStatus.RUNNING)
        task.mark_failed()
        with pytest.raises(InvalidTransitionError):
            task.transition_to(TaskStatus.RUNNING)

    def test_illegal_transition_raises(self):
        task = Task(task_id="t7", name="illegal")
        with pytest.raises(InvalidTransitionError):
            task.transition_to(TaskStatus.DONE)  # pending → done 非法


class TestIsFinalStatus:
    """测试终态判断。"""

    def test_done_is_final(self):
        assert is_final_status(TaskStatus.DONE) is True

    def test_failed_is_final(self):
        assert is_final_status(TaskStatus.FAILED) is True

    def test_pending_not_final(self):
        assert is_final_status(TaskStatus.PENDING) is False

    def test_running_not_final(self):
        assert is_final_status(TaskStatus.RUNNING) is False

    def test_blocked_not_final(self):
        assert is_final_status(TaskStatus.BLOCKED) is False


# ─────────────────────────── 测试事件序列化往返一致 ────────────────────────────

class TestEventSerialization:
    """测试事件序列化/反序列化往返一致（验收硬线）。"""

    def test_event_to_dict_and_back(self):
        evt = Event(
            task_id="t1",
            kind=EventKind.EXEC_DONE,
            status=TaskStatus.DONE,
            output_ref="/tmp/output.txt",
            output_inline="42 items processed",
            sig="abc123",
            created_at=1234567890.0,
            prev_sig="prev000",
            metadata={"cpu_ms": 150},
        )
        d = evt.to_dict()
        restored = Event.from_dict(d)
        assert restored.task_id == evt.task_id
        assert restored.kind == evt.kind
        assert restored.status == evt.status
        assert restored.output_ref == evt.output_ref
        assert restored.output_inline == evt.output_inline
        assert restored.sig == evt.sig
        assert restored.created_at == evt.created_at
        assert restored.prev_sig == evt.prev_sig
        assert restored.metadata == evt.metadata

    def test_event_to_json_and_back(self):
        evt = Event(
            task_id="t2",
            kind=EventKind.EXEC_BLOCKED,
            status=TaskStatus.BLOCKED,
            output_ref="",
            output_inline="waiting for gate",
            metadata={"gate_id": "g1"},
        )
        json_str = evt.to_json()
        d = json.loads(json_str)
        restored = Event.from_dict(d)
        assert restored.task_id == "t2"
        assert restored.kind == EventKind.EXEC_BLOCKED
        assert restored.status == TaskStatus.BLOCKED

    def test_multiple_events_serialization_roundtrip(self):
        events = [
            Event(
                task_id="t3",
                kind=EventKind.TASK_SPAWN,
                status=TaskStatus.RUNNING,
                output_ref="",
                output_inline="started",
            ),
            Event(
                task_id="t3",
                kind=EventKind.EXEC_DONE,
                status=TaskStatus.DONE,
                output_ref="/tmp/t3.out",
                output_inline="",
            ),
        ]
        for evt in events:
            d = evt.to_dict()
            restored = Event.from_dict(d)
            assert restored.task_id == evt.task_id
            assert restored.kind == evt.kind
            assert restored.status == evt.status

    def test_empty_metadata_roundtrip(self):
        evt = Event(
            task_id="t4",
            kind=EventKind.EXEC_METRIC,
            status=TaskStatus.RUNNING,
        )
        d = evt.to_dict()
        restored = Event.from_dict(d)
        assert restored.metadata == {}

    def test_event_sig_sign_and_verify(self):
        evt = Event(
            task_id="t5",
            kind=EventKind.EXEC_DONE,
            status=TaskStatus.DONE,
            output_ref="/tmp/out.txt",
        )
        evt.sign()
        assert evt.sig != ""
        assert evt.verify() is True

    def test_event_hash_chain_integrity(self):
        evt1 = Event(
            task_id="t6",
            kind=EventKind.TASK_SPAWN,
            status=TaskStatus.RUNNING,
        ).sign()

        evt2 = Event(
            task_id="t6",
            kind=EventKind.EXEC_DONE,
            status=TaskStatus.DONE,
        ).sign(prev_sig=evt1.sig)

        assert evt2.prev_sig == evt1.sig
        assert evt1.verify() is True
        assert evt2.verify() is True

    def test_event_verify_fails_on_tamper(self):
        evt = Event(
            task_id="t7",
            kind=EventKind.EXEC_DONE,
            status=TaskStatus.DONE,
            output_ref="/tmp/out.txt",
        )
        evt.sign()
        # 篡改内容
        evt.output_ref = "/tmp/tampered.txt"
        assert evt.verify() is False


# ─────────────────────────── 测试事件流与 EventBus ────────────────────────────

class TestEventBus:
    """测试事件总线与消费者。"""

    def test_create_task_on_bus(self):
        bus = EventBus()
        task = bus.create_task("t1", "编译固件")
        assert task.task_id == "t1"
        assert bus.task_count() == 1

    def test_create_duplicate_raises(self):
        bus = EventBus()
        bus.create_task("t1", "task 1")
        with pytest.raises(ValueError, match="already exists"):
            bus.create_task("t1", "task 1 again")

    def test_get_task(self):
        bus = EventBus()
        bus.create_task("t2", "测试任务")
        retrieved = bus.get_task("t2")
        assert retrieved is not None
        assert retrieved.name == "测试任务"

    def test_get_nonexistent_task(self):
        bus = EventBus()
        assert bus.get_task("nonexistent") is None

    def test_consumer_receives_events(self):
        bus = EventBus()
        received = []

        class Collector(EventConsumer):
            def __init__(self, store):
                self._store = store

            def _dispatch(self, event):
                self._store.append(event)

        collector = Collector(received)
        bus.register_consumer(collector)
        task = bus.create_task("t3", "consumer test")
        task.mark_done()

        assert len(received) == 2  # running + done
        assert received[-1].kind == EventKind.EXEC_DONE

    def test_all_tasks(self):
        bus = EventBus()
        bus.create_task("t4", "task 4")
        bus.create_task("t5", "task 5")
        all_t = bus.all_tasks()
        assert len(all_t) == 2

    def test_task_audit_chain(self):
        bus = EventBus()
        task = bus.create_task("t6", "audit test")
        # create_task 已发出 TASK_SPAWN 事件并置为 RUNNING
        # 再执行 done
        task.mark_done()
        chain = task.get_audit_chain()
        # chain = [spawn(RUNNING), done(DONE)]
        assert len(chain) == 2


class TestGlobalBus:
    """测试全局事件总线单例。"""

    def test_global_bus_singleton(self):
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_create_task_global(self):
        bus = get_event_bus()
        bus._tasks.clear()
        task = create_task("gt1", "global task")
        assert task.task_id == "gt1"

    def test_get_task_global(self):
        bus = get_event_bus()
        bus._tasks.clear()
        create_task("gt2", "another global task")
        retrieved = get_task("gt2")
        assert retrieved is not None


# ─────────────────────────── 测试 wait 原语 ────────────────────────────

class TestWaitPrimitive:
    """测试 wait 原语（herdr wait/prompt 思路）。"""

    def test_wait_returns_true_when_condition_met(self):
        flag = False

        def setter():
            nonlocal flag
            flag = True
            return True

        result = wait("test wait", setter, timeout=2.0)
        assert result is True

    def test_wait_returns_false_on_timeout(self):
        counter = 0

        def never_true():
            nonlocal counter
            counter += 1
            return False

        result = wait("never met", never_true, timeout=0.3, poll_interval=0.05)
        assert result is False
        assert counter >= 3  # 至少轮询了 3 次

    def test_wait_with_poll_interval(self):
        counter = 0

        def increment():
            nonlocal counter
            counter += 1
            return counter >= 3

        result = wait("increment test", increment, timeout=1.0, poll_interval=0.05)
        assert result is True
        assert counter == 3

    def test_wait_for_status_success(self):
        task = Task("wt1", "wait test")
        task.transition_to(TaskStatus.RUNNING)

        def make_done():
            task.mark_done()
            return True

        result = wait("set done", make_done, timeout=1.0)
        assert result is True

        status = wait_for_status(task, [TaskStatus.DONE], timeout=1.0)
        assert status == TaskStatus.DONE

    def test_wait_for_status_timeout(self):
        task = Task("wt2", "wait timeout test")
        task.transition_to(TaskStatus.RUNNING)
        with pytest.raises(WaitTimeoutError):
            wait_for_status(task, [TaskStatus.DONE], timeout=0.2)

    def test_wait_until_done_success(self):
        task = Task("wt3", "until done test")
        task.transition_to(TaskStatus.RUNNING)
        task.mark_done()
        status = wait_until_done(task, timeout=1.0)
        assert status == TaskStatus.DONE


class TestWaitIntegration:
    """集成测试：wait 原语 + 五态状态机联动。"""

    def test_wait_for_blocked_then_unblocked(self):
        task = Task("wi1", "block/unblock test")
        task.transition_to(TaskStatus.RUNNING)
        task.block(reason="waiting approval")

        def check_blocked():
            return task.status == TaskStatus.BLOCKED

        ok = wait("check blocked", check_blocked, timeout=1.0)
        assert ok is True

        task.unblock()
        assert task.status == TaskStatus.RUNNING

    def test_consumer_receives_blocked_event(self):
        bus = EventBus()
        events = []

        class Collector(EventConsumer):
            def _dispatch(self, event):
                events.append(event)

        collector = Collector()
        bus.register_consumer(collector)
        task = bus.create_task("wi2", "block event test")
        task.transition_to(TaskStatus.RUNNING)
        task.block(reason="need approval")

        blocked_evts = [e for e in events if e.kind == EventKind.EXEC_BLOCKED]
        assert len(blocked_evts) == 1
        assert blocked_evts[0].metadata["block_reason"] == "need approval"


# ─────────────────────────── 测试 format_event ────────────────────────────

class TestFormatEvent:
    """测试人类可读事件格式化。"""

    def test_format_event_basic(self):
        evt = Event(
            task_id="t1",
            kind=EventKind.EXEC_DONE,
            status=TaskStatus.DONE,
            output_ref="/tmp/out.txt",
        )
        evt.sign()
        formatted = format_event(evt)
        assert "EXEC_DONE" in formatted
        assert "t1" in formatted
        assert "DONE" in formatted
        assert "/tmp/out.txt" in formatted
        assert len(evt.sig) >= 8
