"""PTZ 状态缓存（卷130 W130-01）。

两个职责：
1. **缓存最近状态**（az/el/moving/fault/updated_at）——状态查询不该每次穿透到设备，
   那会和运动指令抢链路。
2. **幂等**：重复下发相同目标视为 no-op——云台是物理执行器，
   「再走一遍同一个点」既费时又磨损机构，没有意义。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

from .rotator_core import protocol as cmd

#: 目标角比对容差（度）——小于它就认为「已经在目标上」
TARGET_EPSILON_DEG = 0.05


class PTZStateStore:
    """线程安全的状态缓存 + 幂等判定。"""

    def __init__(self, clock=time.monotonic, stale_after_s: float = 30.0):
        self._clock = clock
        self.stale_after_s = float(stale_after_s)
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = {}
        self._updated_at = 0.0
        self._last_target: Tuple[float, float] | None = None
        self._last_source = ""
        self.duplicate_moves = 0

    # ---- 写入 ----

    def absorb(self, status_line: str, *, source: str = "") -> Dict[str, Any]:
        """吃进一行 M114 状态行；畸形行**不猜**，原样保留旧值。"""
        parsed = cmd.parse_status(status_line)
        if parsed is None:
            return dict(self._state)
        with self._lock:
            self._state = dict(parsed)
            self._updated_at = self._clock()
            if source:
                self._last_source = source
        return dict(self._state)

    def note_target(self, az: float, el: float, *, source: str = "") -> None:
        with self._lock:
            self._last_target = (float(az), float(el))
            if source:
                self._last_source = source

    def clear_target(self) -> None:
        with self._lock:
            self._last_target = None

    # ---- 幂等 ----

    def is_duplicate(self, az: float, el: float) -> bool:
        """目标与上次相同（容差内）→ 视为重复。回零/停止会清目标，不会误判。"""
        with self._lock:
            if self._last_target is None:
                return False
            same = (abs(self._last_target[0] - float(az)) <= TARGET_EPSILON_DEG
                    and abs(self._last_target[1] - float(el)) <= TARGET_EPSILON_DEG)
            if same:
                self.duplicate_moves += 1
            return same

    # ---- 读取 ----

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            age = self._clock() - self._updated_at if self._updated_at else None
            return {
                **dict(self._state),
                "updated_at": round(self._updated_at, 3),
                "age_s": round(age, 3) if age is not None else None,
                "stale": bool(age is not None and age > self.stale_after_s),
                "last_target": list(self._last_target) if self._last_target else None,
                "last_source": self._last_source,
                "duplicate_moves": self.duplicate_moves,
                "known": bool(self._state),
            }

    @property
    def last_source(self) -> str:
        return self._last_source

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
            self._updated_at = 0.0
            self._last_target = None
            self._last_source = ""
            self.duplicate_moves = 0


__all__ = ["PTZStateStore", "TARGET_EPSILON_DEG"]
