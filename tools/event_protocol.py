# event_protocol.py — NagaAgent 事件即消息协议
# 参考: block/buzz (Apache-2.0) 事件协议字段 + herdrdev/herdr (Apache-2.0) 五态状态机
# 引用来源: buzz-herdr-消息与运行时-授粉报告.md §四建议1/2

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

# ─────────────────────────── 事件类型与状态 ────────────────────────────

class TaskStatus(Enum):
    """
    五态状态机（对齐 herdr 五态 + buzz 审计链）。
    状态迁移规则:
        pending → running
        running → blocked / done / failed
        blocked → running / failed
        done    → (终态)
        failed  → (终态)
    """
    PENDING = auto()   # 任务已创建，未开始执行
    RUNNING = auto()   # 执行中
    BLOCKED = auto()   # 等待审批/决策/外部输入（对应 herdr blocked）
    DONE = auto()      # 执行完成且正常
    FAILED = auto()    # 执行失败/被拒绝


class EventKind(Enum):
    """
    事件 kind 注册表（对齐 buzz kind 体系）。
    保留 40000+ 段为本仓自定义事件。
    """
    EXEC_DONE = auto()       # 任务执行完成
    EXEC_BLOCKED = auto()    # 任务执行被阻塞（等待审批）
    EXEC_METRIC = auto()     # 执行度量事件（token/cost 等）
    GATE_REQUEST = auto()    # 硬门控申请事件
    GATE_RESOLVED = auto()   # 硬门控审批完成事件
    TASK_SPAWN = auto()      # 任务创建事件


@dataclass
class Event:
    """
    结构化事件（NagaAgent → Hermes 决策层的消息协议）。

    字段设计参考 buzz Nostr 事件 envelope：
    - task_id: 任务唯一标识（≈ Nostr #e 引用）
    - kind: 事件类型（EXEC_DONE / EXEC_BLOCKED / EXEC_METRIC 等）
    - status: 任务当时状态
    - output_ref: 执行输出引用（可为空，表示 inline output）
    - sig: 事件签名（简化版：sha256 哈希链）
    """
    task_id: str
    kind: EventKind
    status: TaskStatus
    output_ref: str = ""          # 输出引用（如文件路径、存储 key）
    output_inline: str = ""       # inline 输出（短结果直接内嵌）
    sig: str = ""                 # 签名/哈希（留接口）
    created_at: float = field(default_factory=time.time)
    prev_sig: str = ""            # 前序事件 sig（哈希链）
    metadata: dict = field(default_factory=dict)

    # ── 序列化 ────────────────────────────────────────────────────────

    def to_json(self) -> str:
        return json.dumps(self._serializable(), ensure_ascii=False, sort_keys=True)

    def to_dict(self) -> dict:
        return self._serializable()

    def _serializable(self) -> dict:
        return {
            "task_id": self.task_id,
            "kind": self.kind.name,
            "status": self.status.name,
            "output_ref": self.output_ref,
            "output_inline": self.output_inline,
            "sig": self.sig,
            "created_at": self.created_at,
            "prev_sig": self.prev_sig,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            task_id=d["task_id"],
            kind=EventKind[d["kind"]],
            status=TaskStatus[d["status"]],
            output_ref=d.get("output_ref", ""),
            output_inline=d.get("output_inline", ""),
            sig=d.get("sig", ""),
            created_at=d.get("created_at", time.time()),
            prev_sig=d.get("prev_sig", ""),
            metadata=d.get("metadata", {}),
        )

    # ── 哈希链签名（简化版，buzz-audit 思路）──────────────────────────

    def sign(self, prev_sig: str = "") -> "Event":
        """
        用 SHA-256 生成事件签名并链接到哈希链。
        实际生产应替换为 Ed25519 / Schnorr 签名。
        """
        self.prev_sig = prev_sig
        payload = (
            f"{self.task_id}:{self.kind.name}:{self.status.name}:"
            f"{self.output_ref}:{self.created_at}:{prev_sig}"
        )
        self.sig = hashlib.sha256(payload.encode()).hexdigest()[:32]
        return self

    def verify(self) -> bool:
        """验证事件签名完整性。"""
        if not self.sig:
            return False
        payload = (
            f"{self.task_id}:{self.kind.name}:{self.status.name}:"
            f"{self.output_ref}:{self.created_at}:{self.prev_sig}"
        )
        expected = hashlib.sha256(payload.encode()).hexdigest()[:32]
        return self.sig == expected


# ─────────────────────────── 五态状态机 ────────────────────────────

