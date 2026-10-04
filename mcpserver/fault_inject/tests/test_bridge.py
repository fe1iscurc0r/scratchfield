"""U-02 验收：fault_inject MCP 桥（FaultInjectBridge）+ manifest 挂载测试。

验收点（工单）：
1. inject 按预置场景/自定义配置注入并统计触发
2. run_robustness 全故障类型回归（指标行与代码枚举同源）
3. handle_handoff 剥离路由键、未知工具报错、坏参数报错
4. agent-manifest.json 可被 registry 发现，工具清单与实现一致
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.fault_inject.bridge import FaultInjectBridge
from mcpserver.fault_inject.faults import FaultType

REPO_ROOT = Path(__file__).resolve().parents[3]

_EXPECTED_TOOLS = {"inject", "run_robustness", "list_scenarios", "check"}


@pytest.fixture()
def bridge() -> FaultInjectBridge:
    return FaultInjectBridge()


def test_inject_scenario_persistent(bridge):
    """persistent 超时时每次调用都被注入（统计与注入器同源）。"""
    r = bridge.inject(scenario="single_timeout", calls=3)
    assert r["status"] == "ok"
    assert r["calls"] == 3 and r["success"] == 0
    assert r["injected"] == {"tool_timeout": 3}
    assert r["stats"]["total_calls"] == 3


def test_inject_custom_spec_once(bridge):
    """once 模式只触发一次，其余调用放行。"""
    r = bridge.inject(specs=[{"type": "tool_error", "mode": "once"}], calls=4)
    assert r["injected"] == {"tool_error": 1}
    assert r["success"] == 3


def test_inject_without_config_errors(bridge):
    assert bridge.inject()["status"] == "error"


def test_check_valid_and_invalid(bridge):
    r = bridge.check({"type": "mcp_rate_limit", "mode": "random", "probability": 0.5})
    assert r["status"] == "ok" and r["spec"]["type"] == "mcp_rate_limit"
    # 非法故障类型直接抛 ValueError（分发层包装为 error JSON）
    with pytest.raises(ValueError):
        bridge.check({"type": "not_a_fault"})


def test_run_robustness_rows_match_enum(bridge):
    """每类故障一行指标（与 FaultType 枚举同源）。"""
    r = asyncio.run(bridge.run_robustness(trials=2))
    assert r["status"] == "ok" and r["trials"] == 2
    assert len(r["rows"]) == len(FaultType)
    for row in r["rows"]:
        assert set(row) >= {"fault_type", "trials", "success_rate",
                            "avg_attempts", "degraded"}


def test_handoff_routing_and_unknown_tool(bridge):
    call = {
        "service_name": "fault_inject",
        "tool_name": "list_scenarios",
        "agentType": "mcp",
        "_tool_call_id": "x-2",
        "message": "路由噪声",
        "callback_url": "http://127.0.0.1/none",
        "params": {"arguments": "噪声键"},
    }
    out = json.loads(asyncio.run(bridge.handle_handoff(call)))
    assert out["status"] == "ok" and out["service"] == "fault_inject"
    assert "single_timeout" in out["scenarios"]
    # 未知工具 → error
    out = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert out["status"] == "error" and "不支持的工具" in out["error"]


def test_handoff_bad_spec_returns_error_json(bridge):
    """坏参数（非法故障类型）以 error JSON 返回，不抛裸异常。"""
    out = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "check", "spec": {"type": "bogus"}})))
    assert out["status"] == "error"


def test_registry_discovers_fault_inject():
    """硬验收：scan_and_register_mcp_agents 输出必须含 fault_inject。"""
    import os
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        from mcpserver.mcp_registry import scan_and_register_mcp_agents
        registered = scan_and_register_mcp_agents("mcpserver")
    finally:
        os.chdir(cwd)
    assert "fault_inject" in registered


def test_manifest_commands_match_bridge():
    manifest = json.loads(
        (Path(__file__).resolve().parent.parent / "agent-manifest.json")
        .read_text(encoding="utf-8"))
    assert manifest["name"] == "fault_inject"
    ep = manifest["entryPoint"]
    assert ep == {"module": "mcpserver.fault_inject.bridge",
                  "class": "FaultInjectBridge"}
    commands = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert commands == _EXPECTED_TOOLS
    import importlib
    inst = getattr(importlib.import_module(ep["module"]), ep["class"])()
    for c in _EXPECTED_TOOLS:
        assert callable(getattr(inst, c)), f"bridge 缺少工具实现: {c}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
