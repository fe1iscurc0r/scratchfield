"""卷123 W123-03 验收：探查步骤 + 每轮验证门（fail-closed / audit_only）。

覆盖：探查步摘要与 file_refs 落库 / 验证门跑测试（通过 & 失败两种）/ 语法门回退 /
失败重试限次后 blocked / audit_only 只记不拦 / 正交字段 / 审计落 phase=verify_gate。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json

import pytest

from apiserver import task_flow, task_store, task_verify
from mcpserver.code_workspace import sandbox
from mcpserver.code_workspace.tools import CodeWorkspaceBridge

PLAN_2 = """[PLAN]
1. 探查：读 utils.py 与 tests（工具：file_read）
2. 实现：新建 utils.py 的 slugify（工具：file_write）
[/PLAN]"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """任务库 + 工作区 + 审计都重定向到 tmp。"""
    db = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    monkeypatch.setattr(sandbox, "workspace_root", lambda: tmp_path / "code_workspace")
    audits: list[dict] = []
    monkeypatch.setattr(task_verify, "_audit", lambda r: audits.append({"phase": "verify_gate", **r}))
    return {"db": db, "audits": audits, "tmp": tmp_path}


class _Cfg:
    def __init__(self, **kw):
        self.verify_audit_only = kw.get("verify_audit_only", False)
        self.verify_max_retries = kw.get("verify_max_retries", 2)
        self.enabled = kw.get("enabled", True)
        self.step_template = kw.get("step_template", [])
        self.review_dir = kw.get("review_dir", "docs/task-reviews")


def _set_cfg(monkeypatch, **kw):
    cfg = _Cfg(**kw)
    monkeypatch.setattr(task_flow, "_cfg", lambda: cfg)
    monkeypatch.setattr(task_verify, "_cfg", lambda: cfg)
    return cfg


# ---------------------------------------------------------------------------
# 探查步骤
# ---------------------------------------------------------------------------


def test_explore_step_records_summary_and_file_refs(env, monkeypatch):
    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s1", "给 utils 加 slugify", PLAN_2)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")

    result = task_flow.finish_step_with_verify(
        tid, "s1",
        result_ref="理解摘要：utils.py 只有 slugify 雏形，tests/test_utils.py 有 2 条用例；最小改动路径：只补 slugify 的多空格处理",
        tool="file_read",
    )
    assert result["ok"] and result["task_status"] == ""
    fresh = task_store.get_task(tid)
    assert fresh["steps"][0]["status"] == "done"
    assert "utils.py" in fresh["file_refs"] and "tests/test_utils.py" in fresh["file_refs"], fresh["file_refs"]
    assert fresh["trajectory"][-1]["status"] == "done"


def test_explore_step_without_summary_leaves_warning(env, monkeypatch):
    """探查步不给摘要 → 留 warn 轨迹（摘要必须用户可见，不静默跳过）。"""
    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_flow.confirm_plan("s1")
    task_flow.finish_step_with_verify(tid, "s1", result_ref="", tool="file_read")
    traj = task_store.get_task(tid)["trajectory"]
    assert any(t.get("status") == "warn" and "理解摘要" in t.get("summary", "") for t in traj)


# ---------------------------------------------------------------------------
# 验证门：通过 / 失败 / 重试 / 语法门
# ---------------------------------------------------------------------------


def test_verify_gate_runs_tests_and_blocks_on_failure(env, monkeypatch):
    """实现类步骤收尾自动跑测试；失败且额度用尽 → 步骤 blocked + 任务 blocked。"""
    _set_cfg(monkeypatch, verify_max_retries=0)
    bridge = CodeWorkspaceBridge()
    bridge.file_write("tests/test_bad.py", "def test_bad():\n    assert 1 == 2\n", session_id="s1")
    bridge.file_write("utils.py", "def slugify(t):\n    return t\n", session_id="s1")

    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_bad.py"], db_path=None)
    task_flow.confirm_plan("s1")

    result = task_flow.finish_step_with_verify(
        tid, "s2", result_ref="实现 slugify（utils.py）", tool="file_write"
    )
    verify = result["verify"]
    assert verify["mode"] == "pytest" and verify["ran"] is True
    assert verify["failed"] == 1 and verify["passed"] == 0
    assert verify["ok"] is False and verify["exit_code"] != 0
    assert result["retry"] is False and result["retries_left"] == 0
    fresh = task_store.get_task(tid)
    assert fresh["status"] == "blocked"
    assert fresh["steps"][1]["status"] == "blocked"
    assert "验证门" in fresh["steps"][1]["result_ref"]
    assert env["audits"] and env["audits"][-1]["phase"] == "verify_gate"
    assert env["audits"][-1]["task_id"] == tid and env["audits"][-1]["timeout"] is False


def test_verify_gate_passes_and_marks_done(env, monkeypatch):
    _set_cfg(monkeypatch)
    bridge = CodeWorkspaceBridge()
    bridge.file_write("utils.py", "def slugify(t):\n    return t.lower()\n", session_id="s1")
    bridge.file_write(
        "tests/test_utils.py",
        "from utils import slugify\n\n\ndef test_lower():\n    assert slugify('AB') == 'ab'\n",
        session_id="s1",
    )
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_utils.py"])
    task_flow.confirm_plan("s1")

    result = task_flow.finish_step_with_verify(tid, "s2", result_ref="实现 slugify", tool="file_write")
    assert result["verify"]["ok"] is True and result["verify"]["passed"] == 1
    fresh = task_store.get_task(tid)
    assert fresh["steps"][1]["status"] == "done"
    assert "验证门 pytest] 通过" in fresh["steps"][1]["result_ref"]


def test_verify_gate_retry_window_then_block(env, monkeypatch):
    """第一次失败仍有额度 → retry=True 且任务不锁死；额度耗尽 → blocked。"""
    _set_cfg(monkeypatch, verify_max_retries=1)
    bridge = CodeWorkspaceBridge()
    bridge.file_write("tests/test_bad.py", "def test_bad():\n    assert 1 == 2\n", session_id="s1")
    bridge.file_write("utils.py", "x = 1\n", session_id="s1")
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_bad.py"])
    task_flow.confirm_plan("s1")

    first = task_flow.finish_step_with_verify(tid, "s2", result_ref="实现", tool="file_write")
    assert first["retry"] is True and first["retries_left"] == 1, first
    assert first["task_status"] == "", "还有额度时不锁任务"
    assert task_store.get_task(tid)["status"] == "running"

    second = task_flow.finish_step_with_verify(tid, "s2", result_ref="再试一次", tool="file_write")
    assert second["retry"] is False and second["retries_left"] == 0
    assert task_store.get_task(tid)["status"] == "blocked"
    assert task_store.get_task(tid)["steps"][1]["verify_attempts"] == 2


def test_verify_gate_falls_back_to_compile_gate(env, monkeypatch):
    """没有测试可跑 → 语法门；语法错误判失败，修好再验通过。"""
    _set_cfg(monkeypatch)
    bridge = CodeWorkspaceBridge()
    bridge.file_write("broken.py", "def f(:\n    pass\n", session_id="s1")
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["broken.py"])
    task_flow.confirm_plan("s1")

    failed = task_flow.finish_step_with_verify(tid, "s2", result_ref="实现 broken.py", tool="file_write")
    assert failed["verify"]["mode"] == "py_compile" and failed["verify"]["ok"] is False
    assert failed["verify"]["errors"] >= 1

    # 修好（清掉引用里的坏文件，换成能编译的）
    bridge.file_write("broken.py", "def f():\n    return 1\n", session_id="s1")
    task_store.set_steps(tid, [{"id": "s1", "desc": "探查", "type": "explore"},
                               {"id": "s2", "desc": "实现", "type": "code"}])
    task_store.add_file_refs(tid, ["broken.py"])
    task_store.set_status(tid, task_store.STATUS_RUNNING)
    ok = task_flow.finish_step_with_verify(tid, "s2", result_ref="修好 broken.py", tool="file_write")
    assert ok["verify"]["ok"] is True, ok.get("verify")
    assert ok["verify"]["mode"] == "py_compile"


def test_verify_gate_skips_when_nothing_to_verify(env, monkeypatch):
    """无测试且无（存在的）.py → 记「跳过」而不是判失败。"""
    _set_cfg(monkeypatch)
    task = task_store.create_task(
        "s1", "只改配置",
        steps=[{"id": "s1", "desc": "调整配置", "type": "code"}],
        status=task_store.STATUS_RUNNING,
    )
    tid = task["task_id"]
    result = task_flow.finish_step_with_verify(tid, "s1", result_ref="只改了配置项，没有代码文件", tool="file_write")
    assert result["verify"]["ran"] is False, result.get("verify")
    assert result["verify"].get("skipped_reason") == "no_target"
    assert task_store.get_task(tid)["steps"][0]["status"] == "done"
    assert "跳过" in task_store.get_task(tid)["steps"][0]["result_ref"]


def test_plan_mentioned_files_are_not_verify_targets(env, monkeypatch):
    """计划里提到但还没写的文件不能当验证目标（避免误判失败）。"""
    _set_cfg(monkeypatch)
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)  # s2 desc 里提到 utils.py
    tid = task["task_id"]
    task_flow.confirm_plan("s1")
    result = task_flow.finish_step_with_verify(tid, "s2", result_ref="实现 utils.py", tool="file_write")
    assert result["verify"]["ran"] is False and result["verify"]["ok"] is True, result.get("verify")
    assert task_store.get_task(tid)["steps"][1]["status"] == "done"


def test_audit_only_records_without_blocking(env, monkeypatch):
    """audit_only：验证失败只记录，不拦（步骤照模型申报落 done）。"""
    _set_cfg(monkeypatch, verify_audit_only=True)
    bridge = CodeWorkspaceBridge()
    bridge.file_write("tests/test_bad.py", "def test_bad():\n    assert 1 == 2\n", session_id="s1")
    bridge.file_write("utils.py", "x = 1\n", session_id="s1")
    task = task_flow.create_task_from_plan("s1", "目标", PLAN_2)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_bad.py"])
    task_flow.confirm_plan("s1")

    result = task_flow.finish_step_with_verify(tid, "s2", result_ref="实现", tool="file_write")
    assert result["verify"]["ok"] is False and result["verify"]["audit_only"] is True
    fresh = task_store.get_task(tid)
    assert fresh["steps"][1]["status"] == "done", "audit_only 不拦"
    assert fresh["status"] != "blocked"
    assert env["audits"] and env["audits"][-1]["audit_only"] is True


def test_needs_verification_scope_and_outcome_fields(env):
    assert task_verify.needs_verification({"type": "code"})
    assert task_verify.needs_verification({"type": "test"})
    assert not task_verify.needs_verification({"type": "explore"})
    assert not task_verify.needs_verification({"type": "verify"})

    # 正交字段齐全（timeout/error/exit 分开）
    outcome = task_verify._empty_outcome("pytest")
    assert {"exit_code", "passed", "failed", "errors", "timeout", "error"} <= set(outcome)
    assert task_verify.format_outcome({"mode": "pytest", "ran": True, "ok": False, "timeout": True}).startswith(
        "[验证门 pytest] 超时"
    )
    assert json.dumps({"ok": True})  # keep json import used