# 合法的状态迁移映射
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING:  {TaskStatus.RUNNING},
    TaskStatus.RUNNING:  {TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.FAILED},
    TaskStatus.BLOCKED:  {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.DONE:     set(),   # 终态
    TaskStatus.FAILED:   set(),   # 终态
}


class InvalidTransitionError(ValueError):
    """非法状态迁移时抛出。"""
    pass


def validate_transition(from_s: TaskStatus, to_s: TaskStatus) -> None:
    """验证状态迁移合法性，非法则抛出 InvalidTransitionError。"""
    if from_s == to_s:
        return  # 自身到自身视为合法（幂等）
    if to_s not in _VALID_TRANSITIONS.get(from_s, set()):
        raise InvalidTransitionError(
            f"Invalid transition: {from_s.name} → {to_s.name}"
        )


# ─────────────────────────── Task 实体 ────────────────────────────

@dataclass
class Task:
    """
    带五态状态机的任务对象。
    状态迁移统一经 validate_transition 校验。
    """
    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    output_ref: str = ""
    output_inline: str = ""
    events: list[Event] = field(default_factory=list)   # 事件流（可被决策层消费）
    metadata: dict = field(default_factory=dict)

    # 内部 sig 游标（哈希链追踪）
    _last_sig: str = ""

    def _append_event(self, kind: EventKind, status: TaskStatus,
                      output_ref: str = "", output_inline: str = "",
                      metadata: dict | None = None) -> Event:
        """创建并追加事件到事件流。"""
        evt = Event(
            task_id=self.task_id,
            kind=kind,
            status=status,
            output_ref=output_ref,
            output_inline=output_inline,
            metadata=metadata or {},
        ).sign(prev_sig=self._last_sig)

        self._last_sig = evt.sig
        self.events.append(evt)
        return evt

    def transition_to(self, new_status: TaskStatus,
                      output_ref: str = "", output_inline: str = "",
                      metadata: dict | None = None) -> Event:
        """
        执行状态迁移，自动追加事件到事件流。
        迁移经五态机校验，非法迁移抛出 InvalidTransitionError。
        """
        validate_transition(self.status, new_status)

        kind_map = {
            (TaskStatus.PENDING,  TaskStatus.RUNNING):  EventKind.TASK_SPAWN,
            (TaskStatus.RUNNING,  TaskStatus.DONE):     EventKind.EXEC_DONE,
            (TaskStatus.RUNNING,  TaskStatus.FAILED):   EventKind.EXEC_METRIC,
            (TaskStatus.RUNNING,  TaskStatus.BLOCKED):  EventKind.EXEC_BLOCKED,
            (TaskStatus.BLOCKED,  TaskStatus.RUNNING):  EventKind.TASK_SPAWN,
            (TaskStatus.BLOCKED,  TaskStatus.FAILED):   EventKind.EXEC_METRIC,
        }
        kind = kind_map.get((self.status, new_status), EventKind.EXEC_METRIC)

        evt = self._append_event(
            kind=kind,
            status=new_status,
            output_ref=output_ref,
            output_inline=output_inline,
            metadata=metadata,
        )
        self.status = new_status

        if output_ref:
            self.output_ref = output_ref
        if output_inline:
            self.output_inline = output_inline

        return evt

    def mark_done(self, output_ref: str = "", output_inline: str = "") -> Event:
        return self.transition_to(TaskStatus.DONE, output_ref, output_inline)

    def mark_failed(self, output_ref: str = "", output_inline: str = "",
                    metadata: dict | None = None) -> Event:
        return self.transition_to(
            TaskStatus.FAILED, output_ref, output_inline, metadata
        )

    def block(self, reason: str = "") -> Event:
        return self.transition_to(
            TaskStatus.BLOCKED,
            metadata={"block_reason": reason},
        )

    def unblock(self) -> Event:
        return self.transition_to(TaskStatus.RUNNING)

    def get_audit_chain(self) -> list[str]:
        """返回哈希链完整 sig 列表（用于审计追溯）。"""
        return [e.sig for e in self.events if e.sig]

    def get_latest_event(self) -> Event | None:
        return self.events[-1] if self.events else None


# ─────────────────────────── wait 原语（herdr wait/prompt 思路）────────────────

class WaitTimeoutError(TimeoutError):
    """wait 原语超时。"""
    pass


class WaitConditionMetError(Exception):
    """wait 条件已满足（内部用）。"""
    pass


