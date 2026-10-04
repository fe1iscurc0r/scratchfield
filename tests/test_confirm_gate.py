"""W121-03 验收：对话流确认门（plan 展示 + diff 确认才写）。

覆盖：拦截并返回 diff / 确认后放行 / 拒绝后不写盘 / 关开关直接执行 / audit 记录 / [PLAN] 抽取。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json
from pathlib import Path

import pytest

from apiserver.event_bus import confirm_gate as cg
from apiserver.event_bus.bus import InProcessEventBus
from mcpserver.code_workspace import sandbox
from mcpserver.code_workspace.tools import CodeWorkspaceBridge


class _Cfg:
    def __init__(self, plan_confirm: bool = True) -> None:
        self.plan_confirm = plan_confirm


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """工作区与审计都重定向到 tmp；待确认状态每例重置。"""
    monkeypatch.setattr(sandbox, "workspace_root", lambda: tmp_path / "code_workspace")
    monkeypatch.setattr(sandbox, "_audit_path", lambda: tmp_path / "audit" / "code_workspace.ndjson")
    records: list[dict] = []
    runtime = cg.ConfirmGateRuntime(_Cfg(True), audit=records.append)
    cg.reset_confirm_gate_for_tests(runtime)
    yield runtime, records, tmp_path
    cg.reset_confirm_gate_for_tests(None)


def _event(tool: str, args: dict, session_id: str = "s1") -> dict:
    return {"tool": tool, "agent_type": "mcp", "session_id": session_id, "args": args}


def _next_called_flag() -> tuple[list[bool], callable]:
    called = []

    def _nxt():
        called.append(True)
        return None

    return called, _nxt


# ---------------------------------------------------------------------------
# 拦截 / 确认 / 拒绝
# ---------------------------------------------------------------------------


def test_file_write_intercepted_with_diff(gate):
    """第一次 file_write 被拦下，返回体里带 diff 预览与待确认信息。"""
    runtime, records, _tmp = gate
    called, nxt = _next_called_flag()

    verdict = runtime.gate(_event("file_write", {"path": "a.py", "content": "print(1)\n"}), nxt)

    assert verdict["veto"] is True and verdict["gate"] == "confirm"
    assert "等待用户确认" in verdict["reason"]
    assert "+print(1)" in verdict["reason"], "拦截原因里必须带 diff 预览"
    assert verdict["pending_confirm"]["path"] == "a.py"
    assert not called, "拦截时不得放行到执行器"

    pending = runtime.pending("s1")
    assert len(pending) == 1 and pending[0]["tool"] == "file_write"
    assert any(r.get("decision") == "pending" for r in records), "audit 必须记录待确认"


def test_confirm_then_release_and_write_lands(gate):
    """确认后同签名调用放行，文件真的落盘（mtime 变化）。"""
    runtime, records, tmp = gate
    args = {"path": "a.py", "content": "print(1)\n", "session_id": "s1"}
    called, nxt = _next_called_flag()

    assert runtime.gate(_event("file_write", args), nxt)["veto"] is True
    target = sandbox.session_workspace("s1") / "a.py"
    assert not target.exists(), "确认前不得写盘"

    assert runtime.decide("s1", "confirm") == 1
    assert runtime.pending("s1") == []

    released = runtime.gate(_event("file_write", args), nxt)
    assert released is None and called == [True], "确认后必须放行"
    # 放行后由工具自己写（这里模拟工具执行）
    CodeWorkspaceBridge().file_write("a.py", "print(1)\n", session_id="s1")
    assert target.exists() and target.read_text(encoding="utf-8") == "print(1)\n"
    assert any(r.get("decision") == "confirmed_release" for r in records)

    # 一次性放行：同签名第二次又要确认
    called2, nxt2 = _next_called_flag()
    assert runtime.gate(_event("file_write", args), nxt2)["veto"] is True
    assert not called2


def test_reject_keeps_file_untouched(gate):
    """拒绝后同签名调用被拦下（原因写明用户拒绝），文件 mtime 不变。"""
    runtime, records, _tmp = gate
    args = {"path": "b.py", "content": "x = 1\n", "session_id": "s1"}
    _, nxt = _next_called_flag()

    runtime.gate(_event("file_write", args), nxt)
    assert runtime.decide("s1", "reject") == 1

    called, nxt2 = _next_called_flag()
    verdict = runtime.gate(_event("file_write", args), nxt2)
    assert verdict["veto"] is True and "用户拒绝" in verdict["reason"]
    assert not called

    target = sandbox.session_workspace("s1") / "b.py"
    assert not target.exists(), "拒绝后不得写盘"
    assert any(r.get("decision") == "reject_all" for r in records)

    # 拒绝也是一次性：第三次再调又回到「等待确认」
    assert runtime.gate(_event("file_write", args), nxt2)["veto"] is True


def test_chat_keyword_confirm_and_reject(gate):
    """对话关键词确认/拒绝（仅在该会话有 pending 时生效）。"""
    runtime, _records, _tmp = gate
    _, nxt = _next_called_flag()

    # 没有 pending 时，普通「继续」不触发任何决策
    assert runtime.observe_user_message("s1", "继续") is None

    runtime.gate(_event("file_write", {"path": "c.py", "content": "c\n"}), nxt)
    assert runtime.observe_user_message("s1", "好的，继续执行") == "confirm"
    assert runtime.observe_user_message("s1", "继续") is None, "决策后 pending 已清空"

    runtime.gate(_event("file_write", {"path": "d.py", "content": "d\n"}), nxt)
    assert runtime.observe_user_message("s1", "算了，先别改") == "reject"


def test_file_edit_also_gated_and_session_scoped(gate):
    """file_edit 同样过门；待确认状态按会话隔离。"""
    runtime, _records, _tmp = gate
    bridge = CodeWorkspaceBridge()
    bridge.file_write("e.py", "value = 1\n", session_id="s1")

    _, nxt = _next_called_flag()
    verdict = runtime.gate(
        _event("file_edit", {"path": "e.py", "old": "value = 1", "new": "value = 2", "session_id": "s1"}), nxt
    )
    assert verdict["veto"] is True
    assert "-value = 1" in verdict["reason"] and "+value = 2" in verdict["reason"]
    assert runtime.pending("s1") and not runtime.pending("other-session")

    # 别的会话确认不影响本会话
    runtime.clear("other-session")
    assert runtime.pending("s1")


def test_non_write_tools_pass_through(gate):
    """非写工具（code_exec / test_run / file_read）不受确认门影响。"""
    runtime, _records, _tmp = gate
    for tool in ("code_exec", "test_run", "file_read", "shell_exec"):
        called, nxt = _next_called_flag()
        assert runtime.gate(_event(tool, {"code": "print(1)"}), nxt) is None
        assert called == [True], tool


# ---------------------------------------------------------------------------
# 开关
# ---------------------------------------------------------------------------


def test_switch_off_executes_directly(gate, monkeypatch):
    """plan_confirm=false → 整门旁路（直接执行），审计仍由审计门负责。"""
    runtime, _records, _tmp = gate
    monkeypatch.setattr(runtime, "_cfg", _Cfg(False))
    assert runtime.enabled is False

    called, nxt = _next_called_flag()
    verdict = runtime.gate(_event("file_write", {"path": "f.py", "content": "f\n"}), nxt)
    assert verdict is None and called == [True]
    assert runtime.pending("s1") == []


# ---------------------------------------------------------------------------
# 总线挂载
# ---------------------------------------------------------------------------


def test_registered_on_tool_pre_execute_waterfall(gate):
    """挂到 TOOL_PRE_EXECUTE waterfall 后，veto 能沿洋葱链传到调用方。"""
    from apiserver.event_bus.topics import Topics

    runtime, _records, _tmp = gate
    bus = InProcessEventBus()
    cg.register_confirm_gate(bus)

    verdict = bus.waterfall(
        Topics.TOOL_PRE_EXECUTE,
        _event("file_write", {"path": "g.py", "content": "g\n"}),
        final=lambda: None,
    )
    assert isinstance(verdict, dict) and verdict.get("veto") is True
    assert verdict.get("gate") == "confirm"

    allowed = bus.waterfall(
        Topics.TOOL_PRE_EXECUTE, _event("code_exec", {"code": "print(1)"}), final=lambda: None
    )
    assert allowed is None, "非写工具应当放行到链尾"


# ---------------------------------------------------------------------------
# 预览失败 / [PLAN]
# ---------------------------------------------------------------------------


def test_preview_error_does_not_create_pending(gate):
    """预览阶段就失败（路径穿越）→ 直接把错误给模型，不挂待确认。"""
    runtime, records, _tmp = gate
    called, nxt = _next_called_flag()
    verdict = runtime.gate(_event("file_write", {"path": "../escape.py", "content": "x\n"}), nxt)
    assert verdict["veto"] is True and "无法应用" in verdict["reason"]
    assert runtime.pending("s1") == []
    assert any(r.get("decision") == "preview_error" for r in records)


def test_extract_plan_section():
    from apiserver.agentic_tool_loop import extract_plan_section

    text = "我打算这么做：\n[PLAN]\n1. 改 calc.py 的 add\n2. 跑 tests/test_calc.py\n[/PLAN]\n先给你看计划。"
    plan = extract_plan_section(text)
    assert plan and "改 calc.py" in plan and "跑 tests/test_calc.py" in plan
    assert extract_plan_section("没有计划段") is None
    # 流式未闭合：取到末尾
    assert "只到一半" in (extract_plan_section("[PLAN]\n只到一半") or "")
