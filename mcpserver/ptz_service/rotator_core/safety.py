"""安全环与失联策略（卷130 W130-05 的主机侧镜像）。

与固件 `safety/safety_governor.hpp` 同一个枚举、同一套语义——**两侧同源，不各写一套**。
主机侧这份存在的理由：失联策略是纯决策函数，能在没有硬件时被测试
（照卷129 的「Python 规格镜像」惯例）。

三保险（卷129 已落地，各自为政）＋链路环（卷130 新增）：

| 环 | 出处 | 触发 | 恢复 |
| --- | --- | --- | --- |
| ① ENCODER | `feedback/as5600.hpp` | 读失败/抖动超阈 | 自动（读数恢复即清） |
| ② STALL | `servo_ptz/servo_axis.hpp` | ADC 电流超阈 | **必须显式 `$X`** |
| ③ SOFT_LIMIT | `motion/planner.hpp` | 目标越限 | 拒绝动作，**不置 fault** |
| ④ LINK | 卷130 `safety_governor` | 心跳超时 | 链路恢复 + 显式确认 |
"""
from __future__ import annotations

from enum import Enum, IntEnum
from typing import Any, Dict


class SafetyRing(IntEnum):
    NONE = 0
    ENCODER = 1        # 编码器闭环
    STALL = 2          # 电流堵转
    SOFT_LIMIT = 3     # 软限位（只拒绝，不锁死）
    LINK = 4           # 链路失联
    ESTOP = 5          # 急停（命令驱动，不是传感器环）

    @classmethod
    def from_value(cls, value: Any) -> "SafetyRing":
        try:
            return cls(int(value))
        except (TypeError, ValueError):
            return cls.NONE

    @property
    def label(self) -> str:
        return _RING_LABEL.get(self, "unknown")

    @property
    def blocks_motion(self) -> bool:
        """该环触发后是否禁止继续运动（软限位只拒绝单条命令，不锁死整机）。"""
        return self in (SafetyRing.ENCODER, SafetyRing.STALL, SafetyRing.LINK, SafetyRing.ESTOP)

    @property
    def needs_explicit_clear(self) -> bool:
        """是否需要显式清故障：机械/硬件类必须；编码器读数恢复即自动。"""
        return self in (SafetyRing.STALL, SafetyRing.LINK, SafetyRing.ESTOP)


_RING_LABEL = {
    SafetyRing.NONE: "none",
    SafetyRing.ENCODER: "编码器闭环",
    SafetyRing.STALL: "电流堵转",
    SafetyRing.SOFT_LIMIT: "软限位",
    SafetyRing.LINK: "链路失联",
    SafetyRing.ESTOP: "急停",
}

#: 环的处置优先级（数字大 = 更该被报出来）。堵转是机械异常，优先于其它。
RING_PRIORITY = {
    SafetyRing.STALL: 50,
    SafetyRing.ESTOP: 45,
    SafetyRing.ENCODER: 40,
    SafetyRing.LINK: 30,
    SafetyRing.SOFT_LIMIT: 20,
    SafetyRing.NONE: 0,
}


def dominant_ring(rings: Any) -> SafetyRing:
    """从一组触发中的环里挑出该上报的那个（按 RING_PRIORITY）。"""
    best = SafetyRing.NONE
    for item in rings or ():
        ring = item if isinstance(item, SafetyRing) else SafetyRing.from_value(item)
        if RING_PRIORITY.get(ring, 0) > RING_PRIORITY.get(best, 0):
            best = ring
    return best


class FailsafePolicy(str, Enum):
    """失联后的安全姿态（卷130 架构决策 3）。三选一，互斥。

    **执行者是固件，不是主机**：链路断了主机根本发不出命令，所以固件自己检测
    心跳超时并执行策略；主机只在连接时把策略下发下去（`$FS=`），
    并在重连后核对设备实际处于什么状态。
    """

    HOLD = "hold"                            # 停住：保持位置与励磁（最保守，但可能持续发热）
    HOLD_THEN_DISABLE = "hold_then_disable"  # 停住 N 秒后卸载使能（**默认**）
    CENTER = "center"                        # 回中：方位 0 / 俯仰 0（姿态可预期，但失联时自动运动）
    DISABLE = "disable"                      # 立即卸载使能（最安全，但天线可能因风载自由转动）

    @classmethod
    def from_name(cls, name: Any) -> "FailsafePolicy":
        text = str(name or "").strip().lower()
        for member in cls:
            if member.value == text:
                return member
        return cls.HOLD_THEN_DISABLE

    @property
    def code(self) -> int:
        """线上编码（`$FS=<code>,<hold_s>`；与固件枚举值同表）。"""
        return _POLICY_CODE[self]

    @classmethod
    def from_code(cls, code: Any) -> "FailsafePolicy":
        try:
            return _CODE_POLICY[int(code)]
        except (KeyError, TypeError, ValueError):
            return cls.HOLD_THEN_DISABLE


_POLICY_CODE = {
    FailsafePolicy.HOLD: 0,
    FailsafePolicy.HOLD_THEN_DISABLE: 1,
    FailsafePolicy.CENTER: 2,
    FailsafePolicy.DISABLE: 3,
}
_CODE_POLICY = {v: k for k, v in _POLICY_CODE.items()}


class FailsafeAction(str, Enum):
    NONE = "none"
    HOLD = "hold"
    DISABLE = "disable"
    CENTER = "center"


#: HOLD_THEN_DISABLE 的默认卸载延迟（秒）
DEFAULT_HOLD_S = 30.0


def failsafe_action(policy: FailsafePolicy, elapsed_s: float,
                    hold_s: float = DEFAULT_HOLD_S) -> FailsafeAction:
    """失联已持续 `elapsed_s` 秒时该做什么。纯函数，无副作用。

    - HOLD                 → 一直停住
    - HOLD_THEN_DISABLE    → 前 hold_s 秒停住，之后卸载使能
    - CENTER               → 立即回中
    - DISABLE              → 立即卸载
    """
    elapsed = max(0.0, float(elapsed_s))
    if policy is FailsafePolicy.HOLD:
        return FailsafeAction.HOLD
    if policy is FailsafePolicy.HOLD_THEN_DISABLE:
        return FailsafeAction.HOLD if elapsed < float(hold_s) else FailsafeAction.DISABLE
    if policy is FailsafePolicy.CENTER:
        return FailsafeAction.CENTER
    if policy is FailsafePolicy.DISABLE:
        return FailsafeAction.DISABLE
    return FailsafeAction.HOLD


def describe(ring: SafetyRing, detail: str = "") -> Dict[str, Any]:
    """故障事件的可上报形状（与固件 `SafetyEvent` 字段对齐）。"""
    return {
        "ring": int(ring),
        "ring_label": ring.label,
        "blocks_motion": ring.blocks_motion,
        "needs_explicit_clear": ring.needs_explicit_clear,
        "detail": str(detail or ""),
    }


__all__ = [
    "SafetyRing", "RING_PRIORITY", "dominant_ring",
    "FailsafePolicy", "FailsafeAction", "DEFAULT_HOLD_S", "failsafe_action", "describe",
]
