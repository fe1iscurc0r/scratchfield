"""U-02 验收：trace_audit MCP 桥（TraceAuditBridge）+ manifest 挂载测试。

验收点（工单）：
1. audit_records/audit_file 七项审计（合法通过、缺字段失败）
2. run_gate 审查门（干净目录不 FAIL、危险 import FAIL、目标不存在 FAIL）
3. handle_handoff 剥离路由键、未知工具报错、坏参数报错
4. agent-manifest.json 可被 registry 发现，工具清单与实现一致
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.trace_audit.bridge import TraceAuditBridge

REPO_ROOT = Path(__file__).resolve().parents[3]

_EXPECTED_TOOLS = {"audit_records", "audit_file", "run_gate", "list_checklist"}


@pytest.fixture()
def bridge() -> TraceAuditBridge:
    return TraceAuditBridge()


def _ok_record(rid: str = "r1", ts: float = 1724900000.0) -> dict:
    return {"id": rid, "timestamp": ts, "source": "local",
            "type": "log", "owner": "agent"}


def test_audit_records_pass_and_fail(bridge):
    r = bridge.audit_records([_ok_record(), _ok_record("r2", 1724900100.0)])
    assert r["status"] == "ok" and r["verdict"] == "PASS"
    assert r["total_records"] == 2 and all(r["criteria"].values())
    # 缺 owner + id 重复 → 必 FAIL 且 issues 非空
    bad = [_ok_record(), {"id": "r1", "timestamp": 1724900200.0,
                           "source": "local", "type": "log"}]
    r = bridge.audit_records(bad)
    assert r["verdict"] == "FAIL" and r["issues"]
    # 坏参数类型 → error
    assert bridge.audit_records("not-a-list")["status"] == "error"


def test_audit_file_jsonl_and_json(bridge, tmp_path):
    jsonl = tmp_path / "rec.jsonl"
    jsonl.write_text(
        "\n".join(json.dumps(_ok_record(f"r{i}", 1724900000 + i))
                  for i in range(3)), encoding="utf-8")
    r = bridge.audit_file(str(jsonl))
    assert r["status"] == "ok" and r["verdict"] == "PASS"
    assert r["total_records"] == 3
    # JSON 数组文件同样可读
    jf = tmp_path / "rec.json"
    jf.write_text(json.dumps([_ok_record()]), encoding="utf-8")
    assert bridge.audit_file(str(jf))["verdict"] == "PASS"
    # 不存在 / 损坏文件 → error
    assert bridge.audit_file(str(tmp_path / "nope.jsonl"))["status"] == "error"
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{bad json}", encoding="utf-8")
    assert bridge.audit_file(str(broken))["status"] == "error"


def test_run_gate_verdicts(bridge, tmp_path):
    # 干净 python 文件：无危险 → 不为 FAIL（无 LICENSE 至多 WARN）
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    r = bridge.run_gate(str(clean))
    assert r["status"] == "ok" and r["verdict"] in ("PASS", "WARN")
    assert r["files_scanned"] >= 1
    # 危险 import → FAIL
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "bad.py").write_text("import subprocess\n", encoding="utf-8")
    r = bridge.run_gate(str(evil))
    assert r["verdict"] == "FAIL"
    assert any(rk["kind"] == "danger" for rk in r["risks"])
    # 目标不存在 → FAIL
    assert bridge.run_gate(str(tmp_path / "missing"))["verdict"] == "FAIL"


def test_list_checklist_matches_schema(bridge):
    r = bridge.list_checklist()
    assert r["status"] == "ok"
    assert set(r["required_fields"]) == {"id", "timestamp", "source", "type", "owner"}
    assert "workorder" in r["known_types"]
    assert len(r["criteria"]) == 7  # 七项标准


def test_handoff_routing_and_unknown_tool(bridge):
    call = {
        "service_name": "trace_audit",
        "tool_name": "list_checklist",
        "agentType": "mcp",
        "_tool_call_id": "x-3",
        "message": "路由噪声",
        "callback_url": "http://127.0.0.1/none",
        "params": {"arguments": "噪声键"},
    }
    out = json.loads(asyncio.run(bridge.handle_handoff(call)))
    assert out["status"] == "ok" and out["service"] == "trace_audit"
    out = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert out["status"] == "error" and "不支持的工具" in out["error"]


def test_handoff_audit_records_nested_params(bridge):
    """嵌套 params 传参 + 路由键剥离（七项审计直达）。"""
    call = {"tool_name": "audit_records", "service_name": "trace_audit",
            "params": {"records": [_ok_record()]}}
    out = json.loads(asyncio.run(bridge.handle_handoff(call)))
    assert out["status"] == "ok" and out["verdict"] == "PASS"


def test_registry_discovers_trace_audit():
    """硬验收：scan_and_register_mcp_agents 输出必须含 trace_audit。"""
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
    assert "trace_audit" in registered


def test_manifest_commands_match_bridge():
    manifest = json.loads(
        (Path(__file__).resolve().parent.parent / "agent-manifest.json")
        .read_text(encoding="utf-8"))
    assert manifest["name"] == "trace_audit"
    ep = manifest["entryPoint"]
    assert ep == {"module": "mcpserver.trace_audit.bridge",
                  "class": "TraceAuditBridge"}
    commands = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert commands == _EXPECTED_TOOLS
    import importlib
    inst = getattr(importlib.import_module(ep["module"]), ep["class"])()
    for c in _EXPECTED_TOOLS:
        assert callable(getattr(inst, c)), f"bridge 缺少工具实现: {c}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
