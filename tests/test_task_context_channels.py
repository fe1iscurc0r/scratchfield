"""卷123 W123-05 验收：任务级上下文 + 跨通道任务继续 + 调度联动。

覆盖：任务上下文含相关文件/上一步结果 / 步骤边界压缩后 goal 与关键结果不丢 /
跨通道 list/continue（同用户可见、按开关隔离）/ 调度空闲提示 / 多轮注入不重复丢信息。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio

import pytest

from apiserver import task_flow, task_store
from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间

PLAN = """[PLAN]
1. 探查：读 utils.py（工具：file_read）
2. 实现：改 utils.py（工具：file_edit）
3. 测试：跑 tests/test_utils.py（工具：test_run）
[/PLAN]"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    return {"db": db}


def _set_cfg(monkeypatch, **kw):
    class _Cfg:
        enabled = True
        step_template: list = []
        verify_audit_only = False
        verify_max_retries = kw.get("verify_max_retries", 2)
        review_enabled = True
        review_dir = "docs/task-reviews"
        cross_channel_shared = kw.get("cross_channel_shared", True)
        idle_advance = kw.get("idle_advance", False)
        idle_minutes = kw.get("idle_minutes", 30)

    cfg = _Cfg()
    monkeypatch.setattr(task_flow, "_cfg", lambda: cfg)
    return cfg


# ---------------------------------------------------------------------------
# 任务级上下文
# ---------------------------------------------------------------------------


def test_task_context_includes_files_and_last_result(env, monkeypatch):
    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s1", "给 utils 加 slugify", PLAN)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    # 第一步完成 → 关键结果进上下文
    task_flow.record_step_result(tid, "s1", task_store.STEP_DONE,
                                 result_ref="理解摘要：utils.py 只有 slugify 雏形，tests 有 2 条用例")
    ctx = task_flow.task_context_prompt("s1")
    assert "当前步骤：s2" in ctx
    assert "本步相关文件" in ctx and "utils.py" in ctx
    assert "上一步结果" in ctx and "只有 slugify 雏形" in ctx
    assert '[TASK]{"op":"step"' in ctx

    # 关键结果清单
    keys = task_flow.key_results(task_store.get_task(tid))
    assert keys and "s1" in keys[0] and "slugify 雏形" in keys[0]


def test_step_boundary_compact_keeps_goal_and_key_results(env, monkeypatch):
    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s1", "给 utils 加 slugify 并跑测试", PLAN)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")
    task_flow.record_step_result(tid, "s1", task_store.STEP_DONE, result_ref="理解摘要：utils.py 需要加 slugify")
    task_flow.record_step_result(tid, "s2", task_store.STEP_DONE, result_ref="utils.py:1 新增 slugify")

    messages = [{"role": "system", "content": "你是陆墨"}]
    for i in range(8):
        messages.append({"role": "assistant", "content": f"第{i}轮说明"})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"大段工具输出 {i}" * 50})
    messages.append({"role": "user", "content": "继续"})

    dropped = task_flow.step_boundary_compact(messages, "s1")
    assert dropped > 0, "步骤边界压缩应当收敛历史工具结果"
    joined = "\n".join(str(m.get("content")) for m in messages)
    assert "任务上下文压缩" in joined
    assert "理解摘要：utils.py 需要加 slugify" in joined, "关键结果必须保留"
    assert "utils.py:1 新增 slugify" in joined
    assert "大段工具输出 0" not in joined, "老工具输出应被收敛掉"
    assert messages[-1]["content"] == "继续", "最近消息不动"
    assert messages[0]["role"] == "system", "首条 system 不动"

    # 任务目标仍可从 task_store 查到（压缩不影响权威源）
    assert "slugify" in task_store.get_task(tid)["goal"]
    # 没有活动任务时不误压
    task_store.set_status(tid, task_store.STATUS_DONE)
    assert task_flow.step_boundary_compact(messages, "s1") == 0


