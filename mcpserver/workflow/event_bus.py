"""事件总线 — buzz「事件日志即消息总线」落地。

- pub/sub：订阅者按事件类型注册，publish 时同步分发。
- 持久化：append-only JSONL 事件日志（只追加、不删改），崩溃后可回放。
- 事件类型：task_created / task_assigned / task_claimed / task_blocked /
  task_done / review_requested / review_approved。
- 每事件带 id / timestamp / source / trace_id，trace_id 贯穿一次逻辑操作的多条事件。

硬约束：纯 Python 标准库（json + threading + uuid + pathlib），零新重依赖。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

# 事件类型常量（buzz 的 kind 语义，此处以字符串命名保持轻量）
EVENT_TASK_CREATED = "task_created"
EVENT_TASK_ASSIGNED = "task_assigned"
EVENT_TASK_CLAIMED = "task_claimed"
EVENT_TASK_BLOCKED = "task_blocked"
EVENT_TASK_DONE = "task_done"
EVENT_REVIEW_REQUESTED = "review_requested"
EVENT_REVIEW_APPROVED = "review_approved"

ALL_EVENT_TYPES: tuple[str, ...] = (
    EVENT_TASK_CREATED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_CLAIMED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_DONE,
    EVENT_REVIEW_REQUESTED,
    EVENT_REVIEW_APPROVED,
)


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_trace_id() -> str:
    """生成贯穿一次逻辑操作的事件链 trace_id。"""
    return uuid.uuid4().hex


@dataclass
class Event:
    """一条事件（对齐 buzz 事件信封的 id/时间/来源/类型，去掉密码学签名）。"""

    event_type: str
    source: str
    timestamp: str = field(default_factory=utcnow_iso)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace_id: str = field(default_factory=new_trace_id)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            event_type=data["event_type"],
            timestamp=data.get("timestamp") or utcnow_iso(),
            source=data.get("source", ""),
            trace_id=data.get("trace_id") or "",
            payload=data.get("payload") or {},
        )


class EventBus:
    """进程内事件总线 + append-only JSONL 持久化日志。

    log_path 为 None 时仅内存分发（不落盘）；否则每次 publish 同步追加一行 JSON。
    追加即提交：只 open(..., "a")，绝不删改既有行，满足 append-only 约束。
    """

    def __init__(self, log_path: str | Path | None = None):
        self._log_path = Path(log_path) if log_path else None
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            # 确保文件存在（空文件即可，不写表头，保证纯事件行）
            self._log_path.touch(exist_ok=True)

    # ── pub/sub ──
    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> Callable[[], None]:
        """注册订阅者，返回退订函数（返回后调用即可取消）。"""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._subscribers.get(event_type)
                if handlers and handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def publish(self, event_type: str, source: str,
                payload: dict[str, Any] | None = None,
                trace_id: str | None = None) -> Event:
        """构造事件 → 追加日志 → 通知订阅者。返回事件对象。"""
        event = Event(
            event_type=event_type,
            source=source,
            trace_id=trace_id or new_trace_id(),
            payload=payload or {},
        )
        self._append(event)
        self._notify(event)
        return event

    # ── 持久化 ──
    def _append(self, event: Event) -> None:
        if self._log_path is None:
            return
        with self._lock, self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _notify(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))
        for handler in handlers:
            handler(event)

    # ── 回放 ──
    def replay(self, event_type: str | None = None,
               source: str | None = None,
               trace_id: str | None = None) -> list[Event]:
        """从日志回放事件，可按 type / source / trace_id 过滤。

        坏事件容错：单行损坏（非 JSON / 缺字段）只跳过并计数，不中断整批回放。
        """
        events: list[Event] = []
        if self._log_path is None:
            return events
        with self._lock:
            if not self._log_path.exists():
                return events
            for line in self._log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    ev = Event.from_dict(data)
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue  # 坏事件容错：跳过该行
                if event_type is not None and ev.event_type != event_type:
                    continue
                if source is not None and ev.source != source:
                    continue
                if trace_id is not None and ev.trace_id != trace_id:
                    continue
                events.append(ev)
        return events

    def iter_events(self) -> Iterator[Event]:
        """惰性迭代全部事件（供回放重建状态）。"""
        yield from self.replay()
