"""PTZ 心跳看门狗（卷130 W130-04 §1）——三保险的第三环（编排层通信心跳）。

**为什么这一环不能省**：卷129 的两环（编码器闭环、电流堵转）都在设备侧，
它们保护的是「机械自己出问题」；而「主机以为云台在听、其实链路已经断了」
是**主机侧才能发现**的故障——设备根本不知道主机的命令没送到。
所以这一环必须长在编排层，且动作是「主动去问，问不到就自己停」。

设计要点：

1. **周期探活**（默认 5s）：`tick()` 每拍发一次 `M114`，成功即清零连失计数。
2. **连续 N 次无响应**（默认 3）→ 触发兜底：`ptz_stop`（进给保持 `!`）→
   可选 `ptz_home`（回零）→ 可选 `M18`（卸载使能）→ fault 事件进卷119 event_bus。
3. **兜底只触发一次**（`_tripped` 闩锁）：失联期间不能每拍都发一遍 home——
   那会在链路恢复瞬间变成一串积压的回零命令，机械会莫名其妙地乱动。
4. **时间由注入的 clock 驱动**：测试用假钟推进，不 sleep。
5. **回零是"可配而非默认"**：失联时自动运动本身就是一种风险（天线被线缆缠住时
   回零比停住更危险），所以 `home_on_watchdog` 默认 False，由安全档显式打开。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

#: 第三环的故障码（与 firmware 侧 ring 名对齐；`SafetyRing.LINK` 同义）
FAULT_WATCHDOG = "watchdog_timeout"
FAULT_LINK_DOWN = "link_down"


class PTZWatchdog:
    """心跳看门狗：主动探活 + 连续失败兜底。

    只依赖一个 `probe` 回调（返回 `{"ok": bool, ...}`），所以既能配 `PTZService`，
    也能被单测用一个假回调直接驱动——不需要真的服务实例。
    """

    def __init__(self, probe: Callable[[], Dict[str, Any]], *,
                 interval_s: float = 5.0, max_miss: int = 3,
                 on_fault: Callable[[Dict[str, Any]], None] | None = None,
                 stop: Callable[[], Any] | None = None,
                 home: Callable[[], Any] | None = None,
                 disable: Callable[[], Any] | None = None,
                 home_on_watchdog: bool = False,
                 disable_on_watchdog: bool = True,
                 clock: Callable[[], float] = time.monotonic):
        self.probe = probe
        self.interval_s = max(0.1, float(interval_s))
        self.max_miss = max(1, int(max_miss))
        self.on_fault = on_fault
        self.stop = stop
        self.home = home
        self.disable = disable
        self.home_on_watchdog = bool(home_on_watchdog)
        self.disable_on_watchdog = bool(disable_on_watchdog)
        self._clock = clock

        self._lock = threading.RLock()
        self._misses = 0
        self._last_ok_at = 0.0
        self._last_tick_at: float | None = None   # None = 从未探活（**不是 0**：t=0 也可能是已探过）
        self._tripped = False
        self._recovering = False

        self.ticks = 0
        self.trips = 0
        self.due_skips = 0
        self.faults: list[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 判定
    # ------------------------------------------------------------------

    def due(self) -> bool:
        """到点了吗（按 `interval_s` 判，不用后台线程——由调用方驱动更可控）。

        「从未探活」用 `None` 表示而不是 `0.0`：假钟从 t=0 起步时，
        `0.0` 既可能是"刚探过"也可能是"没探过"，用哨兵值区分两者。
        （实现时踩过：用 0.0 当哨兵时，t=4.9 的第二拍被当成首拍，节流失效。）
        """
        now = self._clock()
        if self._last_tick_at is None:
            return True
        return (now - self._last_tick_at) >= self.interval_s

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._tripped

    @property
    def last_ok_age_s(self) -> float | None:
        with self._lock:
            if not self._last_ok_at:
                return None
            return round(self._clock() - self._last_ok_at, 3)

    # ------------------------------------------------------------------
    # 主循环（由外部 tick 驱动：服务 tick / 定时器 / 测试假钟）
    # ------------------------------------------------------------------

    def tick(self) -> Dict[str, Any]:
        """一拍。到点才真的探活；未到点直接返回 `skipped`（幂等，可高频调用）。"""
        if not self.due():
            self.due_skips += 1
            return {"ok": True, "skipped": True, "misses": self.misses,
                    "tripped": self.tripped}
        self._last_tick_at = self._clock()
        self.ticks += 1
        try:
            out = self.probe() or {}
        except Exception as exc:  # noqa: BLE001 - 探活异常等价于一次失联
            out = {"ok": False, "error": "probe_exception", "detail": str(exc)}

        if out.get("ok"):
            recovered = self._note_ok()
            return {"ok": True, "skipped": False, "misses": 0,
                    "tripped": self.tripped, "recovered": recovered,
                    "status": out.get("status")}

        return self._note_miss(str(out.get("error") or FAULT_LINK_DOWN),
                               str(out.get("detail") or ""))

    def note_ok(self) -> bool:
        """记一次成功探活（清零连失）。返回是否处于「刚恢复」状态。"""
        return self._note_ok()

    def _note_ok(self) -> bool:
        with self._lock:
            self._last_ok_at = self._clock()
            was = self._misses
            self._misses = 0
            recovered = self._recovering
            self._recovering = False
            return bool(was or recovered)

    def note_miss(self, error: str, detail: str = "") -> Dict[str, Any]:
        """记一次失联（**公开入口**）。

        `tick()` 之外的路径（例如 `_exchange` 里直接撞上 `TransportError`）
        也必须走这里——否则两边各记一份计数，兜底事件里的 `misses` 数值会失真。
        """
        return self._note_miss(error, detail)

    def _note_miss(self, error: str, detail: str) -> Dict[str, Any]:
        with self._lock:
            self._misses += 1
            misses = self._misses
            already = self._tripped
            self._recovering = True
        if misses >= self.max_miss and not already:
            self._trigger(error, detail)
            return {"ok": False, "skipped": False, "misses": misses,
                    "tripped": True, "triggered": True, "error": error}
        return {"ok": False, "skipped": False, "misses": misses,
                "tripped": already, "triggered": False, "error": error}

    # ------------------------------------------------------------------
    # 兜底动作
    # ------------------------------------------------------------------

    def _trigger(self, error: str, detail: str) -> None:
        """连续失败达阈值 → 停住（+可选回零/卸载）+ fault 上报。

        动作顺序是有讲究的：**先停住再回零**——回零本身是运动，
        必须先确保设备不在执行别的运动指令，否则两个运动叠加会撞限位。
        """
        with self._lock:
            self._tripped = True
            self.trips += 1
        actions: list[str] = []
        failed: list[str] = []

        def _try(name: str, fn: Callable[[], Any] | None) -> None:
            if fn is None:
                return
            try:
                fn()
                actions.append(name)
            except Exception as exc:  # noqa: BLE001 - 兜底尽力而为，任一失败不阻断后续
                failed.append(name)
                logger.warning("[ptz_watchdog] 兜底动作 %s 失败: %s", name, exc)

        _try("stop", self.stop)
        if self.home_on_watchdog:
            _try("home", self.home)
        if self.disable_on_watchdog:
            _try("disable", self.disable)

        event = {
            "ts": round(time.time(), 3),
            "kind": "watchdog",
            "error": error,
            "detail": detail,
            "misses": self.misses,
            "max_miss": self.max_miss,
            "interval_s": self.interval_s,
            # `actions` = 真正送达的；`attempted` = 尝试过的（含失败的）。
            # 两个都要留：链路全断时主机侧的兜底命令**自己就发不出去**，
            # 这时 `actions` 为空而 `attempted` 非空——这个差别正是
            # 「设备侧看门狗必须独立存在」的证据（见架构稿决策 3 的实现注记）。
            "actions": actions,
            "attempted": actions + failed,
            "actions_failed": failed,
            # 兼容 W130-01 已有的字段名（编排层/前端可能已经在读 `action`）；
            # 新代码请读 `actions` 列表。旧字段是它的字符串投影，两者同源。
            "action": "+".join(actions) or "none",
            "ring": 4,              # 第三环（编排层通信心跳）；固件侧五环表见 safety_governor
        }
        if failed and not actions:
            event["detail"] = (f"{detail} | 兜底命令未能送达（{','.join(failed)}），"
                               "链路已断时只有设备侧看门狗能执行兜底")
        self.faults.append(event)
        logger.warning("[ptz_watchdog] 心跳兜底触发：%s", event)
        if self.on_fault is not None:
            try:
                self.on_fault(dict(event))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[ptz_watchdog] fault 上报失败: %s", exc)

    def reset(self) -> None:
        """显式复位（`ptz_reset` 后调用）：清计数与闩锁。"""
        with self._lock:
            self._misses = 0
            self._tripped = False
            self._recovering = False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "interval_s": self.interval_s,
            "max_miss": self.max_miss,
            "misses": self.misses,
            "tripped": self.tripped,
            "ticks": self.ticks,
            "trips": self.trips,
            "due_skips": self.due_skips,
            "last_ok_age_s": self.last_ok_age_s,
            "home_on_watchdog": self.home_on_watchdog,
            "disable_on_watchdog": self.disable_on_watchdog,
            "faults": list(self.faults),
        }


__all__ = ["PTZWatchdog", "FAULT_WATCHDOG", "FAULT_LINK_DOWN"]
