"""U-01 验收：workflow MCP 桥（WorkflowBridge）+ manifest 挂载测试。

验收点（工单 TRAE_WORKORDER_PROMPT_AGENT_UNIFORM.md）：
1. bridge 各工具在临时 board 上调通（创建/认领/状态/完成/阻塞/事件）
2. handle_handoff 剥离路由键、嵌套 params 兼容、未知工具报错
3. agent-manifest.json 可被 scan_and_register_mcp_agents 发现并注册
4. manifest 工具清单与 bridge 实现一致
5. 与 CLI 同源：WORKFLOW_DB 环境变量决定数据库路径
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.workflow.bridge import WorkflowBridge

REPO_ROOT = Path(__file__).resolve().parents[3]

# manifest invocationCommands 必须登记的 7 个工具
_EXPECTED_TOOLS = {
    "board_create", "board_claim", "board_status", "board_list",
    "board_done", "board_blocked", "event_log",
}


@pytest.fixture()
def bridge(tmp_path) -> WorkflowBridge:
    """临时 SQLite 板实例（与生产同源接口，避免污染仓库根的 workflow.db）。"""
    return WorkflowBridge(db_path=str(tmp_path / "wf_test.db"))


# ---- 工具直连（封装不重写，行为与 Board/claim 一致）----

def test_create_and_status(bridge):
    r = bridge.board_create("T1", title="测试工单", assignee="agent")
    assert r["status"] == "ok" and r["task"]["id"] == "T1"
    assert r["task"]["status"] == "pending"
    # 空 id 拒绝
    assert bridge.board_create(" ")["status"] == "error"
    # 查看
    r = bridge.board_status("T1")
    assert r["task"]["status"] == "pending"
    # 经状态机迁移：pending -> ready 合法
    r = bridge.board_status("T1", set="ready")
    assert r["task"]["status"] == "ready"
    # 不存在的工单报错
    assert bridge.board_status("NOPE")["status"] == "error"


def test_claim_single_winner(bridge):
    bridge.board_create("T2", title="认领测试")
    bridge.board_status("T2", set="ready")
    r1 = bridge.board_claim("T2", owner="o1")
    assert r1["status"] == "ok" and r1["won"] is True
    assert r1["task"]["status"] == "in_progress"
    # 租约内第二个竞争者必输（单赢家语义）
    r2 = bridge.board_claim("T2", owner="o2")
    assert r2["won"] is False


def test_done_enters_in_review(bridge):
    """审查门默认开启：完成进 in_review 而非直接 done。"""
    bridge.board_create("T3", title="完成测试")
    bridge.board_status("T3", set="ready")
    bridge.board_claim("T3", owner="o1")
    r = bridge.board_done("T3")
    assert r["status"] == "ok"
    assert r["task"]["status"] == "in_review"


def test_blocked_requires_reason(bridge):
    bridge.board_create("T4", title="阻塞测试")
    bridge.board_status("T4", set="ready")
    bridge.board_claim("T4", owner="o1")
    # 无 reason 一律拒绝（G-02 硬语义）
    assert bridge.board_blocked("T4", "")["status"] == "error"
    r = bridge.board_blocked("T4", "blocked_wait_external")
    assert r["task"]["status"] == "blocked"
    assert r["task"]["reason_code"] == "blocked_wait_external"


def test_list_and_event_log(bridge):
    bridge.board_create("T5", title="列表测试", assignee="agent")
    bridge.board_create("T6", title="列表测试2", assignee="other")
    r = bridge.board_list()
    assert r["count"] == 2
    r = bridge.board_list(assignee="agent")
    assert r["count"] == 1 and r["tasks"][0]["id"] == "T5"
    # 事件留痕：本实例经手的板操作均入环形缓冲
    r = bridge.event_log(limit=50)
    assert r["count"] > 0
    assert all("event_type" in e for e in r["events"])


def test_duplicate_create_raises(bridge):
    bridge.board_create("T7")
    with pytest.raises(ValueError):
        bridge.board_create("T7")


# ---- handle_handoff 分发 ----

def test_handoff_strips_routing_keys_and_nested_params(bridge):
    call = {
        "service_name": "workflow",
        "tool_name": "board_create",
        "agentType": "mcp",
        "_tool_call_id": "x-1",
        "message": "路由噪声",
        "callback_url": "http://127.0.0.1/none",
        "params": {"id": "H1", "title": "嵌套传参", "arguments": "噪声键"},
    }
    out = json.loads(asyncio.run(bridge.handle_handoff(call)))
    assert out["status"] == "ok" and out["service"] == "workflow"
    assert out["task"]["id"] == "H1" and out["task"]["title"] == "嵌套传参"


def test_handoff_unknown_tool_returns_error(bridge):
    out = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert out["status"] == "error"
    assert "不支持的工具" in out["error"]


def test_handoff_bad_params_returns_error_json(bridge):
    # 无 id 的 board_done → 业务错误以 JSON 返回，不抛裸异常
    out = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "board_done"})))
    assert out["status"] == "error"


# ---- manifest 挂载与一致性 ----

def test_registry_discovers_workflow():
    """硬验收：scan_and_register_mcp_agents 输出必须含 workflow。"""
    import os
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        from mcpserver.mcp_registry import scan_and_register_mcp_agents
        registered = scan_and_register_mcp_agents("mcpserver")
    finally:
        os.chdir(cwd)
    assert "workflow" in registered


def test_manifest_commands_match_bridge():
    manifest = json.loads(
        (Path(__file__).resolve().parent.parent / "agent-manifest.json")
        .read_text(encoding="utf-8"))
    assert manifest["name"] == "workflow"
    ep = manifest["entryPoint"]
    assert ep["module"] == "mcpserver.workflow.bridge"
    assert ep["class"] == "WorkflowBridge"
    commands = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert commands == _EXPECTED_TOOLS
    # entryPoint 可导入可实例化（注册前自检，避免半挂载）
    import importlib
    mod = importlib.import_module(ep["module"])
    inst = getattr(mod, ep["class"])()
    for c in _EXPECTED_TOOLS:
        assert callable(getattr(inst, c)), f"bridge 缺少工具实现: {c}"


def test_workflow_db_env_default(tmp_path, monkeypatch):
    """与 CLI 同源：WORKFLOW_DB 环境变量决定数据库路径。"""
    db = tmp_path / "env_board.db"
    monkeypatch.setenv("WORKFLOW_DB", str(db))
    b = WorkflowBridge()
    assert b.db_path == str(db)
    b.board_create("E1", title="env")
    assert db.exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
