"""卷123 W123-01 验收：Task 容器（task_store + 对话元指令）。

覆盖：创建 / 步骤流转 / 暂停恢复 / 重启后可查（新连接读同库）/ 轨迹 / 元指令短路 / [TASK] 段解析。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json

import pytest

from apiserver import task_flow, task_store


@pytest.fixture()
def db(tmp_path):
    """任务库重定向到 tmp（不碰用户真实 message_store.db）。"""
    path = tmp_path / "message_store.db"
    return path


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------


def test_create_task_with_template_steps(db):
    task = task_store.create_task(
        "s1", "给 utils 加一个 slugify 函数并测试",
        steps=task_flow.default_steps(), exec_mode="explore", status=task_store.STATUS_RUNNING,
        db_path=db,
    )
    assert task["task_id"] and task["session_id"] == "s1"
    assert task["status"] == "running" and task["exec_mode"] == "explore"
    assert [s["type"] for s in task["steps"]] == ["explore", "code", "test", "verify"]
    assert [s["id"] for s in task["steps"]] == ["s1", "s2", "s3", "s4"]
    assert all(s["status"] == "pending" for s in task["steps"])
    assert task_store.get_task(task["task_id"], db_path=db)["goal"] == task["goal"]


def test_update_step_transitions_and_result_ref(db):
    task = task_store.create_task("s1", "写个函数", steps=["探查", "实现", "跑测试"], db_path=db)
    tid = task["task_id"]

    running = task_store.update_step(tid, "s2", task_store.STEP_RUNNING, db_path=db)
    assert running["steps"][1]["status"] == "running"

    done = task_store.update_step(
        tid, "s2", task_store.STEP_DONE, result_ref="calc.py:12 新增 slugify", db_path=db
    )
    assert done["steps"][1]["status"] == "done"
    assert done["steps"][1]["result_ref"] == "calc.py:12 新增 slugify"
    assert done["steps"][1]["ts"] > 0

    assert task_store.update_step(tid, "nope", task_store.STEP_DONE, db_path=db) is None
    with pytest.raises(ValueError):
        task_store.update_step(tid, "s1", "weird", db_path=db)


def test_pause_resume_and_status_validation(db):
    task = task_store.create_task("s1", "长任务", steps=["a"], status=task_store.STATUS_RUNNING, db_path=db)
    tid = task["task_id"]

    paused = task_store.pause_task(tid, db_path=db)
    assert paused["status"] == "paused"
    assert task_store.pause_task(tid, db_path=db)["status"] == "paused"  # 幂等

    resumed = task_store.resume_task(tid, db_path=db)
    assert resumed["status"] == "running"
    # 非 paused 状态 resume 不改状态
    task_store.set_status(tid, task_store.STATUS_DONE, db_path=db)
    assert task_store.resume_task(tid, db_path=db)["status"] == "done"
    with pytest.raises(ValueError):
        task_store.set_status(tid, "不存在的状态", db_path=db)


def test_state_survives_restart(db):
    """重启语义：新连接（模拟新进程）读同库拿到完整状态与步骤。"""
    task = task_store.create_task("s1", "重启也要在", steps=["探查", "实现"],
                                  status=task_store.STATUS_RUNNING, db_path=db)
    tid = task["task_id"]
    task_store.update_step(tid, "s1", task_store.STEP_DONE, result_ref="理解摘要：2 个文件受影响", db_path=db)
    task_store.pause_task(tid, db_path=db)

    fresh = task_store.get_task(tid, db_path=db)  # 全新连接
    assert fresh["status"] == "paused"
    assert fresh["steps"][0]["status"] == "done"
    assert "理解摘要" in fresh["steps"][0]["result_ref"]

    listed = task_store.list_tasks("s1", db_path=db)
    assert [t["task_id"] for t in listed] == [tid]
    assert task_store.list_tasks("other-session", db_path=db) == []
    assert task_store.resume_task(tid, db_path=db)["status"] == "running"


def test_trajectory_and_stats(db):
    task = task_store.create_task("s1", "带轨迹的任务", steps=["a", "b"], db_path=db)
    tid = task["task_id"]
    task_store.append_trajectory(tid, step_id="s1", tool="file_read", summary="读了 calc.py", status="done", db_path=db)
    task_store.append_trajectory(tid, step_id="s2", tool="test_run", summary="1 passed", status="done", db_path=db)

    traj = task_store.get_task(tid, db_path=db)["trajectory"]
    assert [t["tool"] for t in traj] == ["file_read", "test_run"]
    assert traj[1]["summary"] == "1 passed" and traj[0]["step_id"] == "s1"
    assert task_store.append_trajectory("no-such-task", tool="x", db_path=db) is None

    counts = task_store.stats(db_path=db)["by_status"]
    assert counts.get("pending") == 1
    summary = task_store.task_summary(task_store.get_task(tid, db_path=db))
    assert "带轨迹的任务" in summary and "进度：0/2" in summary


def test_file_refs_and_git_state(db):
    task = task_store.create_task("s1", "带文件的任务", steps=["a"], git_state="main@abc1234", db_path=db)
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["calc.py", "tests/test_calc.py", "calc.py"], db_path=db)
    fresh = task_store.get_task(tid, db_path=db)
    assert fresh["file_refs"] == ["calc.py", "tests/test_calc.py"], "文件引用去重保序"
    assert fresh["git_state"] == "main@abc1234"
    assert "calc.py" in task_store.task_summary(fresh)


# ---------------------------------------------------------------------------
# 对话元指令
# ---------------------------------------------------------------------------


def test_meta_command_create_and_list(db, monkeypatch):
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    reply = task_flow.run_meta_command("s-meta", "task:create 给 calc.py 加 divide 并测试")
    assert "已建任务" in reply and "探查" in reply and "验证" in reply

    listed = task_flow.run_meta_command("s-meta", "task:list")
    assert "divide" in listed and "running" in listed

    # 卷123 W123-05：不再回落到全局列表（会绕过跨通道隔离）；未登录/无 user_id 时别的会话看不到
    other = task_flow.run_meta_command("s-other", "task:list")
    assert "divide" not in other and "没有可见任务" in other


def test_meta_command_pause_resume_continue(db, monkeypatch):
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    task_flow.run_meta_command("s1", "task:create 长任务")
    tid = task_flow.active_task("s1")["task_id"]

    paused = task_flow.run_meta_command("s1", f"task:pause {tid}")
    assert "已暂停" in paused and task_store.get_task(tid)["status"] == "paused"

    resumed = task_flow.run_meta_command("s1", "task:resume")
    assert "已恢复" in resumed and task_store.get_task(tid)["status"] == "running"

    cont = task_flow.run_meta_command("s1", "task:continue")
    assert "继续任务" in cont and task_store.get_task(tid)["status"] == "running"


def test_meta_command_non_task_text_returns_none(db, monkeypatch):
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    assert task_flow.run_meta_command("s1", "今天天气怎么样") is None
    assert task_flow.run_meta_command("s1", "task:") is None
    assert "未知任务指令" in task_flow.run_meta_command("s1", "task:frobnicate")
    assert "用法" in task_flow.run_meta_command("s1", "task:create")


def test_route_helper_short_circuits(db, monkeypatch):
    """路由辅助函数：命中返回文本，未命中返回 None，异常也不炸主链路。"""
    from apiserver.routes import chat as chat_routes

    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    assert chat_routes._try_task_meta_command("s1", "task:list") is not None
    assert chat_routes._try_task_meta_command("s1", "普通消息") is None

    def _boom(session_id, text):
        raise RuntimeError("boom")

    monkeypatch.setattr(task_flow, "run_meta_command", _boom)
    assert chat_routes._try_task_meta_command("s1", "task:list") is None


# ---------------------------------------------------------------------------
# 模型 [TASK] 段
# ---------------------------------------------------------------------------


def test_extract_and_apply_task_ops(db, monkeypatch):
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    text = (
        "我先把任务登记一下。\n"
        '[TASK]{"op":"create","goal":"给 calc.py 加 divide","steps":['
        '{"desc":"探查","type":"explore"},{"desc":"实现","type":"code"}]}[/TASK]\n'
        "开始吧。"
    )
    ops = task_flow.extract_task_ops(text)
    assert len(ops) == 1 and ops[0]["op"] == "create"

    applied = task_flow.apply_task_ops("s1", ops)
    assert applied[0]["ok"] and applied[0]["steps"] == 2
    tid = applied[0]["task_id"]

    applied2 = task_flow.apply_task_ops(
        "s1", [{"op": "step", "task_id": tid, "step_id": "s2", "status": "done",
                "result_ref": "divide 已实现", "tool": "file_edit"}]
    )
    assert applied2[0]["ok"]
    fresh = task_store.get_task(tid)
    assert fresh["steps"][1]["status"] == "done"
    assert fresh["trajectory"][0]["tool"] == "file_edit"

    applied3 = task_flow.apply_task_ops("s1", [{"op": "complete", "task_id": tid}])
    assert applied3[0]["ok"] and task_store.get_task(tid)["status"] == "done"

    assert task_flow.extract_task_ops("没有任务段") == []
    assert task_flow.extract_task_ops("[TASK]{不是 json}[/TASK]") == []
    bad = task_flow.apply_task_ops("s1", [{"op": "nope"}])
    assert bad[0]["ok"] is False and bad[0]["error"] == "unknown_op"


def test_shared_db_with_message_store(db, monkeypatch):
    """任务与消息同库：message_store 写入不影响 tasks 表，反之亦然。"""
    monkeypatch.setattr(task_store, "_default_db_path", lambda: db)
    from apiserver import message_store

    message_store.append_message("s1", "user", "写个函数", db_path=db)
    task = task_store.create_task("s1", "写个函数", steps=["实现"], db_path=db)

    msgs = message_store.query_session("s1", db_path=db)
    assert len(msgs) == 1 and msgs[0]["data"]["content"] == "写个函数"
    assert task_store.get_task(task["task_id"])["task_id"] == task["task_id"]
    # 同库不同表，schema 互不干扰
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"message_store", "tasks"} <= tables
    assert json.dumps({"ok": True})  # keep json import used
