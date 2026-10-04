"""卷123 W123-04 验收：Review 阶段（汇总 + 三种裁决 + 报告落盘）。

覆盖：汇总含改动/验证/文件/待确认问题 / 确认→done 存档 / 打回→running 带意见 / 跳过→done 带标记 /
报告落盘 docs/task-reviews/<task_id>.md 且裁决回写 / 元指令三路径 / review 提示。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import pytest

from apiserver import task_flow, task_review, task_store
from mcpserver.code_workspace import sandbox
from mcpserver.code_workspace.tools import CodeWorkspaceBridge


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    monkeypatch.setattr(sandbox, "workspace_root", lambda: tmp_path / "code_workspace")
    reports = tmp_path / "task-reviews"
    monkeypatch.setattr(task_review, "review_dir", lambda: reports)
    return {"db": db, "reports": reports, "tmp": tmp_path}


def _task_in_review(env, *, verify_ok: bool = True) -> str:
    """造一个「已执行完、带验证结果」的任务，返回 task_id。"""
    bridge = CodeWorkspaceBridge()
    if verify_ok:
        bridge.file_write("utils.py", "def slugify(t):\n    return t.lower()\n", session_id="s1")
        bridge.file_write("tests/test_utils.py",
                          "from utils import slugify\n\n\ndef test_low():\n    assert slugify('A') == 'a'\n",
                          session_id="s1")
    else:
        bridge.file_write("utils.py", "x = 1\n", session_id="s1")
        bridge.file_write("tests/test_utils.py", "def test_bad():\n    assert 1 == 2\n", session_id="s1")

    task = task_store.create_task(
        "s1", "给 utils 加 slugify 并测试",
        steps=[{"id": "s1", "desc": "探查 utils.py", "type": "explore"},
               {"id": "s2", "desc": "实现 slugify", "type": "code"}],
        git_state="main@abc1234", status=task_store.STATUS_RUNNING,
    )
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_utils.py"])
    task_flow.finish_step_with_verify(
        tid, "s1", result_ref="理解摘要：utils.py 有 slugify 雏形；最小改动路径：只调 lower()",
        tool="file_read", session_id="s1",
    )
    task_flow.finish_step_with_verify(
        tid, "s2", result_ref="实现 slugify（utils.py）", tool="file_write", session_id="s1",
    )
    return tid


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def test_build_review_collects_everything(env):
    tid = _task_in_review(env)
    built = task_review.build_review(tid)
    assert built["ok"] is True
    review = built["review"]
    assert review["steps_done"] == 2 and review["steps_total"] == 2
    assert review["diff"]["changed_files"] >= 0 and review["diff"]["source"]
    assert review["verifications"], "应收到验证门结果"
    v = review["verifications"][0]
    assert v["step_id"] == "s2" and v["mode"] in ("pytest", "py_compile") and "通过" in v["result"]
    assert review["questions"], "必须给出待确认清单"
    joined = " ".join(review["questions"])
    # 测试工作区不是 git 仓库，规则会把这点列出来；验证通过则不应出现「验证未全绿」
    assert "git" in joined or "请确认" in joined or "遗留" in joined, review["questions"]
    assert "验证未全绿" not in joined, review["questions"]

    report = built["report"]
    for section in ("# 任务审查", "## 改动摘要", "## 验证结果", "## 涉及文件", "## 待确认问题", "## 裁决"):
        assert section in report, section
    assert "utils.py" in report and "tests/test_utils.py" in report
    assert "main@abc1234" in report

    # 报告落盘
    path = env["reports"] / f"{tid}.md"
    assert path.exists() and len(path.read_text(encoding="utf-8")) > 200
    assert review["report_path"].endswith(f"{tid}.md")


def test_open_questions_flags_gaps(env):
    tid = _task_in_review(env, verify_ok=False)
    review = task_review.build_review(tid)["review"]
    joined = " ".join(review["questions"])
    assert review["verifications"], "验证失败也必须留下验证记录"
    assert review["verifications"][0]["ok"] is False, review["verifications"]
    assert "验证未全绿" in joined, review["questions"]
    assert "仍有" in joined or "重试" in joined, review["questions"]


# ---------------------------------------------------------------------------
# 三种裁决
# ---------------------------------------------------------------------------


def test_verdict_confirm_archives_trajectory(env):
    tid = _task_in_review(env)
    task_review.build_review(tid)
    result = task_review.apply_verdict(tid, "confirmed", note="没问题")
    assert result["ok"] and result["status"] == task_store.STATUS_DONE
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "done"
    assert fresh["review"]["verdict"] == "confirmed"
    assert fresh["trajectory"][-1]["tool"] == "review:confirm"
    report = (env["reports"] / f"{tid}.md").read_text(encoding="utf-8")
    assert "已确认（任务 done，轨迹存档）" in report and "用户意见：没问题" in report


def test_verdict_reject_returns_to_running_with_note(env):
    tid = _task_in_review(env)
    task_review.build_review(tid)
    result = task_review.apply_verdict(tid, "rejected", note="缺边界处理，补一下")
    assert result["ok"] and result["status"] == task_store.STATUS_RUNNING
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "running"
    assert fresh["review"]["verdict"] == "rejected"
    assert "缺边界处理" in fresh["review"]["verdict_note"]
    assert any("打回：缺边界处理" in str(t.get("summary")) for t in fresh["trajectory"])
    assert "已打回" in (env["reports"] / f"{tid}.md").read_text(encoding="utf-8")


def test_verdict_skip_marks_unreviewed(env):
    tid = _task_in_review(env)
    task_review.build_review(tid)
    result = task_review.apply_verdict(tid, "skipped")
    assert result["ok"] and result["status"] == task_store.STATUS_DONE
    fresh = task_store.get_task(tid)
    assert fresh["review"]["verdict"] == "skipped"
    assert any("未经 review" in str(t.get("summary")) for t in fresh["trajectory"])
    assert "已跳过（done，标记：未经 review）" in (env["reports"] / f"{tid}.md").read_text(encoding="utf-8")
    assert task_review.apply_verdict(tid, "乱写")["ok"] is False
    assert task_review.apply_verdict("no-such-task", "confirmed")["ok"] is False


# ---------------------------------------------------------------------------
# 对话侧
# ---------------------------------------------------------------------------


def test_meta_commands_drive_review(env):
    tid = _task_in_review(env)
    assert task_store.get_task(tid)["status"] == "review"

    report = task_flow.run_meta_command("s1", "task:review")
    assert "任务审查" in report and "task:accept" in report

    rejected = task_flow.run_meta_command("s1", "task:reject 边界要补")
    assert "已打回" in rejected and task_store.get_task(tid)["status"] == "running"
    assert "边界要补" in task_store.get_task(tid)["review"]["verdict_note"]

    task_store.set_status(tid, task_store.STATUS_REVIEW)
    accepted = task_flow.run_meta_command("s1", "task:accept")
    assert "审查通过" in accepted and task_store.get_task(tid)["status"] == "done"

    # 跳过审查：done 任务不算活动任务，需显式给 id
    task_store.set_status(tid, task_store.STATUS_REVIEW)
    skipped = task_flow.run_meta_command("s1", f"task:skip-review {tid}")
    assert "未经 review" in skipped
    assert task_store.get_task(tid)["review"]["verdict"] == "skipped"


def test_review_prompt_and_stats(env):
    tid = _task_in_review(env)
    prompt = task_review.review_prompt(tid)
    assert "已进入审查" in prompt and "task:accept" in prompt
    stats = task_review.stats()
    assert stats["reports"] >= 1 and str(env["reports"]) == stats["dir"]
    assert task_review.review_prompt("no-such-task") == ""


def test_review_status_is_terminal_step_of_flow(env):
    """全部步骤完成即自动进 review（W123-02 联动），确认后 done —— 全链路状态收口。"""
    tid = _task_in_review(env)
    assert task_store.get_task(tid)["status"] == "review"
    task_review.build_review(tid)
    task_review.apply_verdict(tid, "confirmed")
    assert task_store.get_task(tid)["status"] == "done"
    assert task_flow.active_task("s1") is None, "done 任务不再算活动任务"
