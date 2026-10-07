"""任务级工具调用链摘要验收（工单205 任务一）。

覆盖：显式序列入口（两种形态）/ 错误步骤标记 / 落盘 append + 文件名净化 /
无 caller 与无 telemetry 库时的降级 / audit_and_write 不抛异常。
"""
from __future__ import annotations

import json

from mcpserver import tool_chain_audit as A


def test_summarize_steps_from_strings():
    s = A.summarize_steps("task-1", ["parse_glycan", "to_tree", "parse_glycan"])
    assert s["caller"] == "task-1"
    assert s["step_count"] == 3                 # 步数含重复（还原调用链形状）
    assert s["tools"] == ["parse_glycan", "to_tree"]   # 去重但保序
    assert s["tool_set_size"] == 2
    assert s["source"] == "explicit_steps"


def test_summarize_steps_from_dicts_and_errors():
    steps = [
        {"tool": "analyze_signal", "ts": 100.0, "status": "ok"},
        {"tool": "spectrum_events.ingest_frame", "ts": 101.5, "status": "error", "error_kind": "timeout"},
    ]
    s = A.summarize_steps("task-2", steps, agents=["rf_brain"])
    assert s["step_count"] == 2
    assert s["errors"] and s["errors"][0]["error_kind"] == "timeout"
    assert s["duration_s"] == 1.5
    assert s["agents"] == ["rf_brain"]


def test_empty_steps_is_valid():
    s = A.summarize_steps("task-3", [])
    assert s["step_count"] == 0 and s["tools"] == [] and s["duration_s"] is None


def test_write_summary_appends_and_sanitizes_name(tmp_path):
    p1 = A.write_summary(A.summarize_steps("sess/1:a", ["t1"]), tmp_path)
    p2 = A.write_summary(A.summarize_steps("sess/1:a", ["t2"]), tmp_path)
    assert p1 == p2, "同一 caller 应写同一文件"
    assert "/" not in p1.name and ":" not in p1.name, "文件名必须净化"
    lines = p1.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "应为 append-only"
    assert json.loads(lines[0])["tools"] == ["t1"]


def test_build_chain_summary_degrades_without_inputs(tmp_path):
    assert A.build_chain_summary("")["empty_reason"] == "empty_caller"
    missing = A.build_chain_summary("x", db_path=tmp_path / "nope.db")
    assert missing["empty_reason"] == "no_telemetry_db"
    assert missing["step_count"] == 0


def test_audit_and_write_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(A.DEFAULT_STORE_ENV, str(tmp_path))
    out = A.audit_and_write("task-4", db_path=tmp_path / "nope.db")
    assert isinstance(out, dict)                      # 旁路模块：任何情况都返回 dict
    assert out.get("step_count") == 0


def test_upstream_caller_semantics_is_documented():
    """把"caller 当前被填成 tool_name"这一现状钉在文档里，避免后人误用。"""
    doc = A.summarize_steps.__doc__ or ""
    assert "tool_name" in doc and "mcp_manager.py" in doc, \
        "必须在 docstring 里写明 caller 语义错位的现状与两条路径"