def wait(
    prompt: str,
    until: Callable[[], bool],
    timeout: float = 30.0,
    poll_interval: float = 0.1,
) -> bool:
    """
    等待 until() 返回 True，或超时返回 False。
    对应 herdr agent.wait {until, timeout_ms} 原语。

    参数:
        prompt: 等待说明（用于日志）
        until: 条件回调（返回 True 表示条件满足）
        timeout: 超时秒数（默认 30s）
        poll_interval: 轮询间隔秒数（默认 0.1s）

    返回:
        True  if 条件在 timeout 内满足
        False if 超时

    用法示例:
        task = Task("t1", "编译固件")
        task.block("等待审批")
        ok = wait("等待审批通过", lambda: gate.check_gate(...) == GateDecision.APPROVED, timeout=60)
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if until():
                return True
        except WaitConditionMetError:
            return True
        time.sleep(poll_interval)
    return False


def wait_for_status(
    task: Task,
    target_statuses: list[TaskStatus],
    timeout: float = 30.0,
) -> TaskStatus:
    """
    等待 task 进入目标状态之一。
    超时抛出 WaitTimeoutError。
    """
    def _check() -> bool:
        return task.status in target_statuses

    ok = wait(f"等待 task={task.task_id} 进入 {target_statuses}", _check, timeout=timeout)
    if not ok:
        raise WaitTimeoutError(
            f"等待超时: task={task.task_id} 在 {timeout}s 内未进入 {[s.name for s in target_statuses]}，"
            f"当前状态={task.status.name}"
        )
    return task.status


def wait_until_done(task: Task, timeout: float = 60.0) -> TaskStatus:
    """
    等待 task 进入终态（done / failed）。
    超时抛出 WaitTimeoutError。
    """
    return wait_for_status(task, [TaskStatus.DONE, TaskStatus.FAILED], timeout=timeout)


# ─────────────────────────── 事件流消费者接口 ────────────────────────────

class EventConsumer:
    """
    事件流消费者（对接 Hermes 决策层）。
    注册回调，每次 Task 状态迁移时自动推送事件。
    """

    def __init__(self):
        self._handlers: list[Callable[[Event], None]] = []

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        self._handlers.append(handler)

    def _dispatch(self, event: Event) -> None:
        for h in self._handlers:
            try:
                h(event)
            except Exception:
                pass  # 不因单个消费者异常中断其他消费者

    def clear(self) -> None:
        self._handlers.clear()


# ─────────────────────────── 全局事件总线 ────────────────────────────

class EventBus:
    """
    任务事件总线（单例）。
    所有 Task 的事件流通过 EventBus 广播给注册的消费者。
    """

    def __init__(self):
        self._consumers: list[EventConsumer] = []
        self._tasks: dict[str, Task] = {}

    def register_consumer(self, consumer: EventConsumer) -> None:
        self._consumers.append(consumer)

    def create_task(self, task_id: str, name: str,
                    metadata: dict | None = None) -> Task:
        """创建任务并注册到总线。"""
        if task_id in self._tasks:
            raise ValueError(f"Task {task_id} already exists")
        task = Task(task_id=task_id, name=name, metadata=metadata or {})

        # 拦截 transition_to，自动分发事件
        original_transition = task.transition_to

        def _wrapped_transition(new_status: TaskStatus,
                                output_ref: str = "", output_inline: str = "",
                                metadata: dict | None = None) -> Event:
            evt = original_transition(new_status, output_ref, output_inline, metadata)
            for c in self._consumers:
                c._dispatch(evt)
            return evt

        task.transition_to = _wrapped_transition  # type: ignore[assignment]
        self._tasks[task_id] = task

        # 发出 TASK_SPAWN 事件（对应 pending→running 的迁移）
        spawn_evt = task._append_event(
            kind=EventKind.TASK_SPAWN,
            status=TaskStatus.RUNNING,
            output_inline="task spawned",
            metadata={},
        )
        task.status = TaskStatus.RUNNING
        for c in self._consumers:
            c._dispatch(spawn_evt)

        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def task_count(self) -> int:
        return len(self._tasks)


# ─────────────────────────── 全局单例 ────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def create_task(task_id: str, name: str,
                metadata: dict | None = None) -> Task:
    return get_event_bus().create_task(task_id, name, metadata)


def get_task(task_id: str) -> Task | None:
    return get_event_bus().get_task(task_id)


# ─────────────────────────── 工具函数 ────────────────────────────

def is_final_status(status: TaskStatus) -> bool:
    """判断状态是否为终态。"""
    return status in (TaskStatus.DONE, TaskStatus.FAILED)


def format_event(event: Event) -> str:
    """人类可读的事件描述。"""
    return (
        f"[{event.kind.name}] task={event.task_id} "
        f"status={event.status.name} output_ref={event.output_ref!r} "
        f"sig={event.sig[:8]}..."
    )