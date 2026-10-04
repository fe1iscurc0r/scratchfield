"""
mcpserver/orchestration/core.py — Orca 三层编排原型（纯 Python，MIT 参考设计）

参考来源：stablyai/orca（MIT）并行舰队编排架构
  - Run    = 协调者命名空间 + 消息收件箱
  - Task   = 工作项，deps DAG + parent 父子链，状态机 pending/ready/dispatched/completed/failed/blocked
  - Dispatch = Task → Agent Terminal 一次性绑定（可重试，不可并发）
  - Decision Gate = 协调者主导的阻塞式决策点

【参考实现边界】
  本模块提取 Orca 设计思路独立实现，未使用任何 orca 源码。
  Orca 原型使用 TypeScript + SQLite；本模块使用纯 Python + 内存/JSON 序列化。
"""

from __future__ import annotations

import enum
import json
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, enum.Enum):
    """Task 生命周期状态，映射 Orca 状态机。"""
    PENDING    = "pending"     # 等待依赖完成
    READY      = "ready"       # 依赖全满足，可分发
    DISPATCHED = "dispatched"  # 已分配给 Agent Terminal
    COMPLETED  = "completed"   # 正常结束
    FAILED     = "failed"      # 异常结束
    BLOCKED    = "blocked"     # 被 Decision Gate 阻塞


class DispatchStatus(str, enum.Enum):
    """Dispatch 生命周期状态。"""
    PENDING        = "pending"
    DISPATCHED     = "dispatched"
    COMPLETED      = "completed"
    FAILED         = "failed"
    CIRCUIT_BROKEN = "circuit_broken"  # 熔断（连续失败 N 次）


class GateStatus(str, enum.Enum):
    """Decision Gate 状态。"""
    PENDING   = "pending"
    RESOLVED  = "resolved"
    TIMEOUT   = "timeout"


class MessageKind(str, enum.Enum):
    """Orca 消息收件箱类型。"""
    WORKER_DONE    = "worker_done"
    ESCALATION     = "escalation"
    QUESTION       = "question"
    HEARTBEAT      = "heartbeat"
    DECISION_GATE  = "decision_gate"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """
    工作项，对应 Orca Task。

    Attributes:
        task_id: 全局唯一标识
        spec: 任务描述（可序列化任意对象）
        deps: 依赖 Task ID 列表（DAG 边）
        parent_id: 父任务 ID（父子链）
        status: 当前状态
        result: 执行结果（任务完成后填充）
        created_at: 创建时间戳
        updated_at: 更新时间戳
    """
    task_id: str
    spec: dict[str, Any]
    deps: list[str] = field(default_factory=list)
    parent_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Task":
        d = dict(d)
        d["status"] = TaskStatus(d.pop("status"))
        return cls(**d)

    def advance_time(self):
        self.updated_at = time.time()


@dataclass
class Dispatch:
    """
    Task → Agent Terminal 的一次性分配，对应 Orca Dispatch。

    Attributes:
        dispatch_id: 全局唯一标识
        task_id: 关联 Task ID
        agent_id: Agent Terminal 标识
        attempt: 第几次尝试（可重试）
        status: 当前状态
        max_attempts: 最大重试次数（默认 3）
        result: 执行结果
        created_at: 创建时间戳
        updated_at: 更新时间戳
    """
    dispatch_id: str
    task_id: str
    agent_id: str
    attempt: int = 1
    status: DispatchStatus = DispatchStatus.PENDING
    max_attempts: int = 3
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Dispatch":
        d = dict(d)
        d["status"] = DispatchStatus(d.pop("status"))
        return cls(**d)

    def can_retry(self) -> bool:
        """可重试但不可超过 max_attempts，且当前不是 circuit_broken。"""
        return (
            self.status not in (DispatchStatus.CIRCUIT_BROKEN, DispatchStatus.COMPLETED)
            and self.attempt < self.max_attempts
        )

    def advance_time(self):
        self.updated_at = time.time()


@dataclass
class DecisionGate:
    """
    协调者主导的阻塞式决策点，对应 Orca gate-create。

    Attributes:
        gate_id: 全局唯一标识
        task_id: 关联 Task ID（Gate 挂在哪个 Task 上）
        question: 决策问题描述
        options: 可选决策列表
        status: 当前状态
        resolution: 决策结果（resolved 后填充）
        created_at: 创建时间戳
        resolved_at: 解决时间戳（可选）
    """
    gate_id: str
    task_id: str
    question: str
    options: list[str]
    status: GateStatus = GateStatus.PENDING
    resolution: str | None = None
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DecisionGate":
        d = dict(d)
        d["status"] = GateStatus(d.pop("status"))
        return cls(**d)


