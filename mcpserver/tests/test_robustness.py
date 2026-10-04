"""鲁棒性回归测试套件（E-02）。

用 E-01 故障注入框架给核心调用链注入各类故障，断言：
超时后重试成功 / 限流后退避重试 / 断连后重连 / 工具错误走降级路径 /
前缀扰动不影响核心语义 / 编排中断后状态一致。
全部标记 @pytest.mark.robustness，可单独跑。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from mcpserver.fault_inject import FaultInjector, FaultMode, FaultSpec, FaultType
from mcpserver.fault_inject.robustness import MockMCPAgent, RobustCaller


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.robustness
def test_timeout_then_retry_succeeds():
    """超时故障（once）应触发重试并最终成功。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_TIMEOUT, mode=FaultMode.ONCE))
    caller = RobustCaller(max_attempts=3, base_delay=0.005, max_delay=0.02)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo", "message": "hi"}))

    assert outcome.success is True
    assert outcome.attempts >= 2
    assert json.loads(result)["status"] == "ok"


@pytest.mark.robustness
def test_rate_limit_backoff_retries():
    """限流故障应退避后重试成功，且记录退避等待时间。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.MCP_RATE_LIMIT, mode=FaultMode.ONCE))
    caller = RobustCaller(max_attempts=3, base_delay=0.01, backoff=2.0, max_delay=0.05)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo", "message": "hi"}))

    assert outcome.success is True
    assert outcome.attempts >= 2
    assert outcome.waited >= 0.01  # 退避生效
    assert json.loads(result)["status"] == "ok"


@pytest.mark.robustness
def test_disconnect_then_reconnects():
    """断连故障应触发 reconnect 回调后重连成功。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.MCP_DISCONNECT, mode=FaultMode.ONCE))
    reconnects: list[int] = []

    async def _reconnect() -> None:
        reconnects.append(1)

    caller = RobustCaller(max_attempts=3, base_delay=0.005, max_delay=0.02, reconnect=_reconnect)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo", "message": "hi"}))

    assert outcome.success is True
    assert outcome.reconnect_count == 1
    assert len(reconnects) == 1
    assert json.loads(result)["status"] == "ok"


@pytest.mark.robustness
def test_tool_error_degrades():
    """工具错误不走重试，应走降级路径。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_ERROR, mode=FaultMode.PERSISTENT))

    async def _degrade(exc):
        return json.dumps({"status": "degraded", "error_type": getattr(exc, "fault_type", "")})

    caller = RobustCaller(degrade=_degrade)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo"}))

    assert outcome.success is False
    assert outcome.degraded is True
    assert outcome.error_type == "tool_error"
    assert json.loads(result)["status"] == "degraded"


@pytest.mark.robustness
def test_prefix_perturb_preserves_semantics():
    """前缀扰动不应影响核心路由与语义本体。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.PREFIX_PERTURB, mode=FaultMode.PERSISTENT, message="noise"))
    caller = RobustCaller()
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo", "message": "core"}))

    assert outcome.success is True
    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["tool_name"] == "echo"  # 核心路由字段不受扰动
    assert payload["message"].endswith("core")  # 语义本体保留


@pytest.mark.robustness
def test_orchestrator_interrupt_state_consistent():
    """编排中断应降级，且 agent 无部分写入（状态一致）。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.ORCHESTRATOR_INTERRUPT, mode=FaultMode.ONCE))

    async def _degrade(exc):
        return json.dumps({"status": "degraded", "error_type": getattr(exc, "fault_type", "")})

    caller = RobustCaller(degrade=_degrade)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo"}))

    assert outcome.degraded is True
    assert outcome.error_type == "orchestrator_interrupt"
    assert agent.calls == 0  # 中断发生在真正调用前
    assert agent.interrupted_state == {}
    assert json.loads(result)["status"] == "degraded"


@pytest.mark.robustness
def test_retriable_exhaustion_degrades():
    """持续限流超过最大尝试次数后应降级。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.MCP_RATE_LIMIT, mode=FaultMode.PERSISTENT))

    async def _degrade(exc):
        return json.dumps({"status": "degraded", "error_type": getattr(exc, "fault_type", "")})

    caller = RobustCaller(max_attempts=3, base_delay=0.005, max_delay=0.02, degrade=_degrade)
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo"}))

    assert outcome.degraded is True
    assert outcome.attempts == 3
    assert outcome.error_type == "mcp_rate_limit"
    assert agent.calls == 0  # 每次都注入，func 从未真正执行
    assert json.loads(result)["status"] == "degraded"


@pytest.mark.robustness
def test_slow_fault_does_not_retry():
    """mcp_slow 只是慢，不算错误，不应触发重试。"""
    agent = MockMCPAgent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.MCP_SLOW, mode=FaultMode.PERSISTENT, delay=0.01))
    caller = RobustCaller()
    wrapped = inj.inject(agent.handle_handoff)

    result, outcome = _run(caller.call(wrapped, {"tool_name": "echo"}))

    assert outcome.success is True
    assert outcome.attempts == 1
    assert json.loads(result)["status"] == "ok"
