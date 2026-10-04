"""卷123 W123-02 验收：Goal Mode（目标 → [PLAN] → 任务 → 确认 → 逐步执行 → fail-closed）。

覆盖：PLAN 解析（≥3 步含探查）/ 确认后执行与步骤流转 / 某步失败 → blocked 不继续 /
暂停恢复与跳过 / 目标模式提示与任务上下文注入 / loop 按 [PLAN] 建任务。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json

import pytest

from apiserver import task_flow, task_store
from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间

PLAN_TEXT = """我先给个计划：

[PLAN]
1. 探查 calc.py 与 tests 目录结构（工具：file_read）
2. 实现 divide 函数（工具：file_edit）
3. 跑 tests/test_calc.py（工具：test_run）
4. 验证结果符合目标，无副作用
[/PLAN]

确认后我就开工。
"""


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: path)
    return path


# ---------------------------------------------------------------------------
# PLAN 解析与建任务
# ---------------------------------------------------------------------------


def test_parse_plan_steps_detects_types_and_tools():
    steps = task_flow.parse_plan_steps(PLAN_TEXT)
    assert len(steps) == 4, steps
    assert [s["type"] for s in steps] == ["explore", "code", "test", "verify"]
    assert steps[0]["tool"] == "file_read" and steps[1]["tool"] == "file_edit"
    assert "探查" in steps[0]["desc"] and "（工具" not in steps[0]["desc"], "工具标注要从描述里剔除"

    # 无 [PLAN] 段 / 空段 → 空列表
    assert task_flow.parse_plan_steps("没有计划") == []
    assert task_flow.parse_plan_steps("[PLAN]\n[/PLAN]") == []

    # 各种行格式都认：短横线 / 复选框；无标记的普通句子不算步骤
    mixed = "- 探查仓库结构\n[ ] 实现改动\n随便一句描述"
    parsed = task_flow.parse_plan_steps(mixed)
    assert len(parsed) == 2 and parsed[0]["type"] == "explore", parsed
    assert all("随便一句" not in s["desc"] for s in parsed)

    # 行首类型词优先：正文里出现 tests/ 不能把「实现」步判成 test
    typed = task_flow.parse_plan_steps(
        "1. 实现：新建 utils.py 并写 tests/test_utils.py\n2. 测试：跑 pytest 确认全绿"
    )
    assert [s["type"] for s in typed] == ["code", "test"], typed


def test_create_task_from_plan_and_confirm(db):
    task = task_flow.create_task_from_plan("s1", "给 calc.py 加 divide", PLAN_TEXT)
    assert task["status"] == "pending", "计划先等用户确认"
    assert [s["type"] for s in task["steps"]] == ["explore", "code", "test", "verify"]
    assert task_flow.pending_plan("s1")["task_id"] == task["task_id"]

    confirmed = task_flow.confirm_plan("s1")
    assert confirmed["status"] == "running"
    assert task_flow.pending_plan("s1") is None
    assert task_flow.next_step(confirmed)["id"] == "s1"
    assert task_store.get_task(task["task_id"])["trajectory"][-1]["tool"] == "goal:confirm"

    # 解析不出步骤 → 退回默认四步模板
    fallback = task_flow.create_task_from_plan("s2", "没有计划段的目标", "啥也没有")
    assert [s["type"] for s in fallback["steps"]] == ["explore", "code", "test", "verify"]


def test_step_flow_then_review_or_done(db):
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_TEXT)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    task_flow.record_step_result(tid, "s1", task_store.STEP_DONE,
                                 result_ref="理解摘要：calc.py 只有 add，tests 一条用例", tool="file_read")
    task_flow.record_step_result(tid, "s2", task_store.STEP_DONE, result_ref="新增 divide", tool="file_edit")
    task_flow.record_step_result(tid, "s3", task_store.STEP_DONE, result_ref="2 passed", tool="test_run")
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "running", "还有一步没走完"
    assert task_flow.next_step(fresh)["id"] == "s4"

    result = task_flow.record_step_result(tid, "s4", task_store.STEP_DONE, result_ref="符合目标")
    assert result["task_status"] in ("review", "done"), "全部完成应进入 review/done"
    assert task_store.get_task(tid)["status"] == result["task_status"]
    assert len(task_store.get_task(tid)["trajectory"]) >= 5


def test_failed_step_blocks_task_fail_closed(db):
    """fail-closed：某步失败 → 任务 blocked，不自动继续下一步。"""
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_TEXT)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    task_flow.record_step_result(tid, "s1", task_store.STEP_DONE, result_ref="摘要")
    blocked = task_flow.record_step_result(
        tid, "s2", task_store.STEP_BLOCKED, result_ref="syntax error: 缩进错误", tool="test_run"
    )
    assert blocked["task_status"] == "blocked"
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "blocked"
    assert fresh["steps"][2]["status"] == "pending", "后续步骤不得自动执行"

    # 一步 failed 同样触发 blocked
    other = task_flow.create_task_from_plan("s2", "目标2", PLAN_TEXT)
    task_flow.confirm_plan("s2")
    res = task_flow.record_step_result(other["task_id"], "s1", "failed", result_ref="炸了")
    assert res["task_status"] == "blocked"

    # 模型通过 [TASK] 段报 blocked 也走同一路径
    applied = task_flow.apply_task_ops(
        "s2", [{"op": "step", "task_id": other["task_id"], "step_id": "s2", "status": "blocked",
                "result_ref": "验证不过"}]
    )
    assert applied[0]["ok"] and applied[0]["task_status"] == "blocked"


def test_pause_resume_skip_and_replan(db):
    task = task_flow.create_task_from_plan("s1", "原始目标", PLAN_TEXT)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    paused = task_flow.run_meta_command("s1", "task:pause")
    assert "已暂停" in paused and task_store.get_task(tid)["status"] == "paused"
    resumed = task_flow.run_meta_command("s1", "task:resume")
    assert "已恢复" in resumed and task_store.get_task(tid)["status"] == "running"

    skipped = task_flow.run_meta_command("s1", "task:skip s1")
    assert "已跳过 s1" in skipped
    assert task_store.get_task(tid)["steps"][0]["status"] == "skipped"
    assert task_flow.next_step(task_store.get_task(tid))["id"] == "s2"

    replanned = task_flow.run_meta_command("s1", "task:replan 换个做法：直接重写 divide")
    assert "已重新计划" in replanned
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "pending" and "重写 divide" in fresh["goal"]
    assert all(s["status"] == "pending" for s in fresh["steps"])


def test_confirm_meta_command_and_goal_prefix(db):
    assert "没有待确认的计划" in task_flow.run_meta_command("s1", "task:confirm")

    task = task_flow.create_task_from_plan("s1", "给 calc.py 加 divide", PLAN_TEXT)
    reply = task_flow.run_meta_command("s1", "task:confirm")
    assert "计划已确认" in reply and "s1 探查" in reply
    assert task_store.get_task(task["task_id"])["status"] == "running"

    assert task_flow.goal_from_text("goal: 修好 add 函数") == "修好 add 函数"
    assert task_flow.goal_from_text("目标：把测试跑绿") == "把测试跑绿"
    assert task_flow.goal_from_text("普通聊天") == ""
    assert task_flow.goal_from_messages([{"role": "user", "content": "goal: 加 divide"}]) == "加 divide"


def test_goal_mode_prompt_and_task_context(db):
    prompt = task_flow.goal_mode_prompt("给 calc.py 加 divide")
    assert "[PLAN]" in prompt and "探查" in prompt and "[TASK]" in prompt

    assert task_flow.task_context_prompt("s-none") == ""
    task = task_flow.create_task_from_plan("s1", "给 calc.py 加 divide", PLAN_TEXT)
    pending_ctx = task_flow.task_context_prompt("s1")
    assert "计划待用户确认" in pending_ctx and "给 calc.py 加 divide" in pending_ctx

    task_flow.confirm_plan("s1")
    running_ctx = task_flow.task_context_prompt("s1")
    assert "当前步骤：s1" in running_ctx and '"op":"step"' in running_ctx

    task_store.set_status(task["task_id"], task_store.STATUS_BLOCKED)
    assert "blocked" in task_flow.task_context_prompt("s1")


# ---------------------------------------------------------------------------
# Loop 接线
# ---------------------------------------------------------------------------


def test_loop_creates_task_from_plan_and_reports_task_update(db, monkeypatch):
    """loop 里模型出 [PLAN] → 建任务（pending）并发 task_update 事件。"""
    from tests.test_agentic_loop_flow import _collect, _events, _FakeLLM, _ScriptedCalls

    llm = _FakeLLM([PLAN_TEXT, "好的，等你确认。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls([[], []]))

    messages = [
        {"role": "system", "content": "你是陆墨"},
        {"role": "user", "content": "goal: 给 calc.py 加 divide 并测试"},
    ]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-plan", max_rounds=2)))
    events = _events(chunks)

    assert any(e.get("type") == "plan" for e in events), "应发 plan 事件"
    updates = [e for e in events if e.get("type") == "task_update"]
    assert updates, "应按 [PLAN] 建任务并发 task_update"
    tid = updates[0]["applied"][0]["task_id"]
    task = task_store.get_task(tid)
    assert task["status"] == "pending" and len(task["steps"]) == 4

    # 目标模式提示注入到了 system 层（并入 messages[0]）
    assert "[PLAN]" in llm.calls[0][0]["content"]
    assert llm.calls[0][0]["role"] == "system"

    # 第二轮：同会话再跑一次，注入任务上下文（pending → 提示等确认）
    messages2 = [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": "确认"}]
    asyncio.run(_collect(atl.run_agentic_loop(messages2, "s-plan", max_rounds=1)))
    assert "当前任务" in llm.calls[-1][0]["content"]
    assert "计划待用户确认" in llm.calls[-1][0]["content"]


def test_loop_applies_task_step_ops(db, monkeypatch):
    """模型用 [TASK] 段报步状态 → loop 落库并发 task_update。"""
    from tests.test_agentic_loop_flow import _collect, _events, _FakeLLM, _ScriptedCalls

    task = task_flow.create_task_from_plan("s1", "目标", PLAN_TEXT)
    task_flow.confirm_plan("s1")
    tid = task["task_id"]

    text = (
        "探查完成。\n"
        '[TASK]{"op":"step","task_id":"%s","step_id":"s1","status":"done",'
        '"result_ref":"calc.py 只有 add","tool":"file_read"}[/TASK]' % tid
    )
    llm = _FakeLLM([text, "继续下一步。"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls([[], []]))

    chunks = asyncio.run(_collect(atl.run_agentic_loop([{"role": "user", "content": "继续"}], "s1", max_rounds=2)))
    applied = [e for e in _events(chunks) if e.get("type") == "task_update"]
    assert applied and applied[0]["applied"][0]["ok"]
    fresh = task_store.get_task(tid)
    assert fresh["steps"][0]["status"] == "done"
    assert fresh["trajectory"][-1]["tool"] == "file_read"
    assert json.dumps({"ok": True})  # keep json import used
