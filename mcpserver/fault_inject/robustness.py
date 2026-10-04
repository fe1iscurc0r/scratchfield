"""鲁棒性回归 harness（E-02）。

用 E-01 的故障注入框架给核心调用链注入各类故障，量化
「重试次数 / 退避重试 / 断连重连 / 降级路径 / 错误恢复」指标。
纯内存 mock MCP agent，不接真实网络。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .faults import (
    DisconnectError,
    FaultMode,
    FaultSpec,
    FaultType,
    OrchestratorInterruptError,
    RateLimitError,
    ToolError,
    ToolTimeoutError,
)
from .injector import FaultInjector

# 可重试的故障异常（超时 / 限流 / 断连）
RETRIABLE = (ToolTimeoutError, RateLimitError, DisconnectError)


@dataclass
class CallOutcome:
    """一次鲁棒性调用的结果指标。"""

    success: bool
    attempts: int
    elapsed: float
    degraded: bool = False
    error_type: str | None = None
    reconnect_count: int = 0
    waited: float = 0.0


class RobustCaller:
    """带重试/退避/重连/降级的调用器（参考实现，供回归测试量化指标）。

    - 超时（ToolTimeoutError）/ 限流（RateLimitError）：退避重试；
    - 断连（DisconnectError）：调用 reconnect 回调后重试；
    - 工具错误（ToolError）：不走重试，直接走降级路径；
    - 编排中断（OrchestratorInterruptError）：不重试，降级并保持状态一致。
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.01,
        backoff: float = 2.0,
        max_delay: float = 0.1,
        reconnect: Callable | None = None,
        degrade: Callable | None = None,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.reconnect = reconnect  # async callable() -> None
        self.degrade = degrade  # async callable(exc) -> fallback result

    async def call(self, func: Callable, *args: Any, **kwargs: Any):
        attempt = 0
        reconnect_count = 0
        waited = 0.0
        delay = self.base_delay
        t0 = time.monotonic()
        while True:
            attempt += 1
            try:
                result = await func(*args, **kwargs)
                return result, CallOutcome(
                    success=True,
                    attempts=attempt,
                    elapsed=time.monotonic() - t0,
                    reconnect_count=reconnect_count,
                    waited=waited,
                )
            except DisconnectError as exc:
                if attempt < self.max_attempts and self.reconnect is not None:
                    reconnect_count += 1
                    await self.reconnect()
                    waited += delay
                    await asyncio.sleep(delay)
                    delay = min(delay * self.backoff, self.max_delay)
                    continue
                return await self._degrade(exc, attempt, t0, reconnect_count, waited)
            except (ToolTimeoutError, RateLimitError) as exc:
                if attempt < self.max_attempts:
                    waited += delay
                    await asyncio.sleep(delay)
                    delay = min(delay * self.backoff, self.max_delay)
                    continue
                return await self._degrade(exc, attempt, t0, reconnect_count, waited)
            except ToolError as exc:
                return await self._degrade(exc, attempt, t0, reconnect_count, waited)
            except OrchestratorInterruptError as exc:
                return await self._degrade(exc, attempt, t0, reconnect_count, waited)

    async def _degrade(self, exc, attempt, t0, reconnect_count, waited):
        result = await self.degrade(exc) if self.degrade is not None else None
        return result, CallOutcome(
            success=False,
            attempts=attempt,
            elapsed=time.monotonic() - t0,
            degraded=True,
            error_type=getattr(exc, "fault_type", type(exc).__name__),
            reconnect_count=reconnect_count,
            waited=waited,
        )


class MockMCPAgent:
    """mock MCP server agent：echo 回传工具调用，不接真实网络。"""

    name = "Mock MCP Agent"

    def __init__(self, service_name: str = "mock_service"):
        self.service_name = service_name
        self.calls = 0
        self.interrupted_state: dict[str, Any] = {}

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        self.calls += 1
        self.interrupted_state["calls"] = self.calls
        return json.dumps(
            {
                "status": "ok",
                "service_name": self.service_name,
                "tool_name": task.get("tool_name", ""),
                "message": task.get("message", ""),
            },
            ensure_ascii=False,
        )


async def _run_fault_type(ftype: FaultType, trials: int) -> dict[str, Any]:
    """对单个故障类型跑 trials 次，聚合成功/重试/恢复/重连/降级指标。"""
    successes = 0
    degraded = 0
    total_attempts = 0
    recovery_times: list[float] = []
    reconnect_total = 0

    for _ in range(trials):
        agent = MockMCPAgent()
        injector = FaultInjector()
        injector.add_fault(FaultSpec(type=ftype, mode=FaultMode.ONCE))

        async def _reconnect() -> None:
            pass

        async def _degrade(exc: BaseException) -> str:
            return json.dumps(
                {"status": "degraded", "error": getattr(exc, "fault_type", str(exc))},
                ensure_ascii=False,
            )

        caller = RobustCaller(
            max_attempts=3, base_delay=0.005, backoff=2.0, max_delay=0.02,
            reconnect=_reconnect, degrade=_degrade,
        )
        wrapped = injector.inject(agent.handle_handoff)
        _, outcome = await caller.call(wrapped, {"tool_name": "echo", "message": "hi"})

        if outcome.success:
            successes += 1
            recovery_times.append(outcome.elapsed)
        if outcome.degraded:
            degraded += 1
        total_attempts += outcome.attempts
        reconnect_total += outcome.reconnect_count

    avg_attempts = round(total_attempts / trials, 3)
    return {
        "fault_type": ftype.value,
        "trials": trials,
        "success_rate": round(successes / trials, 4),
        "avg_retries": round(max(avg_attempts - 1, 0.0), 3),
        "avg_attempts": avg_attempts,
        "avg_recovery_s": round(sum(recovery_times) / len(recovery_times), 4) if recovery_times else 0.0,
        "reconnects": reconnect_total,
        "degraded": degraded,
    }


async def run_robustness_suite(trials: int = 20) -> list[dict[str, Any]]:
    """跑一遍全故障类型的鲁棒性回归，返回每类故障的指标行。"""
    rows = []
    for ftype in FaultType:
        rows.append(await _run_fault_type(ftype, trials))
    return rows
