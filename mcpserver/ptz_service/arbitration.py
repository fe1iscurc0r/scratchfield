"""双路仲裁（卷130 W130-02 §4）——本地串口 + LoRa 无线并存时的「最后指令优先」。

工单原文：「本地串口 + LoRa 同时控制时**最后指令优先**（时间戳）；`ptz_status`
显示 last_source（serial/lora）」。

**为什么是 last-wins 而不是优先级**：这是有意的语义选择。两条路都是"人在操作",
谁后动手谁说话算数——这是操作台的直觉。用固定优先级会在"LoRa 操作员想让位、
但串口端没人动"时把控制权锁死在空转的串口上。

与卷130 架构稿的差异要说明清楚：架构稿当时拟的是「本地 > 有线 > LoRa 优先级 + owner
空闲释放」；工单明确规定 last-wins。**以工单为准**，本模块实现工单语义。
优先级方案留作可选项（`mode="priority"`），因为某些部署（例如调试口要压过遥控口）
确实需要它——但默认是工单要求的 last-wins。

并发安全：`claim()` 必须原子。两路同时到达时"谁后到"本身有竞争，
但**结果必须是一个确定的赢家**，不能两个都执行（机械执行器不接受双主）。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

#: 来源常量（与固件/审计里的 source 字段同表）
SOURCE_SERIAL = "serial"
SOURCE_LORA = "lora"
SOURCE_SIM = "sim"
SOURCE_LOCAL = "local"

#: 优先级方案（可选）下的档位：越大越优先
PRIORITY_ORDER = {SOURCE_SIM: 0, SOURCE_LORA: 1, SOURCE_LOCAL: 2, SOURCE_SERIAL: 3}

MODE_LAST_WINS = "last_wins"
MODE_PRIORITY = "priority"


class ArbitrationResult:
    """一次仲裁判定。"""

    def __init__(self, accepted: bool, winner: str = "", reason: str = "",
                 detail: str = ""):
        self.accepted = accepted
        self.winner = winner
        self.reason = reason
        self.detail = detail

    def as_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "winner": self.winner,
                "reason": self.reason, "detail": self.detail}


class ChannelArbiter:
    """双路仲裁器：决定"这条命令该不该被执行"。"""

    def __init__(self, mode: str = MODE_LAST_WINS, *, clock: Callable[[], float] = time.time,
                 min_switch_interval_s: float = 0.0):
        self.mode = str(mode or MODE_LAST_WINS)
        self._clock = clock
        #: 防抖：同一来源在极短时间里重复涌现（例如重传）不该算"换了来源"。
        #: 默认 0 表示不防抖——仲裁语义要纯粹，需要时显式打开。
        self.min_switch_interval_s = float(min_switch_interval_s)
        self._lock = threading.Lock()
        self._last_source = ""
        self._last_ts = 0.0
        self._last_cmd = ""
        self.switches = 0
        self.rejected = 0
        self.accepted = 0
        #: 来源切换轨迹（诊断用，不落盘——落盘由审计模块负责）
        self.history: List[Dict[str, Any]] = []

    # ---- 判定 ----

    def claim(self, source: str, cmd: str = "", *, priority: int | None = None) -> ArbitrationResult:
        """申报一次控制权。"""
        src = str(source or "").strip().lower()
        if not src:
            return ArbitrationResult(False, reason="bad_source",
                                     detail="来源不能为空（serial/lora）")
        now = self._clock()
        with self._lock:
            prev = self._last_source
            if self.mode == MODE_PRIORITY:
                allowed, why = self._priority_allows(src, priority)
                if not allowed:
                    self.rejected += 1
                    return ArbitrationResult(False, winner=prev, reason="priority_denied",
                                             detail=why)
            if prev and prev != src:
                # 来源确实换了（last-wins 下这是允许的，只记一笔）
                if self.min_switch_interval_s > 0 and (now - self._last_ts) < self.min_switch_interval_s:
                    self.rejected += 1
                    return ArbitrationResult(
                        False, winner=prev, reason="switch_too_fast",
                        detail=f"{prev} 在 {self.min_switch_interval_s}s 内刚控制过，"
                               f"{src} 的指令被抑制（防抖）")
                self.switches += 1
                self.history.append({"ts": round(now, 3), "from": prev, "to": src,
                                     "cmd": str(cmd)[:60]})
                if len(self.history) > 100:
                    del self.history[:-100]
            self._last_source = src
            self._last_ts = now
            self._last_cmd = str(cmd or "")
            self.accepted += 1
        return ArbitrationResult(True, winner=src,
                                 detail=(f"来源 {src} 取得控制权"
                                         + (f"（从 {prev} 切换）" if prev and prev != src else "")))

    def _priority_allows(self, src: str, priority: int | None) -> tuple[bool, str]:
        """优先级方案（非默认）：不低于当前持有者的档位才放行。"""
        if not self._last_source:
            return True, ""
        cur = PRIORITY_ORDER.get(self._last_source, 0)
        new = int(priority) if priority is not None else PRIORITY_ORDER.get(src, 0)
        if new < cur:
            return False, (f"{src}(档 {new}) 低于当前持有者 "
                           f"{self._last_source}(档 {cur})，控制权不转移")
        return True, ""

    def release(self, source: str = "") -> None:
        """释放控制权（空闲超时/显式让位）。`source` 不匹配则不释放。"""
        with self._lock:
            if source and str(source).lower() != self._last_source:
                return
            self._last_source = ""
            self._last_ts = 0.0

    def release_if_idle(self, idle_s: float) -> bool:
        """空闲超过 `idle_s` 就释放——避免"上一次操作"永久占着来源标记。"""
        with self._lock:
            if not self._last_source:
                return False
            if (self._clock() - self._last_ts) >= float(idle_s):
                self._last_source = ""
                return True
            return False

    # ---- 读取 ----

    @property
    def last_source(self) -> str:
        with self._lock:
            return self._last_source

    @property
    def last_age_s(self) -> float | None:
        with self._lock:
            if not self._last_source or not self._last_ts:
                return None
            return round(self._clock() - self._last_ts, 3)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "last_source": self._last_source,
                "last_cmd": self._last_cmd,
                "last_age_s": (round(self._clock() - self._last_ts, 3)
                               if self._last_source and self._last_ts else None),
                "switches": self.switches,
                "accepted": self.accepted,
                "rejected": self.rejected,
                "history": list(self.history[-20:]),
            }


__all__ = ["ChannelArbiter", "ArbitrationResult", "MODE_LAST_WINS", "MODE_PRIORITY",
           "SOURCE_SERIAL", "SOURCE_LORA", "SOURCE_SIM", "SOURCE_LOCAL", "PRIORITY_ORDER"]
