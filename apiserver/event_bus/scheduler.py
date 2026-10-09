"""W120-02：调度任务总线化 —— 轻量 tick 发号器，把定时任务统一到总线事件。

- `Topics.SCHEDULER_TICK`（`lumo.scheduler.tick`）payload：`{interval, tick_n, triggered_at}`
- 档位配置：`config.bus.scheduler.ticks`（默认 `["5m", "1h"]`，支持 `30s` / `0.5m` / `2h`）
- 每个档位一个异步循环任务：到点 emit tick（`tick_n` 单调递增）；单次异常不中断循环
- proactive 迁移：`lumo_proactive.on_scheduler_tick` 订阅 5m 档，行为与原 `_periodic_check` 等价；
  原定时器保留为兜底（`config.bus.scheduler.use_bus=false` 时可切回）
- 未来 cron/日报/巡检：`handlers.register_scheduler_subscriber(bus, handler)` 一行注册
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .bus import EventBus
from .disposable import Disposable
from .topics import Topics

logger = logging.getLogger(__name__)

_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smh])\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0}
DEFAULT_TICKS = ("5m", "1h")


def parse_interval(spec: str) -> float:
    """`5m` / `30s` / `0.5m` / `2h` → 秒；无法解析抛 ValueError。"""
    match = _INTERVAL_RE.match(str(spec or ""))
    if not match:
        raise ValueError(f"无法解析调度档位: {spec!r}（支持 30s/5m/2h 形式）")
    return float(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scheduler:
    """按档位周期 emit `SCHEDULER_TICK` 的发号器。"""

    def __init__(self, bus: EventBus, ticks: List[str] | None = None) -> None:
        self.bus = bus
        self.ticks: List[str] = [str(t) for t in (ticks or DEFAULT_TICKS)]
        self._counters: Dict[str, int] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._lock = threading.Lock()

    # ---- 事件构造 / 手动发号（测试与手动触发用） ----

    def emit_tick(self, spec: str) -> Dict[str, Any]:
        """发一次 tick（计数器 +1），返回事件 payload。"""
        key = str(spec)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1
            tick_n = self._counters[key]
        payload = {"interval": key, "tick_n": tick_n, "triggered_at": _now_iso()}
        try:
            self.bus.emit(Topics.SCHEDULER_TICK, payload)
        except Exception:  # noqa: BLE001 - 单次发号失败不影响调度循环
            logger.warning("[scheduler] tick 分发失败（%s）", key, exc_info=True)
        return payload

    def tick_count(self, spec: str | None = None) -> int:
        with self._lock:
            if spec is None:
                return sum(self._counters.values())
            return self._counters.get(str(spec), 0)

    # ---- 循环 ----

    async def _run_interval(self, spec: str) -> None:
        try:
            seconds = parse_interval(spec)
        except ValueError as e:
            logger.warning("[scheduler] 档位 %s 无效，跳过: %s", spec, e)
            return
        while self._running:
            try:
                await asyncio.sleep(seconds)
                if not self._running:
                    return
                self.emit_tick(spec)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 单轮失败继续下一轮
                logger.warning("[scheduler] 档位 %s 单轮异常，继续", spec, exc_info=True)

    def start(self) -> None:
        """启动全部档位循环（幂等）。"""
        if self._running:
            return
        self._running = True
        for spec in self.ticks:
            try:
                self._tasks[spec] = asyncio.ensure_future(self._run_interval(spec))
            except RuntimeError:
                # 无事件循环（同步上下文）：退化到手动 emit_tick，不抛
                logger.warning("[scheduler] 无事件循环，档位 %s 未启动（可用 emit_tick 手动发号）", spec)
                self._running = False
                return
        logger.info("[scheduler] 已启动档位: %s", ", ".join(self.ticks))

    def stop(self) -> None:
        self._running = False
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "ticks": list(self.ticks),
            "counters": dict(self._counters),
        }


_scheduler: Scheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler(bus: EventBus | None = None) -> Scheduler | None:
    """进程级单例（读 config.bus.scheduler.ticks）。

    工单222 任务三：并发首建加锁（原为裸 check-then-set，两线程可各建一个
    Scheduler → 定时任务重复注册）。
    """
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                target_bus = bus
                if target_bus is None:
                    try:
                        from . import get_bus

                        target_bus = get_bus()
                    except Exception:  # noqa: BLE001
                        return None
                ticks: List[str] = list(DEFAULT_TICKS)
                try:
                    from system.config import get_config

                    cfg_ticks = getattr(get_config().bus.scheduler, "ticks", None)
                    if cfg_ticks:
                        ticks = [str(t) for t in cfg_ticks]
                except Exception as e:  # noqa: BLE001 - 配置不可用时用默认档位
                    logger.debug("[scheduler] 读取配置失败，用默认档位: %s", e)
                _scheduler = Scheduler(target_bus, ticks=ticks)
    return _scheduler


def reset_scheduler_for_tests(scheduler: Scheduler | None = None) -> None:
    global _scheduler
    if _scheduler is not None and _scheduler is not scheduler:
        _scheduler.stop()
    _scheduler = scheduler


def start_scheduler() -> Scheduler | None:
    scheduler = get_scheduler()
    if scheduler is not None:
        scheduler.start()
    return scheduler


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.stop()


def register_scheduler_subscriber(
    bus: EventBus, handler: Callable[[Dict[str, Any]], Any]
) -> Disposable:
    """通用订阅入口：定时任务（日报/巡检/记忆归档）订阅 SCHEDULER_TICK。

    用法（文档示例）：`register_scheduler_subscriber(bus, lambda e: daily_job() if e["interval"] == "1h" else None)`
    """
    return bus.on(Topics.SCHEDULER_TICK, handler)
