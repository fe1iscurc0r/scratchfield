"""故障注入框架单元测试（E-01）。

覆盖：每类故障注入生效 / 参数解析 / 随机模式统计 / 组合场景 / 渐进恶化 /
恢复（故障解除后调用正常）/ 坏配置报错 / 拦截器装卸。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from mcpserver.fault_inject import (
    DisconnectError,
    FaultInjectionError,
    FaultInjector,
    FaultMode,
    FaultSpec,
    FaultType,
    OrchestratorInterruptError,
    RateLimitError,
    ToolError,
    ToolTimeoutError,
    load_scenario,
)

HERE = Path(__file__).resolve().parent
PKG_DIR = HERE.parent / "fault_inject"


def _run(coro):
    return asyncio.run(coro)


async def _echo(task: dict | None = None, **kwargs) -> str:
    if task is None:
        task = kwargs
    return json.dumps({"status": "ok", "message": task.get("message", "")}, ensure_ascii=False)


# 异常型故障：类型 → 期望异常
_EXCEPTION_FAULTS = [
    (FaultType.TOOL_TIMEOUT, ToolTimeoutError),
    (FaultType.TOOL_ERROR, ToolError),
    (FaultType.MCP_RATE_LIMIT, RateLimitError),
    (FaultType.MCP_DISCONNECT, DisconnectError),
    (FaultType.ORCHESTRATOR_INTERRUPT, OrchestratorInterruptError),
]


@pytest.mark.parametrize("ftype,exc_cls", _EXCEPTION_FAULTS)
def test_exception_faults_raise(ftype, exc_cls):
    """每类异常型故障注入后，调用应抛出对应异常并计入统计。"""
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=ftype, mode=FaultMode.PERSISTENT))
    wrapped = inj.inject(_echo)

    with pytest.raises(exc_cls):
        _run(wrapped({"message": "hi"}))

    assert inj.stats()[ftype.value] == 1
    assert inj.stats()["total_calls"] == 1


def test_slow_fault_adds_latency():
    """mcp_slow 应引入延迟但不抛异常。"""
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.MCP_SLOW, mode=FaultMode.PERSISTENT, delay=0.15))
    wrapped = inj.inject(_echo)

    t0 = time.monotonic()
    result = _run(wrapped({"message": "hi"}))
    elapsed = time.monotonic() - t0

    assert json.loads(result)["status"] == "ok"
    assert elapsed >= 0.1  # 留余量，避免 Windows 定时器精度导致的偶发误差


def test_prefix_perturb_preserves_core():
    """prefix_perturb 只扰动 message 前缀，核心语义本体保留。"""
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.PREFIX_PERTURB, mode=FaultMode.PERSISTENT, message="noise"))
    wrapped = inj.inject(_echo)

    payload = json.loads(_run(wrapped({"message": "core"})))

    assert payload["status"] == "ok"
    assert payload["message"].startswith("[prefix_perturb]")
    assert payload["message"].endswith("core")


def test_faultspec_parameter_parsing():
    """参数解析：delay/probability/duration/count/message 正确，缺省值合理。"""
    spec = FaultSpec.from_dict({
        "type": "mcp_slow", "mode": "random",
        "probability": 0.4, "delay": 1.5, "duration": 3.0, "count": 5, "message": "m",
    })
    assert spec.type == FaultType.MCP_SLOW
    assert spec.mode == FaultMode.RANDOM
    assert spec.probability == pytest.approx(0.4)
    assert spec.delay == pytest.approx(1.5)
    assert spec.duration == pytest.approx(3.0)
    assert spec.count == 5
    assert spec.message == "m"

    default = FaultSpec.from_dict({"type": "tool_error"})
    assert default.mode == FaultMode.ONCE
    assert default.probability == 1.0
    assert default.count == 1
    assert default.delay == 0.0


def test_random_mode_statistics():
    """随机模式：多次调用后实测注入率应逼近配置概率，统计一致。"""
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_ERROR, mode=FaultMode.RANDOM, probability=0.5))
    wrapped = inj.inject(_echo)

    async def _loop() -> int:
        injected = 0
        for _ in range(2000):
            try:
                await wrapped({"message": "x"})
            except ToolError:
                injected += 1
        return injected

    injected = _run(_loop())
    rate = injected / 2000

    assert 0.40 < rate < 0.60
    assert inj.stats()["tool_error"] == injected
    assert inj.stats()["total_calls"] == 2000


def test_combined_scenario():
    """组合场景：逐次触发 slow → rate_limit → disconnect → tool_error。"""
    inj = load_scenario("combined")
    wrapped = inj.inject(_echo)

    async def _seq() -> list[str]:
        effects = []
        for _ in range(4):
            try:
                await wrapped({"message": "x"})
                effects.append("ok")
            except FaultInjectionError as exc:
                effects.append(exc.fault_type)
        return effects

    effects = _run(_seq())

    assert effects[0] == "ok"  # mcp_slow 不抛异常
    assert effects[1] == "mcp_rate_limit"
    assert effects[2] == "mcp_disconnect"
    assert effects[3] == "tool_error"


def test_progressive_scenario():
    """渐进恶化场景：延迟递增后转为断连（一次→持续）。"""
    inj = load_scenario("progressive")
    wrapped = inj.inject(_echo)

    async def _seq() -> list[str]:
        effects = []
        for _ in range(5):
            try:
                await wrapped({"message": "x"})
                effects.append("ok")
            except FaultInjectionError as exc:
                effects.append(exc.fault_type)
        return effects

    effects = _run(_seq())

    assert effects[:3] == ["ok", "ok", "ok"]  # 三次 mcp_slow 正常返回
    assert effects[3] == "mcp_disconnect"
    assert effects[4] == "mcp_disconnect"


def test_recovery_after_fault_cleared():
    """故障解除后调用链应恢复正常。"""
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_ERROR, mode=FaultMode.PERSISTENT))
    wrapped = inj.inject(_echo)

    with pytest.raises(ToolError):
        _run(wrapped({"message": "x"}))

    inj.clear()
    payload = json.loads(_run(wrapped({"message": "ok"})))
    assert payload["status"] == "ok"


@pytest.mark.parametrize("cfg", [
    {"faults": [{"type": "not_a_fault"}]},
    {"faults": [{"type": "tool_error", "mode": "sometimes"}]},
    {"faults": [{"type": "tool_error", "probability": 1.5}]},
    {"faults": [{"type": "tool_error", "probability": 0}]},
    {"faults": [{"type": "mcp_slow", "delay": -1}]},
    {"faults": [{"type": "tool_error", "count": 0}]},
    {"faults": ["tool_error"]},
    {"faults": "tool_error"},
])
def test_bad_config_raises(cfg):
    """坏配置应抛 ValueError。"""
    with pytest.raises(ValueError):
        FaultInjector(config=cfg)


def test_bad_config_string_raises():
    """非法内联配置字符串应抛 ValueError。"""
    with pytest.raises(ValueError):
        FaultInjector(config="this is not json or yaml {{{")


def test_load_config_from_json_file():
    """从 JSON 文件加载配置。"""
    inj = FaultInjector(config=PKG_DIR / "example_config.json")
    assert len(inj.faults()) == 3
    assert inj.faults()[0].type == FaultType.MCP_SLOW


def test_load_config_from_yaml_string():
    """从 YAML 字符串加载配置。"""
    yaml_cfg = "faults:\n  - type: tool_timeout\n    mode: persistent\n"
    inj = FaultInjector(config=yaml_cfg)
    assert len(inj.faults()) == 1
    assert inj.faults()[0].type == FaultType.TOOL_TIMEOUT


class _FakeManager:
    def __init__(self):
        self.calls = 0

    async def unified_call(self, service_name: str, tool_call: dict) -> str:
        self.calls += 1
        return json.dumps({"status": "ok"})


def test_interceptor_install_uninstall():
    """拦截器装卸：install 后注入生效，uninstall 后恢复正常。"""
    mgr = _FakeManager()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_ERROR, mode=FaultMode.PERSISTENT))
    inj.install(mgr, "unified_call")

    try:
        with pytest.raises(ToolError):
            _run(mgr.unified_call("svc", {"tool_name": "t"}))
    finally:
        inj.uninstall()

    payload = json.loads(_run(mgr.unified_call("svc", {"tool_name": "t"})))
    assert payload["status"] == "ok"
    assert mgr.calls == 1  # 注入期间 func 未执行；恢复后执行一次


def test_injector_context_manager_restores():
    """上下文管理器退出后自动恢复被拦截的方法。"""
    mgr = _FakeManager()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_TIMEOUT, mode=FaultMode.PERSISTENT))

    with inj:
        inj.install(mgr, "unified_call")
        with pytest.raises(ToolTimeoutError):
            _run(mgr.unified_call("svc", {}))

    payload = json.loads(_run(mgr.unified_call("svc", {})))
    assert payload["status"] == "ok"


class _Agent:
    name = "FakeAgent"

    def __init__(self):
        self.calls = 0

    async def handle_handoff(self, task: dict) -> str:
        self.calls += 1
        return json.dumps({"status": "ok"})


def test_wrap_agent():
    """wrap_agent 用 wrapper 方式包裹 handle_handoff，once 故障后恢复。"""
    agent = _Agent()
    inj = FaultInjector()
    inj.add_fault(FaultSpec(type=FaultType.TOOL_TIMEOUT, mode=FaultMode.ONCE))
    proxy = inj.wrap_agent(agent)

    with pytest.raises(ToolTimeoutError):
        _run(proxy.handle_handoff({"tool_name": "t"}))

    payload = json.loads(_run(proxy.handle_handoff({"tool_name": "t"})))
    assert payload["status"] == "ok"
    assert agent.calls == 1
