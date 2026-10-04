"""故障注入类型定义（E-01）。

定义故障类型/模式枚举、可配置参数模型 FaultSpec，以及各故障类型触发时抛出的
异常。本模块纯 Python 标准库，零新重依赖。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class FaultType(str, enum.Enum):
    """故障类型枚举。"""

    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    MCP_RATE_LIMIT = "mcp_rate_limit"
    MCP_DISCONNECT = "mcp_disconnect"
    MCP_SLOW = "mcp_slow"
    PREFIX_PERTURB = "prefix_perturb"
    ORCHESTRATOR_INTERRUPT = "orchestrator_interrupt"


class FaultMode(str, enum.Enum):
    """故障触发模式：一次 / 持续 / 随机。"""

    ONCE = "once"
    PERSISTENT = "persistent"
    RANDOM = "random"


class FaultInjectionError(Exception):
    """故障注入触发时抛出的基类异常。"""

    fault_type: str = "unknown"


class ToolTimeoutError(FaultInjectionError):
    fault_type = FaultType.TOOL_TIMEOUT.value


class ToolError(FaultInjectionError):
    fault_type = FaultType.TOOL_ERROR.value


class RateLimitError(FaultInjectionError):
    fault_type = FaultType.MCP_RATE_LIMIT.value


class DisconnectError(FaultInjectionError):
    fault_type = FaultType.MCP_DISCONNECT.value


class OrchestratorInterruptError(FaultInjectionError):
    fault_type = FaultType.ORCHESTRATOR_INTERRUPT.value


# 故障类型 → 抛出异常（mcp_slow / prefix_perturb 不抛异常，走延迟/扰动路径）
FAULT_EXCEPTIONS: dict[FaultType, type[FaultInjectionError]] = {
    FaultType.TOOL_TIMEOUT: ToolTimeoutError,
    FaultType.TOOL_ERROR: ToolError,
    FaultType.MCP_RATE_LIMIT: RateLimitError,
    FaultType.MCP_DISCONNECT: DisconnectError,
    FaultType.ORCHESTRATOR_INTERRUPT: OrchestratorInterruptError,
}


def _coerce_float(value: Any, name: str) -> float:
    """把配置值安全转为 float，拒绝布尔等非数字类型。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是数字，收到布尔值 {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字，收到 {value!r}") from exc


@dataclass
class FaultSpec:
    """单个故障的可配置参数模型。

    通用可配参数：delay（延迟/超时秒）、probability（随机模式概率）、duration（持续时间秒）。
    额外参数：count（once 模式可触发总次数）、message（错误/扰动携带的消息）、enabled（是否生效）。
    """

    type: FaultType
    mode: FaultMode = FaultMode.ONCE
    probability: float = 1.0
    delay: float = 0.0
    duration: float = 0.0
    count: int = 1
    message: str = ""
    enabled: bool = True
    # 运行时状态（注入器维护，非配置字段）
    remaining: int = field(init=False)
    armed_at: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.remaining = self.count

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FaultSpec:
        """从配置 dict 解析并校验，非法配置抛 ValueError。"""
        if not isinstance(data, dict):
            raise ValueError(f"故障配置必须是 JSON 对象，收到 {type(data).__name__}")

        raw_type = data.get("type")
        try:
            ftype = FaultType(str(raw_type).strip())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"未知故障类型: {raw_type!r}（合法值: {[t.value for t in FaultType]}）"
            ) from exc

        raw_mode = data.get("mode", FaultMode.ONCE.value)
        try:
            fmode = FaultMode(str(raw_mode).strip().lower())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"未知故障模式: {raw_mode!r}（合法值: {[m.value for m in FaultMode]}）"
            ) from exc

        probability = _coerce_float(data.get("probability", 1.0), "probability")
        if not 0.0 < probability <= 1.0:
            raise ValueError(f"probability 必须在 (0, 1]，收到 {probability}")

        delay = _coerce_float(data.get("delay", 0.0), "delay")
        if delay < 0:
            raise ValueError(f"delay 不能为负，收到 {delay}")

        duration = _coerce_float(data.get("duration", 0.0), "duration")
        if duration < 0:
            raise ValueError(f"duration 不能为负，收到 {duration}")

        count = data.get("count", 1)
        if isinstance(count, bool):
            raise ValueError(f"count 必须是整数，收到布尔值 {count!r}")
        try:
            count = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"count 必须是整数，收到 {count!r}") from exc
        if count < 1:
            raise ValueError(f"count 必须 ≥1，收到 {count}")

        message = str(data.get("message") or "")
        enabled = bool(data.get("enabled", True))

        return cls(
            type=ftype,
            mode=fmode,
            probability=probability,
            delay=delay,
            duration=duration,
            count=count,
            message=message,
            enabled=enabled,
        )
