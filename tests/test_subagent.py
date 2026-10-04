"""W124-02 验收：Subagent 子代理（派生 / 受限工具集 / 并行聚合 / 不可嵌套）。

覆盖：spawn 落库与工具白名单 / 并行执行结果聚合 / 受限工具集裁剪（授权外不可见）/
嵌套拒绝 / 超时与失败落库 / [SUBAGENT] 段解析 / 结果注入父对话 / subagent:status 指令。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json

import pytest

from apiserver import subagent, task_store
from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间


class _SubCfg:
    def __init__(self, **kw):
        self.enabled = kw.get("enabled", True)
        self.max_parallel = kw.get("max_parallel", 3)
        self.default_tools = kw.get("default_tools", ["file_read", "code_exec", "test_run"])
        self.max_rounds = kw.get("max_rounds", 2)
        self.timeout_s = kw.get("timeout_s", 30.0)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: path)
    monkeypatch.setattr(subagent, "_db_path", lambda: path)
    return path


@pytest.fixture()
def cfg(db, monkeypatch):
    def _set(**kw):
        c = _SubCfg(**kw)
        monkeypatch.setattr(subagent, "_cfg", lambda: c)
        return c

    return _set


# ---------------------------------------------------------------------------
# 派生与受限工具集
# ---------------------------------------------------------------------------


def test_spawn_records_toolset_and_defaults(cfg):
    cfg()
    created = subagent.spawn("读一下 utils.py 并报告函数签名", parent_task="t-1", session_id="s1", run=False)
    assert created["ok"] is True
    assert created["toolset"] == ["file_read", "code_exec", "test_run"], "默认白名单"

    record = subagent.get_subagent(created["subagent_id"])
    assert record["status"] == subagent.STATUS_PENDING
    assert record["parent_task"] == "t-1" and record["session_id"] == "s1"
    assert record["tools"] == ["file_read", "code_exec", "test_run"]


def test_spawn_rejects_empty_goal_and_disabled(cfg):
    cfg()
    assert subagent.spawn("   ", run=False)["error"] == "empty_goal"
    cfg(enabled=False)
    assert subagent.spawn("干活", run=False)["error"] == "disabled"


def test_restricted_toolset_filters_schemas(cfg, monkeypatch):
    """工具集裁剪：授权外工具不进 schema（子代理看不到也调不动）。"""
    cfg()
    fake = [
        {"function": {"name": "mcp__code_workspace__file_read"}},
        {"function": {"name": "mcp__code_workspace__code_exec"}},
        {"function": {"name": "mcp__code_workspace__file_write"}},
        {"function": {"name": "openclaw__agent"}},
        {"function": {"name": "mcp__vulnclaw__vulnclaw_invoke"}},
    ]
    monkeypatch.setattr("apiserver.tool_schemas.get_all_tool_schemas", lambda *a, **k: fake)
    from mcpserver import scope as scope_mod

    monkeypatch.setattr(scope_mod, "enabled", lambda: False)  # 只测子代理这层的裁剪
    names = [s["function"]["name"] for s in subagent.filter_tool_schemas(["file_read", "code_exec"])]
    assert names == ["mcp__code_workspace__file_read", "mcp__code_workspace__code_exec"]
    assert "mcp__code_workspace__file_write" not in names
    assert "openclaw__agent" not in names and "mcp__vulnclaw__vulnclaw_invoke" not in names


def test_nested_spawn_rejected(cfg):
    cfg()
    denied = subagent.spawn("再派生一个", session_id=subagent.session_of("abc123"), run=False)
    assert denied["error"] == "nested_not_allowed"
    assert asyncio.run(subagent.spawn_many([{"goal": "x"}],
                                           session_id=subagent.session_of("abc"))) == [
        {"ok": False, "error": "nested_not_allowed"}
    ]
    assert subagent.is_subagent_session("sub-xyz") and not subagent.is_subagent_session("s1")


# ---------------------------------------------------------------------------
# 执行与并行聚合
# ---------------------------------------------------------------------------


def test_run_subagent_and_aggregate(cfg, monkeypatch):
    cfg()

    async def _fake_llm(subagent_record, context):
        return f"完成：{subagent_record['goal']}（上下文 {len(context)} 字）"

    monkeypatch.setattr(subagent, "_run_llm", _fake_llm)
    results = asyncio.run(subagent.spawn_many(
        [{"goal": "改 A 文件"}, {"goal": "改 B 文件"}, {"goal": "改 C 文件"}],
        parent_task="t-1", session_id="s1", context="仓库结构摘要",
    ))
    assert len(results) == 3 and all(r["ok"] for r in results)
    assert {r["status"] for r in results} == {subagent.STATUS_DONE}

    prompt = subagent.results_prompt("s1")
    assert "〔子代理结果〕" in prompt
    assert "改 A 文件" in prompt and "改 B 文件" in prompt and "改 C 文件" in prompt
    assert all(subagent.get_subagent(r["subagent_id"])["status"] == "done" for r in results)


def test_max_parallel_is_respected(cfg, monkeypatch):
    cfg(max_parallel=2)
    live = {"now": 0, "peak": 0}

    async def _slow_llm(subagent_record, context):
        live["now"] += 1
        live["peak"] = max(live["peak"], live["now"])
        await asyncio.sleep(0.05)
        live["now"] -= 1
        return "ok"

    monkeypatch.setattr(subagent, "_run_llm", _slow_llm)
    asyncio.run(subagent.spawn_many(
        [{"goal": f"任务{i}"} for i in range(5)], session_id="s1"
    ))
    assert live["peak"] <= 2, f"并发上限失效：{live['peak']}"


def test_timeout_and_failure_recorded(cfg, monkeypatch):
    cfg(timeout_s=5.0)

    async def _boom(subagent_record, context):
        raise RuntimeError("llm 挂了")

    monkeypatch.setattr(subagent, "_run_llm", _boom)
    failed = asyncio.run(subagent.spawn_async("会失败的任务", session_id="s1"))
    assert failed["ok"] is False and failed["status"] == subagent.STATUS_FAILED
    assert "llm 挂了" in subagent.get_subagent(failed["subagent_id"])["result"]

    async def _hang(subagent_record, context):
        await asyncio.sleep(10)

    monkeypatch.setattr(subagent, "_run_llm", _hang)
    cfg(timeout_s=0.2)
    timeout = asyncio.run(subagent.spawn_async("会超时的任务", session_id="s1"))
    assert timeout["status"] == subagent.STATUS_FAILED and timeout["error"] == "timeout"


# ---------------------------------------------------------------------------
# 对话协议
# ---------------------------------------------------------------------------


def test_extract_and_run_via_loop(cfg, monkeypatch, db):
    """模型输出 [SUBAGENT] 段 → loop 派生并聚合，父对话拿到结果。"""
    from tests.test_agentic_loop_flow import _collect, _events, _FakeLLM, _ScriptedCalls

    cfg()
    seen: list[dict] = []

    async def _fake_llm(subagent_record, context):
        seen.append({"goal": subagent_record["goal"], "tools": subagent_record["tools"]})
        return f"子代理完成：{subagent_record['goal']}"

    monkeypatch.setattr(subagent, "_run_llm", _fake_llm)
    text = (
        "我并行派两个子代理：\n"
        '[SUBAGENT]{"goal":"读 utils.py 并报告函数"},{"goal":"跑一次测试看基线"}[/SUBAGENT]'
    )
    llm = _FakeLLM([text, "两个子代理都完成了。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls([[], []]))

    messages = [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": "并行查一下"}]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-parent", max_rounds=2)))
    events = _events(chunks)

    sub_events = [e for e in events if e.get("type") == "subagents"]
    assert sub_events, "应发 subagents 事件"
    assert len(sub_events[0]["results"]) == 2
    assert all(r["toolset"] == ["file_read", "code_exec", "test_run"] for r in sub_events[0]["results"])
    assert {s["goal"] for s in seen} == {"读 utils.py 并报告函数", "跑一次测试看基线"}

    # 结果聚合注入父对话（第二轮 LLM 调用能看到）
    injected = json.dumps(llm.calls[-1], ensure_ascii=False)
    assert "〔子代理结果〕" in injected and "子代理完成" in injected


def test_status_text_and_stats(cfg):
    cfg()
    created = subagent.spawn("统计子代理", session_id="s1", run=False)
    listing = subagent.status_text(session_id="s1")
    assert created["subagent_id"] in listing and "统计子代理" in listing
    detail = subagent.status_text(created["subagent_id"])
    assert "状态 pending" in detail
    assert subagent.status_text("nope") .startswith("没找到子代理")
    assert subagent.stats()["default_tools"] == ["file_read", "code_exec", "test_run"]
    assert subagent.extract_subagent_specs("没有段") == []
    assert subagent.extract_subagent_specs("[SUBAGENT]{坏 json}[/SUBAGENT]") == []
