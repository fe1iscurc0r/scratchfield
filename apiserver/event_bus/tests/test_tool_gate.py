"""W119-03 验收：工具调用安全门（veto / 放行 / 审计 / 熔断 / audit_only）。

对应工单验收：
- 敏感工具被拒（veto 生效且注明原因）；非敏感工具正常执行
- audit_only 模式只记不拦
- 熔断触发（模拟连续失败 → veto）
- audit ndjson 有记录（pre/post 两相）
- 工具回路（execute_tool_calls）实际尊重 veto
"""
from __future__ import annotations

import asyncio
import json

import pytest

from apiserver.event_bus import InProcessEventBus, Topics
from apiserver.event_bus.tool_gate import (
    ToolGateRuntime,
    register_tool_gates,
    reset_tool_gate_runtime_for_tests,
)


class Cfg:
    """配置替身（不依赖 config.json）。"""

    def __init__(self, **kw):
        self.enabled = kw.get("enabled", True)
        self.audit_only = kw.get("audit_only", False)
        self.sensitive_tools = kw.get("sensitive_tools", ["exec", "write", "mcp__vulnclaw__vulnclaw_invoke"])
        self.sensitive_keywords = kw.get("sensitive_keywords", ["shell", "ssh", "scp"])
        self.allowlist = kw.get("allowlist", [])
        self.breaker_threshold = kw.get("breaker_threshold", 3)
        self.breaker_window_seconds = kw.get("breaker_window_seconds", 60)


def _setup(tmp_path, monkeypatch, **cfg_kw):
    """建总线 + 运行时装门，并把审计路径重定向到 tmp。"""
    from apiserver.event_bus import tool_gate as gate_mod

    monkeypatch.setattr(gate_mod, "_audit_path", lambda: tmp_path / "audit" / "tool_calls.ndjson")
    bus = InProcessEventBus()
    runtime = ToolGateRuntime(Cfg(**cfg_kw), bus=bus)
    reset_tool_gate_runtime_for_tests(runtime)
    register_tool_gates(bus)
    return bus, runtime


def _audit_lines(tmp_path):
    path = tmp_path / "audit" / "tool_calls.ndjson"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sensitive_tool_vetoed_with_reason(tmp_path, monkeypatch):
    bus, runtime = _setup(tmp_path, monkeypatch)

    result = bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "exec"}, final=lambda: "EXECUTED")
    assert isinstance(result, dict) and result["veto"] is True
    assert "exec" in result["reason"] and result["gate"] == "sensitive"
    assert runtime.veto_count == 1

    # 关键字族同样命中
    hit, reason = runtime.is_sensitive("mcp__something__shell_exec")
    assert hit and "shell" in reason


def test_non_sensitive_and_allowlist_pass(tmp_path, monkeypatch):
    bus, _ = _setup(tmp_path, monkeypatch, allowlist=["write"])

    assert bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "read"}, final=lambda: "EXECUTED") == "EXECUTED"
    # allowlist 覆盖黑名单
    assert bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "write"}, final=lambda: "EXECUTED") == "EXECUTED"
    # 未放行的敏感工具仍被拦
    assert isinstance(
        bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "exec"}, final=lambda: "EXECUTED"), dict
    )


def test_audit_records_pre_phase(tmp_path, monkeypatch):
    bus, _ = _setup(tmp_path, monkeypatch)
    bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "read", "session_id": "s1"}, final=lambda: "EXECUTED")
    bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "exec", "session_id": "s1"}, final=lambda: "EXECUTED")

    lines = _audit_lines(tmp_path)
    assert any(item.get("phase") == "pre" and item.get("tool") == "read" for item in lines)
    assert any(item.get("phase") == "veto" and item.get("tool") == "exec" for item in lines)

    # post 相由 record_tool_result 写入
    from apiserver.event_bus.tool_gate import record_tool_result

    record_tool_result("read", True, duration_s=0.25)
    post = [item for item in _audit_lines(tmp_path) if item.get("phase") == "post"]
    assert post and post[-1]["tool"] == "read" and post[-1]["ok"] is True


def test_breaker_trips_after_consecutive_failures(tmp_path, monkeypatch):
    bus, runtime = _setup(tmp_path, monkeypatch, breaker_threshold=3)
    from apiserver.event_bus.tool_gate import record_tool_result

    for _ in range(2):
        record_tool_result("mcp__x__probe", False)
    assert bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "mcp__x__probe"}, final=lambda: "EXECUTED") == "EXECUTED"

    record_tool_result("mcp__x__probe", False)  # 第 3 次 → 达阈值
    result = bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "mcp__x__probe"}, final=lambda: "EXECUTED")
    assert isinstance(result, dict) and result["gate"] == "breaker" and "熔断" in result["reason"]

    # 成功一次即清零
    record_tool_result("mcp__x__probe", True)
    assert bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "mcp__x__probe"}, final=lambda: "EXECUTED") == "EXECUTED"


def test_audit_only_mode_does_not_block(tmp_path, monkeypatch):
    bus, runtime = _setup(tmp_path, monkeypatch, audit_only=True)

    assert bus.waterfall(Topics.TOOL_PRE_EXECUTE, {"tool": "exec"}, final=lambda: "EXECUTED") == "EXECUTED"
    assert runtime.veto_count == 0
    assert runtime.audit_only_skips == 1
    assert any(item.get("phase") == "sensitive_skip" for item in _audit_lines(tmp_path))


def test_execute_tool_calls_respects_veto_and_records_result(tmp_path, monkeypatch):
    """工具回路集成：veto 的工具不执行；放行的执行并回填熔断计数。"""
    bus, _ = _setup(tmp_path, monkeypatch)

    import apiserver.agentic_tool_loop as loop
    import apiserver.event_bus as bus_pkg

    monkeypatch.setattr(bus_pkg, "get_bus", lambda: bus)

    calls: list[str] = []

    async def fake_dispatch(call, session_id, source_agent_id):
        calls.append(str(call.get("tool_name")))
        return {
            "tool_call": call,
            "result": "ok",
            "status": "success",
            "service_name": call.get("agentType", ""),
            "tool_name": str(call.get("tool_name")),
        }

    monkeypatch.setattr(loop, "_dispatch_one_call", fake_dispatch)

    results = asyncio.run(
        loop.execute_tool_calls(
            [
                {"agentType": "mcp", "tool_name": "exec"},
                {"agentType": "mcp", "tool_name": "read"},
            ],
            "s1",
        )
    )
    assert calls == ["read"]  # exec 被拦，未执行
    by_tool = {r["tool_name"]: r for r in results}
    assert by_tool["exec"]["status"] == "error"
    assert "拦截" in by_tool["exec"]["result"]
    assert by_tool["read"]["status"] == "success"

    # 放行的调用回填了 post 审计
    assert any(item.get("phase") == "post" and item.get("tool") == "read" for item in _audit_lines(tmp_path))
