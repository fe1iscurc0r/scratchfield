"""W121-02 验收：Agentic Loop 工具结果回流 + 多轮迭代 + 步数上限 + 失败重试。

覆盖工单验收项：
- 结果回注：工具结果作为消息进入下一轮 LLM 上下文（「说了不做、做了不继续说」的根因项）
- 多轮：写代码 → 跑 → 报错 → 改 → 再跑，最终答复基于第二次运行结果
- max_steps 收敛：步数用尽后强制总结，且总结提示含「已完成 / 未完成」清单
- 失败重试：可重试失败重试到上限；策略类失败（白名单/安全门）不重试
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json
from typing import Any

import pytest

from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间

# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class _FakeLLM:
    """按脚本逐轮吐文本；记录每轮收到的 messages，供回注断言。"""

    def __init__(self, script: list[str]) -> None:
        self.script = script
        self.calls: list[list[dict[str, Any]]] = []
        self.tools_seen: list[Any] = []
        self.router_meta_seen: list[Any] = []  # W125-01：loop 会把 session/step 传给路由

    async def stream_chat_with_context(self, messages, temperature, model_override=None,
                                       tools=None, enable_thinking=None, router_meta=None):
        self.calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        self.tools_seen.append(tools)
        self.router_meta_seen.append(router_meta)
        idx = min(len(self.calls) - 1, len(self.script) - 1)
        for piece in (self.script[idx],):  # 单块流式
            yield _sse({"type": "content", "text": piece})


class _ScriptedCalls:
    """按轮次返回预置工具调用（替代文本解析）。"""

    def __init__(self, rounds: list[list[dict[str, Any]]]) -> None:
        self.rounds = rounds
        self.seen_texts: list[str] = []

    def __call__(self, text: str):
        self.seen_texts.append(text)
        idx = min(len(self.seen_texts) - 1, len(self.rounds) - 1)
        return text, self.rounds[idx]


def _tool_result(status: str, result: str, attempts: int = 1) -> dict[str, Any]:
    return {
        "tool_call": {"agentType": "mcp"},
        "result": result,
        "status": status,
        "service_name": "code_workspace",
        "tool_name": "code_exec",
        "attempts": attempts,
    }


def _events(chunks: list[str]) -> list[dict[str, Any]]:
    out = []
    for c in chunks:
        if c.startswith("data: "):
            body = c[6:].strip()
            if body and body != "[DONE]":
                try:
                    out.append(json.loads(body))
                except json.JSONDecodeError:
                    pass
    return out


@pytest.fixture(autouse=True)
def _quiet_side_effects(monkeypatch):
    """工具结果回填走内存替身，别往用户目录里写审计/指标。"""
    from apiserver.event_bus import tool_gate as gate_mod

    monkeypatch.setattr(gate_mod, "record_tool_result", lambda *a, **k: None, raising=False)
    try:
        from apiserver import telemetry as telemetry_mod

        monkeypatch.setattr(telemetry_mod, "record_tool_metric", lambda *a, **k: None, raising=False)
    except Exception:  # noqa: BLE001
        pass
    yield


# ---------------------------------------------------------------------------
# 多轮 + 结果回注
# ---------------------------------------------------------------------------


def test_tool_result_reinjected_next_round(monkeypatch):
    """工具结果必须作为消息回注，下一轮 LLM 能读到（否则就是「做了不继续说」）。"""
    llm = _FakeLLM(["我来跑一下代码。", "好，看到 NameError 了，我改成定义了变量。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)

    rounds = [
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}],
        [],  # 第二轮不再调工具 → 循环结束
    ]
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls(rounds))

    async def _fake_execute(calls, session_id, source_agent_id=None, max_retries=None):
        return [_tool_result("error", "Traceback: NameError: name 'foo' is not defined")]

    monkeypatch.setattr(atl, "execute_tool_calls", _fake_execute)

    messages = [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": "写个加法"}]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-reinject", max_rounds=4)))

    assert len(llm.calls) == 2, "应当发生第二轮 LLM 调用"
    second_round_text = json.dumps(llm.calls[1], ensure_ascii=False)
    assert "NameError: name 'foo' is not defined" in second_round_text, "工具结果未回注到下一轮上下文"
    assert "code_workspace" in second_round_text

    # 前端事件：tool_calls / tool_results / round_end 齐全
    types = [e.get("type") for e in _events(chunks)]
    assert "tool_calls" in types and "tool_results" in types and "round_end" in types
    assert _events(chunks)[-1].get("has_more") is False


def test_two_round_write_run_fix_run_flow(monkeypatch):
    """两轮闭环：跑失败 → 改 → 再跑成功，最终答复基于第二次运行结果。"""
    llm = _FakeLLM(["我先跑一版。", "第二次跑通了：输出 2。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)

    rounds = [
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}],
        [{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}],
        [],
    ]
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls(rounds))

    seen_inputs: list[str] = []

    async def _fake_execute(calls, session_id, source_agent_id=None, max_retries=None):
        text = json.dumps(session_id) + str(len(seen_inputs))
        seen_inputs.append(text)
        if len(seen_inputs) == 1:
            return [_tool_result("error", "SyntaxError: invalid syntax")]
        return [_tool_result("success", "stdout=2\nexit_code=0")]

    monkeypatch.setattr(atl, "execute_tool_calls", _fake_execute)

    messages = [{"role": "user", "content": "写个 1+1 并跑给我看"}]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-two-round", max_rounds=5)))

    assert len(seen_inputs) == 2, "应当执行两轮工具调用"
    final_text = "".join(
        e.get("text", "") for e in _events(chunks) if e.get("type") == "content"
    )
    assert "第二次跑通了" in final_text
    third_round_text = json.dumps(llm.calls[2], ensure_ascii=False)
    assert "stdout=2" in third_round_text and "SyntaxError" in third_round_text


# ---------------------------------------------------------------------------
# max_steps 收敛
# ---------------------------------------------------------------------------


def test_max_steps_converges_with_summary(monkeypatch):
    """步数用尽 → 强制收敛：总结轮不带 tools，提示含已完成/未完成清单。"""
    llm = _FakeLLM(["继续调工具", "继续调工具", "最终答复：已完成两步。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)

    always_tool = [[{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}]]
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls(always_tool))

    async def _fake_execute(calls, session_id, source_agent_id=None, max_retries=None):
        return [_tool_result("success", "stdout=2")]

    monkeypatch.setattr(atl, "execute_tool_calls", _fake_execute)

    messages = [{"role": "user", "content": "一直调工具"}]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-max-steps", max_rounds=2)))

    assert len(llm.calls) == 3, "2 步 + 1 总结轮"
    summary_prompt = llm.calls[-1][-1]["content"]
    assert "工具迭代已达上限（2 步）" in summary_prompt
    assert "已完成：" in summary_prompt and "未完成 / 失败：" in summary_prompt
    assert summary_prompt.count("- 第1轮") >= 1 and summary_prompt.count("- 第2轮") >= 1
    assert llm.tools_seen[-1] is None, "总结轮不得再传 tools"

    events = _events(chunks)
    assert any(e.get("type") == "round_start" and e.get("summary") for e in events)


def test_consecutive_failures_early_convergence(monkeypatch):
    """连续两轮全失败 → 提前收敛，且收敛提示把失败原因写清楚。"""
    llm = _FakeLLM(["调工具", "再调", "兜底答复"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)

    always_tool = [[{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "test_run"}]]
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls(always_tool))

    async def _fake_execute(calls, session_id, source_agent_id=None, max_retries=None):
        return [_tool_result("error", "1 failed, 0 passed")]

    monkeypatch.setattr(atl, "execute_tool_calls", _fake_execute)

    messages = [{"role": "user", "content": "跑到绿为止"}]
    asyncio.run(_collect(atl.run_agentic_loop(messages, "s-fail", max_rounds=8)))

    assert len(llm.calls) == 3, "两轮失败后立即收敛，不用跑到 max_steps=8"
    summary_prompt = llm.calls[-1][-1]["content"]
    assert "连续多轮工具调用全部失败" in summary_prompt
    assert "1 failed, 0 passed" in summary_prompt


# ---------------------------------------------------------------------------
# 失败重试
# ---------------------------------------------------------------------------


def test_retry_on_retryable_failure_then_success(monkeypatch):
    """超时类失败重试到上限内成功：attempts 反映真实尝试次数。"""
    monkeypatch.setattr(atl, "_run_tool_gate", _no_gate())

    attempts = {"n": 0}

    async def _flaky(call, session_id, source_agent_id):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return {"result": "执行超时（>10s），已终止", "status": "error",
                    "service_name": "code_workspace", "tool_name": "code_exec"}
        return {"result": "stdout=2", "status": "success",
                "service_name": "code_workspace", "tool_name": "code_exec"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _flaky)

    results = asyncio.run(
        atl.execute_tool_calls(
            [{"agentType": "mcp", "tool_name": "code_exec"}], "s-retry", max_retries=2
        )
    )
    assert results[0]["status"] == "success"
    assert results[0]["attempts"] == 3, "两次重试后第三次成功"
    assert attempts["n"] == 3


def test_no_retry_on_policy_and_gate_failures(monkeypatch):
    """策略类失败（白名单拒绝）与安全门拦截不重试。"""
    monkeypatch.setattr(atl, "_run_tool_gate", _no_gate())
    calls = {"n": 0}

    async def _denied(call, session_id, source_agent_id):
        calls["n"] += 1
        return {"result": "not_allowlisted: 命令 whoami 不在白名单", "status": "error",
                "service_name": "code_workspace", "tool_name": "shell_exec"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _denied)
    results = asyncio.run(
        atl.execute_tool_calls(
            # command 用沙箱白名单内的，让失败发生在「策略层」而不是 guard（W124-03）
            [{"agentType": "mcp", "tool_name": "shell_exec", "command": "ls"}], "s-deny", max_retries=2
        )
    )
    assert results[0]["attempts"] == 1 and calls["n"] == 1, "白名单拒绝不应重试"

    # 安全门 veto：直接返回，未执行、未重试
    async def _veto(call, session_id, source_agent_id):
        return {"tool_call": call, "result": "等待用户确认：diff 预览", "status": "error",
                "service_name": "tool_gate", "tool_name": "file_write"}

    monkeypatch.setattr(atl, "_run_tool_gate", _veto_async())
    executed = {"n": 0}

    async def _should_not_run(call, session_id, source_agent_id):
        executed["n"] += 1
        return {"result": "written", "status": "success", "service_name": "code_workspace",
                "tool_name": "file_write"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _should_not_run)
    results = asyncio.run(
        atl.execute_tool_calls(
            [{"agentType": "mcp", "tool_name": "file_write"}], "s-veto", max_retries=2
        )
    )
    assert results[0]["attempts"] == 1
    assert executed["n"] == 0, "被 veto 的调用不得执行"


def test_retry_count_is_bounded(monkeypatch):
    """一直失败 → 重试到 max_retries 就停，并标注重试过。"""
    monkeypatch.setattr(atl, "_run_tool_gate", _no_gate())
    calls = {"n": 0}

    async def _always_timeout(call, session_id, source_agent_id):
        calls["n"] += 1
        return {"result": "timeout", "status": "error",
                "service_name": "code_workspace", "tool_name": "code_exec"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _always_timeout)
    results = asyncio.run(
        atl.execute_tool_calls(
            [{"agentType": "mcp", "tool_name": "code_exec"}], "s-bounded", max_retries=2
        )
    )
    assert calls["n"] == 3, "1 次原始 + 2 次重试"
    assert results[0]["attempts"] == 3
    assert "已重试 2 次仍失败" in results[0]["result"]


def test_retry_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(atl, "_run_tool_gate", _no_gate())
    calls = {"n": 0}

    async def _timeout(call, session_id, source_agent_id):
        calls["n"] += 1
        return {"result": "timeout", "status": "error", "service_name": "x", "tool_name": "y"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _timeout)
    results = asyncio.run(
        atl.execute_tool_calls([{"agentType": "mcp", "tool_name": "y"}], "s-zero", max_retries=0)
    )
    assert calls["n"] == 1 and results[0]["attempts"] == 1


# ---------------------------------------------------------------------------
# 会话号注入（W121-04 按会话隔离的前提）
# ---------------------------------------------------------------------------


def test_inject_session_id_only_for_declared_tools(monkeypatch):
    """只有 manifest 声明了 session_id 的工具才注入，且不覆盖模型显式给的值。"""
    from mcpserver import mcp_registry

    fake_manifest = {
        "code_workspace": {
            "capabilities": {
                "invocationCommands": [
                    {"command": "code_exec", "parameters": {"properties": {"code": {}, "session_id": {}}}},
                    {"command": "test_run", "parameters": {"properties": {"path": {}}}},
                ]
            }
        },
        "weather_time": {"capabilities": {"invocationCommands": [
            {"command": "today_weather", "parameters": {"properties": {"city": {}}}}
        ]}},
    }
    monkeypatch.setattr(mcp_registry, "MANIFEST_CACHE", fake_manifest, raising=False)

    call = {"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}
    atl._inject_session_id(call, "sess-42")
    assert call["session_id"] == "sess-42"

    # 未声明 session_id 的工具不注入
    call2 = {"agentType": "mcp", "service_name": "code_workspace", "tool_name": "test_run"}
    atl._inject_session_id(call2, "sess-42")
    assert "session_id" not in call2

    other = {"agentType": "mcp", "service_name": "weather_time", "tool_name": "today_weather"}
    atl._inject_session_id(other, "sess-42")
    assert "session_id" not in other

    # 模型显式指定时不覆盖
    explicit = {"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec",
                "session_id": "model-chosen"}
    atl._inject_session_id(explicit, "sess-42")
    assert explicit["session_id"] == "model-chosen"


# ---------------------------------------------------------------------------
# 收敛提示词（纯函数）
# ---------------------------------------------------------------------------


def test_build_convergence_prompt_contents():
    ledger = [
        {"round": 1, "label": "code_workspace:code_exec", "status": "success", "attempts": 3,
         "summary": "stdout=2"},
        {"round": 2, "label": "code_workspace:test_run", "status": "error", "attempts": 3,
         "summary": "1 failed"},
    ]
    text = atl.build_convergence_prompt(ledger, "max_steps", 8)
    assert "工具迭代已达上限（8 步）" in text
    assert "已完成：" in text and "重试 2 次后成功" in text
    assert "未完成 / 失败：" in text and "1 failed" in text
    assert "不要再发起任何工具调用" in text

    empty = atl.build_convergence_prompt([], "consecutive_failures", 8)
    assert "连续多轮工具调用全部失败" in empty
    assert "已完成：（无）" in empty


def test_retryable_failure_classification():
    assert atl._retryable_failure({"status": "error", "result": "执行超时（>10s），已终止"})
    assert atl._retryable_failure({"status": "error", "result": "Connection reset by peer"})
    assert atl._retryable_failure({"status": "error", "result": "执行异常: RuntimeError"})
    assert not atl._retryable_failure({"status": "success", "result": "timeout"})
    assert not atl._retryable_failure({"status": "error", "result": "not_allowlisted: whoami"})
    assert not atl._retryable_failure({"status": "error", "result": "等待用户确认：diff 预览"})


def test_effective_status_corrects_mcp_error_payload():
    """MCP 桥把业务错误包在返回体里，外层却是 success —— 真实状态必须判为 error。"""
    wrapped_error = {
        "status": "success",  # dispatch 层对 MCP 调用一律标 success
        "result": '{"status": "error", "message": "参数错误: unexpected keyword argument", "data": {}}',
    }
    assert atl._effective_status(wrapped_error) == "error"
    assert atl._effective_status({"status": "success", "result": '{"status": "success"}'}) == "success"
    assert atl._effective_status({"status": "error", "result": "boom"}) == "error"
    # 错误体里是瞬时原因时，仍按可重试处理
    assert atl._retryable_failure(
        {"status": "success", "result": '{"status": "error", "message": "connection reset"}'}
    )


def test_mcp_error_payload_triggers_early_convergence(monkeypatch):
    """MCP 错误体连续两轮 → 提前收敛（外层 success 不得掩盖失败）。"""
    llm = _FakeLLM(["调工具", "再调", "兜底答复"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(
        atl, "parse_tool_calls_from_text",
        _ScriptedCalls([[{"agentType": "mcp", "service_name": "code_workspace", "tool_name": "file_write"}]]),
    )

    async def _fake_execute(calls, session_id, source_agent_id=None, max_retries=None):
        return [{
            "tool_call": {}, "status": "success",  # 外层 success
            "result": '{"status": "error", "message": "参数错误"}',
            "service_name": "code_workspace", "tool_name": "file_write", "attempts": 1,
        }]

    monkeypatch.setattr(atl, "execute_tool_calls", _fake_execute)

    asyncio.run(_collect(atl.run_agentic_loop([{"role": "user", "content": "写到绿"}], "s-mcp-err", max_rounds=8)))
    assert len(llm.calls) == 3, "两轮真实失败后应提前收敛"
    assert "连续多轮工具调用全部失败" in llm.calls[-1][-1]["content"]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


async def _collect(gen):
    out = []
    async for chunk in gen:
        out.append(chunk)
    return out


def _no_gate():
    async def _inner(call, session_id, source_agent_id):
        return None

    return _inner


def _veto_async():
    async def _inner(call, session_id, source_agent_id):
        return {"tool_call": call, "result": "等待用户确认：diff 预览", "status": "error",
                "service_name": "tool_gate", "tool_name": "file_write"}

    return _inner
