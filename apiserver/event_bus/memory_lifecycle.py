"""W120-03：记忆事件化 + 分层（MEMORY_CREATED / MEMORY_ARCHIVED 接通）。

- 发布：`message_manager` 的记忆写入路径（远程 `memory_client` 与本地 `summer_memory`）成功后
  emit `MEMORY_CREATED`；归档/删除处 emit `MEMORY_ARCHIVED`
- 消费：`SummerMemoryConsumer`（订阅 MEMORY_CREATED，做统计/联动/触发压缩检查）——由
  `api_server` lifespan 通过 `handlers.register_summer_memory_consumer` 注册
- 分层：`MemoryLayering` 维护短期窗口 → 超阈值/超时长时 emit `MEMORY_ARCHIVED`
  （对 summer_memory 存储**只做标记与策略建议**，不改其 schema）
- 压缩联动：MEMORY_ARCHIVED 可被压缩/摘要逻辑订阅（本卷只接线，实现留给现有 context_compressor；
  订阅示例见本文件 `register_compression_hint`）
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from .bus import EventBus
from .disposable import Disposable
from .topics import Topics

logger = logging.getLogger(__name__)


class MemoryLayering:
    """短期记忆窗口 → 超阈值/超时长提升为长期（emit MEMORY_ARCHIVED 表示「离开短期层」）。"""

    def __init__(
        self,
        bus: EventBus,
        *,
        enabled: bool = True,
        max_short_term: int = 50,
        promote_after_seconds: float = 6 * 3600,
    ) -> None:
        self.bus = bus
        self.enabled = bool(enabled)
        self.max_short_term = max(1, int(max_short_term))
        self.promote_after_seconds = max(60.0, float(promote_after_seconds))
        self._short: Deque[Dict[str, Any]] = deque()
        self._long_ids: set[str] = set()
        self._lock = threading.Lock()
        self.created_total = 0
        self.promoted_total = 0

    # ---- 事件入口 ----

    def on_memory_created(self, event: Any) -> None:
        if not self.enabled:
            return
        payload = event if isinstance(event, dict) else {}
        memory_id = str(payload.get("memory_id") or payload.get("id") or "")
        item = {
            "memory_id": memory_id,
            "summary": str(payload.get("summary") or "")[:160],
            "source": str(payload.get("source") or ""),
            "ts": float(payload.get("ts") or time.time()),
        }
        with self._lock:
            self.created_total += 1
            self._short.append(item)
        self._maybe_promote(trigger="capacity")

    def on_memory_archived(self, event: Any) -> None:
        payload = event if isinstance(event, dict) else {}
        memory_id = str(payload.get("memory_id") or payload.get("id") or "")
        with self._lock:
            if memory_id:
                self._long_ids.add(memory_id)
            self._short = deque(i for i in self._short if i["memory_id"] != memory_id)

    # ---- 分层判定 ----

    def _maybe_promote(self, *, trigger: str, now: float | None = None) -> List[Dict[str, Any]]:
        """把短期条目提升为长期（emit MEMORY_ARCHIVED）。返回被提升的条目。

        两个触发各管各的规则（避免互相「顺手」提升造成语义含糊）：
        - `capacity`（每次写入后）：只按容量上限提升
        - `time`（`sweep()`，可由 SCHEDULER_TICK 驱动）：只按驻留时长提升
        """
        current = now if now is not None else time.time()
        promoted: List[Dict[str, Any]] = []
        with self._lock:
            if trigger == "capacity":
                while len(self._short) > self.max_short_term:
                    promoted.append(self._short.popleft())
            elif trigger == "time":
                stale = [i for i in self._short if (current - i["ts"]) >= self.promote_after_seconds]
                for item in stale:
                    self._short.remove(item)
                    promoted.append(item)
        for item in promoted:
            self.promoted_total += 1
            payload = {
                "id": item["memory_id"],
                "memory_id": item["memory_id"],
                "summary": item["summary"],
                "source": item["source"],
                "reason": f"layering:{trigger}",
                "layer": "long_term",
                "ts": current,
            }
            try:
                self.bus.emit(Topics.MEMORY_ARCHIVED, payload)
            except Exception:  # noqa: BLE001 - 分层失败不影响记忆写入
                logger.debug("[memory_layering] ARCHIVED 事件分发失败", exc_info=True)
        return promoted

    def sweep(self) -> List[Dict[str, Any]]:
        """按时间阈值扫一次（可由 SCHEDULER_TICK 驱动）。"""
        if not self.enabled:
            return []
        return self._maybe_promote(trigger="time")

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "short_term": len(self._short),
                "long_term": len(self._long_ids),
                "created_total": self.created_total,
                "promoted_total": self.promoted_total,
                "max_short_term": self.max_short_term,
                "promote_after_seconds": self.promote_after_seconds,
            }


class SummerMemoryConsumer:
    """summer_memory 侧消费者：统计 + 触发分层 + 给压缩逻辑留钩子。"""

    def __init__(self, bus: EventBus, layering: MemoryLayering | None = None) -> None:
        self.bus = bus
        self.layering = layering or MemoryLayering(bus)
        self.created_seen = 0
        self.archived_seen = 0
        self._compression_hooks: List[Callable[[Dict[str, Any]], None]] = []

    def on_memory_created(self, event: Any) -> None:
        self.created_seen += 1
        self.layering.on_memory_created(event)

    def on_memory_archived(self, event: Any) -> None:
        self.archived_seen += 1
        self.layering.on_memory_archived(event)
        payload = event if isinstance(event, dict) else {}
        for hook in list(self._compression_hooks):
            try:
                hook(payload)
            except Exception:  # noqa: BLE001
                logger.debug("[memory_consumer] 压缩钩子失败", exc_info=True)

    def attach(self) -> List[Disposable]:
        return [
            self.bus.on(Topics.MEMORY_CREATED, self.on_memory_created),
            self.bus.on(Topics.MEMORY_ARCHIVED, self.on_memory_archived),
        ]

    def stats(self) -> Dict[str, Any]:
        return {
            "created_seen": self.created_seen,
            "archived_seen": self.archived_seen,
            "compression_hooks": len(self._compression_hooks),
            **{f"layering_{k}": v for k, v in self.layering.stats().items()},
        }


_consumer: SummerMemoryConsumer | None = None
_consumer_lock = threading.Lock()


def get_memory_consumer(bus: EventBus | None = None) -> SummerMemoryConsumer | None:
    """进程级单例（读 config.memory.layering.*）。"""
    global _consumer
    if _consumer is None:
        target = bus
        if target is None:
            try:
                from . import get_bus

                target = get_bus()
            except Exception:  # noqa: BLE001
                return None
        enabled, max_short, promote_after = True, 50, 6 * 3600.0
        try:
            from system.config import get_config

            cfg = get_config().memory.layering
            enabled = bool(getattr(cfg, "enabled", True))
            max_short = int(getattr(cfg, "max_short_term", 50))
            promote_after = float(getattr(cfg, "promote_after_seconds", 6 * 3600))
        except Exception as e:  # noqa: BLE001
            logger.debug("[memory_consumer] 读取配置失败，用默认值: %s", e)
        with _consumer_lock:
            if _consumer is None:
                _consumer = SummerMemoryConsumer(
                    target,
                    layering=MemoryLayering(
                        target,
                        enabled=enabled,
                        max_short_term=max_short,
                        promote_after_seconds=promote_after,
                    ),
                )
    return _consumer


def reset_memory_consumer_for_tests(consumer: SummerMemoryConsumer | None = None) -> None:
    global _consumer
    with _consumer_lock:
        _consumer = consumer


def register_compression_hint(consumer: SummerMemoryConsumer, hook: Callable[[Dict[str, Any]], None]) -> None:
    """压缩/摘要逻辑的订阅示例（README 同款）：

        register_compression_hint(get_memory_consumer(),
                                  lambda ev: compressor.maybe_compress(ev["memory_id"]))
    """
    consumer._compression_hooks.append(hook)
