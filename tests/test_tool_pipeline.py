"""W124-03 验收：工具三段管道（guard → pre-execute → execute → post-execute）。

覆盖：非法参数被 guard 拦（不进执行、不写盘）/ 三段顺序 / post-execute 事件字段完整 /
失败统计驱动熔断 / 正交字段（timeout-aborted-exit 分开）/ guard 规则（路径·语言·manifest·shell）。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json

import pytest

from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间
from apiserver.event_bus import tool_pipeline
from apiserver.event_bus.topics import Topics
from mcpserver.code_workspace import sandbox


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "workspace_root", lambda: tmp_path / "code_workspace")
    return tmp_path


@pytest.fixture()
def audits(monkeypatch):
    records: list[dict] = []
    monkeypatch.setattr(tool_pipeline, "_audit", records.append)
    return records


# ---------------------------------------------------------------------------
# guard 规则
# ---------------------------------------------------------------------------


def test_guard_blocks_path_traversal(ws, audits):
    """非法 file_write 路径被 guard 拦下，且不写盘。"""
    verdict = tool_pipeline.guard_tool("file_write", {"path": "../escape.py", "content": "x = 1"})
    assert verdict and verdict["error"] == "invalid_args"
    assert "path_traversal" in verdict["reason"] or "绝对" in verdict["reason"] or "逃逸" in verdict["reason"]
    assert not (ws / "escape.py").exists()

    ok = tool_pipeline.guard_tool("file_write", {"path": "pkg/main.py", "content": "x = 1"})
    assert ok is None, "工作区内路径应放行"
    assert audits and audits[-1]["phase"] == "guard" and audits[-1]["result"] == "rejected"


def test_guard_checks_language_and_manifest(ws, audits):
    bad_lang = tool_pipeline.guard_tool("code_exec", {"code": "print(1)", "language": "ruby"})
    assert bad_lang and "language" in bad_lang["reason"]
    assert tool_pipeline.guard_tool("code_exec", {"code": "print(1)", "language": "python"}) is None

    missing = tool_pipeline.guard_tool("file_write", {"content": "no path"})
    assert missing and "path" in missing["reason"]
    assert tool_pipeline.guard_tool("shell_exec", {"command": "   "}) is not None
    assert tool_pipeline.guard_tool("shell_exec", {"command": "ls"}) is None
    assert tool_pipeline.guard_tool("shell_exec", {"command": "rm -rf /"}) is not None
    assert tool_pipeline.guard_tool("test_run", {}) is None, "无规则工具放行"


def test_guard_rules_table_and_summary():
    summary = tool_pipeline.pipeline_summary()
    assert summary["stages"] == ["guard", "pre-execute", "execute", "post-execute"]
    assert summary["topics"]["guard"] == "lumo.tool.guard"
    assert summary["topics"]["post_execute"] == "lumo.tool.post-execute"
    assert "_guard_path" in summary["guard_rules"]["file_write"]
    assert "_guard_manifest_params" in summary["guard_rules"]["__all__"]


def test_guard_registered_on_bus(ws, monkeypatch):
    from apiserver.event_bus.bus import InProcessEventBus

    bus = InProcessEventBus()
    seen: list[dict] = []
    monkeypatch.setattr(tool_pipeline, "_audit", seen.append)
    disposer = tool_pipeline.register_guard(bus)

    bad = bus.bail(Topics.TOOL_GUARD, {"tool": "file_write", "args": {"path": "/etc/passwd"}})
    assert isinstance(bad, dict) and bad.get("error") == "invalid_args"
    good = bus.bail(Topics.TOOL_GUARD, {"tool": "file_write", "args": {"path": "a.py"}})
    assert good is None
    disposer()
    assert bus.bail(Topics.TOOL_GUARD, {"tool": "file_write", "args": {"path": "/etc/passwd"}}) is None


# ---------------------------------------------------------------------------
# 三段顺序
# ---------------------------------------------------------------------------


def test_pipeline_order_guard_then_pre_then_execute(ws, monkeypatch, audits):
    """顺序断言：guard → pre-execute → execute；guard 拒了就不进后面两步。"""
    order: list[str] = []
    real_guard = tool_pipeline.guard_tool

    def _guard_spy(tool, args):
        order.append("guard")
        return real_guard(tool, args)

    monkeypatch.setattr(tool_pipeline, "guard_tool", _guard_spy)

    async def _gate(call, session_id, source_agent_id):
        order.append("pre-execute")
        return None

    monkeypatch.setattr(atl, "_run_tool_gate", _gate)

    async def _dispatch(call, session_id, source_agent_id):
        order.append("execute")
        return {"result": "ok", "status": "success", "service_name": "code_workspace",
                "tool_name": "file_write"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _dispatch)

    bad = asyncio.run(atl.execute_tool_calls(
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "file_write",
          "path": "../escape.py", "content": "x"}], "s1"))
    assert bad[0]["status"] == "error" and "参数不合法" in bad[0]["result"]
    assert order == ["guard"], "被 guard 拒后不得进 pre-execute / execute"

    order.clear()
    good = asyncio.run(atl.execute_tool_calls(
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "file_write",
          "path": "ok.py", "content": "x"}], "s1"))
    assert good[0]["status"] == "success"
    assert order == ["guard", "pre-execute", "execute"], order


# ---------------------------------------------------------------------------
# post-execute
# ---------------------------------------------------------------------------


def test_post_execute_event_fields_and_audit(ws, monkeypatch, audits):
    """执行后广播的事实：字段齐全，且外层 success/返回体 ok=false 时事实为失败。"""
    captured: list[tuple[str, dict]] = []

    class _Bus:
        def emit(self, topic, event):
            captured.append((topic, event))

    monkeypatch.setattr("apiserver.event_bus.get_bus", lambda: _Bus())

    async def _gate(call, session_id, source_agent_id):
        return None

    monkeypatch.setattr(atl, "_run_tool_gate", _gate)

    async def _dispatch(call, session_id, source_agent_id):
        return {"result": json.dumps({"ok": False, "exit_code": 3, "stderr": "boom"}),
                "status": "success", "service_name": "code_workspace", "tool_name": "code_exec"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _dispatch)
    asyncio.run(atl.execute_tool_calls(
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec",
          "code": "print(1)"}], "s1"))

    assert captured, "执行后必须发 post-execute 事实"
    topic, event = captured[0]
    assert topic == "lumo.tool.post-execute"
    assert event["tool"] == "code_exec" and event["session_id"] == "s1"
    assert event["duration"] >= 0
    assert event["ok"] is False, "外层 success 但返回体 ok=false → 事实为失败"
    assert event["exit_code"] == 3 and event["aborted"] is False
    assert any(r.get("phase") == "post_execute" for r in audits), "post-execute 必须落审计"


def test_normalize_result_orthogonal_fields(ws):
    timeout = tool_pipeline.normalize_result(
        {"result": "执行超时（>10s），已终止", "status": "error", "error": "timeout"}, duration_s=10.1
    )
    assert timeout["ok"] is False and timeout["aborted"] is True
    assert timeout["error"] == "timeout" and timeout["exit_code"] is None
    assert timeout["duration"] == 10.1

    ok = tool_pipeline.normalize_result(
        {"result": json.dumps({"ok": True, "exit_code": 0, "passed": 2}), "status": "success"},
        duration_s=0.42,
    )
    assert ok["ok"] is True and ok["exit_code"] == 0 and ok["aborted"] is False

    killed = tool_pipeline.normalize_result(
        {"result": json.dumps({"signal": "SIGKILL", "exit_code": 137}), "status": "error"},
        duration_s=1.0,
    )
    assert killed["signal"] == "SIGKILL" and killed["exit_code"] == 137, "signal 与 exit 分开"


def test_post_execute_feeds_breaker(ws, monkeypatch):
    """post-execute 的失败统计要能驱动卷119 熔断门。"""
    from apiserver.event_bus.tool_gate import ToolGateRuntime, reset_tool_gate_runtime_for_tests

    runtime = ToolGateRuntime(cfg=None)
    runtime.audit = lambda record: None  # 不落盘
    reset_tool_gate_runtime_for_tests(runtime)
    monkeypatch.setattr(tool_pipeline, "_audit", lambda record: None)

    for _ in range(5):
        tool_pipeline.emit_post_execute(
            tool="flaky_tool", args={}, result={"result": "boom", "status": "error"},
            duration_s=0.1, session_id="s1", ok=False,
        )
    tripped, streak = runtime.breaker_tripped("flaky_tool")
    assert tripped and streak >= 5, "连续失败应触发熔断"

    tool_pipeline.emit_post_execute(
        tool="flaky_tool", args={}, result={"result": "ok", "status": "success"},
        duration_s=0.1, session_id="s1", ok=True,
    )
    assert runtime.breaker_tripped("flaky_tool")[1] == 0, "成功应清零失败计数"
    reset_tool_gate_runtime_for_tests(None)