def test_loop_injects_task_context_with_plan(env, monkeypatch):
    """多轮注入：system 层带上任务块，且首轮注入的目标模式提示不丢。"""
    from tests.test_agentic_loop_flow import _collect, _FakeLLM, _ScriptedCalls

    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s-loop", "目标：把 utils 的 slugify 修好", PLAN)
    task_flow.confirm_plan("s-loop")
    task_flow.record_step_result(task["task_id"], "s1", task_store.STEP_DONE, result_ref="已读 utils.py")

    llm = _FakeLLM(["继续下一步", "完成"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls([[], []]))

    asyncio.run(_collect(atl.run_agentic_loop(
        [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": "继续"}], "s-loop", max_rounds=1
    )))
    system_content = llm.calls[0][0]["content"]
    assert "当前任务" in system_content
    assert "当前步骤：s2" in system_content
    assert "上一步结果" in system_content and "已读 utils.py" in system_content


# ---------------------------------------------------------------------------
# 跨通道
# ---------------------------------------------------------------------------


def test_cross_channel_list_and_continue(env, monkeypatch):
    """A 通道建任务 → B 通道 list/continue 成功（同一登录用户）。"""
    _set_cfg(monkeypatch, cross_channel_shared=True)
    monkeypatch.setattr(task_flow, "current_user_id", lambda: "u-shenyao")

    created = task_flow.run_meta_command("session-qq", "task:create 给 calc.py 加 divide")
    assert "已建任务" in created
    tid = task_flow.active_task("session-qq")["task_id"]
    assert task_store.get_task(tid)["user_id"] == "u-shenyao", "建任务应绑当前用户"

    listed = task_flow.run_meta_command("session-wechat", "task:list")
    assert tid in listed and "来自会话 session-qq" in listed

    cont = task_flow.run_meta_command("session-wechat", f"task:continue {tid}")
    assert "继续任务" in cont and "该任务来自会话 session-qq" in cont
    assert task_store.get_task(tid)["status"] == "running", "resume 生效"


def test_cross_channel_isolation_switch(env, monkeypatch):
    """cross_channel_shared=false → 按通道隔离，别的会话看不到任务。"""
    _set_cfg(monkeypatch, cross_channel_shared=False)
    monkeypatch.setattr(task_flow, "current_user_id", lambda: "u-shenyao")

    task_flow.run_meta_command("session-qq", "task:create 私密任务")
    tid = task_flow.active_task("session-qq")["task_id"]

    listed = task_flow.run_meta_command("session-wechat", "task:list")
    assert tid not in listed, listed
    assert task_flow.find_visible_task("session-wechat", tid) is None
    # 本会话仍可见
    assert task_flow.find_visible_task("session-qq", tid) is not None


def test_cross_channel_blocked_for_other_user(env, monkeypatch):
    """不同用户的跨通道任务不可见（避免越权）。"""
    _set_cfg(monkeypatch, cross_channel_shared=True)
    monkeypatch.setattr(task_flow, "current_user_id", lambda: "u-a")
    task_flow.run_meta_command("session-a", "task:create A 的任务")
    tid = task_flow.active_task("session-a")["task_id"]

    monkeypatch.setattr(task_flow, "current_user_id", lambda: "u-b")
    assert task_flow.find_visible_task("session-b", tid) is None
    assert tid not in task_flow.run_meta_command("session-b", "task:list")


# ---------------------------------------------------------------------------
# 调度联动
# ---------------------------------------------------------------------------


def test_idle_task_advice(env, monkeypatch):
    _set_cfg(monkeypatch, idle_advance=True, idle_minutes=1)
    task = task_flow.create_task_from_plan("s1", "空闲任务", PLAN)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    # 刚建不算空闲
    assert task_flow.scheduler_tick_advice(minutes=30) is None
    # 把 updated_at 推早 2 小时（touch=False：不刷新时间戳）
    task_store._update_fields(tid, {"updated_at": task_store.time.time() - 7200}, touch=False)
    advice = task_flow.scheduler_tick_advice(minutes=60)
    assert advice and tid in advice and "空闲" in advice
    assert "task:continue" in advice
    idle = task_flow.idle_tasks(minutes=60)
    assert [t["task_id"] for t in idle] == [tid]


def test_register_scheduler_advice_respects_switch(env, monkeypatch):
    from apiserver.event_bus.bus import InProcessEventBus

    bus = InProcessEventBus()
    _set_cfg(monkeypatch, idle_advance=False)
    assert task_flow.register_scheduler_advice(bus) is None, "默认关：不挂"

    _set_cfg(monkeypatch, idle_advance=True, idle_minutes=1)
    disposer = task_flow.register_scheduler_advice(bus)
    assert disposer is not None
    task = task_flow.create_task_from_plan("s1", "空闲任务", PLAN)
    task_store._update_fields(task["task_id"], {"updated_at": task_store.time.time() - 7200}, touch=False)
    from apiserver.event_bus import Topics

    bus.emit(Topics.SCHEDULER_TICK, {"tick": "5m"})  # 命中处理函数不抛异常即可
    disposer()