@dataclass
class Message:
    """
    Orca 消息收件箱条目。
    4 种消息类型：worker_done / escalation / question / heartbeat / decision_gate
    """
    msg_id: str
    kind: MessageKind
    task_id: str
    payload: dict[str, Any]
    dispatch_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Message":
        d = dict(d)
        d["kind"] = MessageKind(d.pop("kind"))
        return cls(**d)


# ---------------------------------------------------------------------------
# Run（协调者命名空间 + 消息收件箱）
# ---------------------------------------------------------------------------

class Run:
    """
    协调者命名空间，对应 Orca Run。
    管理所有 Task、Dispatch、Decision Gate 实例，以及消息收件箱。
    """

    def __init__(self, run_id: str | None = None, objective: str = ""):
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.objective = objective
        self._tasks: dict[str, Task] = {}
        self._dispatches: dict[str, Dispatch] = {}
        self._gates: dict[str, DecisionGate] = {}
        self._inbox: list[Message] = []
        # 加速查找索引
        self._task_children: dict[str, list[str]] = defaultdict(list)  # parent_id → [child_id]

    # ---- 消息收件箱 ----

    def send(self, kind: MessageKind, task_id: str,
             payload: dict[str, Any] | None = None,
             dispatch_id: str | None = None) -> Message:
        """发送一条消息到收件箱。"""
        msg = Message(
            msg_id=str(uuid.uuid4()),
            kind=kind,
            task_id=task_id,
            payload=payload or {},
            dispatch_id=dispatch_id,
        )
        self._inbox.append(msg)
        return msg

    def check_inbox(self, kinds: list[MessageKind] | None = None,
                    task_id: str | None = None) -> list[Message]:
        """按类型和/或 task_id 过滤收件箱消息。"""
        results = self._inbox
        if kinds:
            results = [m for m in results if m.kind in kinds]
        if task_id:
            results = [m for m in results if m.task_id == task_id]
        return results

    def clear_inbox(self):
        """清空收件箱（可选，用于长任务清理）。"""
        self._inbox.clear()

    # ---- Task CRUD ----

    def task_create(self, spec: dict[str, Any],
                    deps: list[str] | None = None,
                    parent_id: str | None = None) -> Task:
        """创建一个 Task，自动维护父子链与初始状态。"""
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            spec=spec,
            deps=deps or [],
            parent_id=parent_id,
            status=TaskStatus.PENDING,
        )
        self._tasks[task.task_id] = task
        if parent_id:
            self._task_children[parent_id].append(task.task_id)
        # 依赖为空 → 直接就绪
        if not task.deps:
            task.status = TaskStatus.READY
        return task

    def task_get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def task_update_status(self, task_id: str, status: TaskStatus,
                           result: dict[str, Any] | None = None):
        """更新 Task 状态，推进 DAG。"""
        task = self._tasks[task_id]
        task.status = status
        if result is not None:
            task.result = result
        task.advance_time()
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            self._promote_ready_tasks()

    def _promote_ready_tasks(self):
        """
        扫描所有 PENDING Task，当 deps 全 completed 时推进到 READY。
        这是 Orca promoteReadyTasks 的核心逻辑。
        """
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            if not task.deps:
                task.status = TaskStatus.READY
                task.advance_time()
                continue
            all_deps_done = all(
                self._tasks.get(dep_id, None) is not None
                and self._tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.deps
            )
            if all_deps_done:
                task.status = TaskStatus.READY
                task.advance_time()

    def task_list(self, status: TaskStatus | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def dag_order(self) -> list[str]:
        """
        返回 DAG 的拓扑排序（Kahn 算法）。
        验收硬线：「Task DAG 依赖解析顺序正确」
        """
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for task_id, task in self._tasks.items():
            if task_id not in in_degree:
                in_degree[task_id] = 0
            for dep in task.deps:
                adj[dep].append(task_id)
                in_degree[task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            tid = queue.pop(0)
            order.append(tid)
            for nxt in adj[tid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        # 若有环，返回部分顺序（不抛异常，调用方自行判断）
        return order

    # ---- Dispatch ----

    def dispatch_create(self, task_id: str, agent_id: str,
                        attempt: int = 1) -> Dispatch:
        """
        为 Task 创建一次 Dispatch（一次性绑定可重试）。
        验收硬线：「Dispatch 可重试但不重复执行」
        attempt 用于重试计数：重试时传入旧 dispatch.attempt + 1。
        """
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        dispatch = Dispatch(
            dispatch_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            agent_id=agent_id,
            attempt=attempt,
            max_attempts=task.max_attempts,
        )
        self._dispatches[dispatch.dispatch_id] = dispatch

        # Task 状态推进到 DISPATCHED（若尚非 BLOCKED）
        if task.status not in (TaskStatus.BLOCKED, TaskStatus.DISPATCHED,
                               TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.status = TaskStatus.DISPATCHED
            task.advance_time()

        return dispatch

    def dispatch_get(self, dispatch_id: str) -> Dispatch | None:
        return self._dispatches.get(dispatch_id)

    def dispatch_resolve(self, dispatch_id: str, status: DispatchStatus,
                         result: dict[str, Any] | None = None):
        """
        解决一次 Dispatch（成功/失败）。
        失败且可重试 → 创建新 Dispatch（同一 task_id，不同 agent_id）；
        失败且达熔断阈值 → 标记 CIRCUIT_BROKEN，不重试。
        """
        dispatch = self._dispatches[dispatch_id]
        dispatch.status = status
        dispatch.result = result
        dispatch.advance_time()

        task = self._tasks[dispatch.task_id]
        if status == DispatchStatus.COMPLETED:
            self.task_update_status(dispatch.task_id, TaskStatus.COMPLETED, result)
        elif status == DispatchStatus.FAILED:
            if dispatch.can_retry():
                # 重试：生成新 Dispatch（同一 Task），attempt 继承 +1
                self._dispatches[dispatch.dispatch_id]  # keep old for audit
                self.dispatch_create(dispatch.task_id, dispatch.agent_id,
                                     attempt=dispatch.attempt + 1)
            else:
                # 熔断
                dispatch.status = DispatchStatus.CIRCUIT_BROKEN
                self.task_update_status(dispatch.task_id, TaskStatus.FAILED, result)
        elif status == DispatchStatus.CIRCUIT_BROKEN:
            self.task_update_status(dispatch.task_id, TaskStatus.FAILED, result)

    def dispatch_find_active(self, task_id: str) -> Dispatch | None:
        """查找某 Task 当前有效的（pending/dispatched）Dispatch。"""
        for d in self._dispatches.values():
            if d.task_id == task_id and d.status in (
                    DispatchStatus.PENDING, DispatchStatus.DISPATCHED):
                return d
        return None

    def dispatch_prevent_duplicate_execution(self, task_id: str) -> bool:
        """
        验收硬线：Dispatch 可重试但不重复执行。
        若存在 active Dispatch 或 Task 已终态（completed/failed/blocked），
        返回 False（不可再次分发）。
        """
        task = self._tasks.get(task_id)
        if task is None:
            return True  # 未知 task，允许创建（由 task_create 兜底）
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                           TaskStatus.BLOCKED):
            return False  # 已终态，不再分发
        return self.dispatch_find_active(task_id) is None

    # ---- Decision Gate ----

    def gate_create(self, task_id: str, question: str,
                    options: list[str]) -> DecisionGate:
        """创建 Decision Gate（协调者主导的阻塞式决策点）。"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        gate = DecisionGate(
            gate_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            question=question,
            options=options,
        )
        self._gates[gate.gate_id] = gate

        # 关联 Task 标记为 BLOCKED
        task.status = TaskStatus.BLOCKED
        task.advance_time()
        return gate

    def gate_get(self, gate_id: str) -> DecisionGate | None:
        return self._gates.get(gate_id)

    def gate_resolve(self, gate_id: str, resolution: str):
        """解决 Decision Gate（必须从 options 中选）。"""
        gate = self._gates[gate_id]
        if gate.status != GateStatus.PENDING:
            raise ValueError(f"Gate {gate_id} is not pending")
        if resolution not in gate.options:
            raise ValueError(f"Resolution '{resolution}' not in options: {gate.options}")

        gate.status = GateStatus.RESOLVED
        gate.resolution = resolution
        gate.resolved_at = time.time()

        # 关联 Task 解除 BLOCKED → READY（可重新分发）
        task = self._tasks[gate.task_id]
        task.status = TaskStatus.READY
        task.advance_time()

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
            "dispatches": {did: d.to_dict() for did, d in self._dispatches.items()},
            "gates": {gid: g.to_dict() for gid, g in self._gates.items()},
            "inbox": [m.to_dict() for m in self._inbox],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Run":
        run = cls(run_id=d["run_id"], objective=d.get("objective", ""))
        for tid, td in d.get("tasks", {}).items():
            run._tasks[tid] = Task.from_dict(td)
        for did, dd in d.get("dispatches", {}).items():
            run._dispatches[did] = Dispatch.from_dict(dd)
        for gid, gd in d.get("gates", {}).items():
            run._gates[gid] = DecisionGate.from_dict(gd)
        for md in d.get("inbox", []):
            run._inbox.append(Message.from_dict(md))
        for task in run._tasks.values():
            if task.parent_id:
                run._task_children[task.parent_id].append(task.task_id)
        return run

    def serialize(self) -> str:
        """JSON 序列化（state 可序列化）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)