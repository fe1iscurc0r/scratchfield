# -*- coding: utf-8 -*-
"""agent-66 测试（W66-01/03/06/07 验收，合并单文件）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eda_parasite import EDACommander, replica_target_plan
from postgres_query_mcp import PostgresQueryMCP
from workorder_state_machine import PENDING_APPROVAL, LoopDetector, WorkOrder

from mcpserver.sentinel_intel.collectors.passive import PASSIVE_COLLECTORS, collect


# ---- W66-01 被动 OSINT 收集器 ----
def test_all_six_collectors_return_structured_dict():
    for name in PASSIVE_COLLECTORS:
        r = collect(name, "demo")
        assert isinstance(r, dict) and r.get("ok") is True and r.get("mock") is True


def test_collector_mock_degrade_on_unknown():
    assert collect("nonexistent", "x") is None


# ---- W66-03 工单状态机 ----
def test_gate_not_approved_task_not_advance():
    wo = WorkOrder("w1", approval_gates=["gate-a"])
    assert wo.try_advance() == PENDING_APPROVAL
    wo.resolve_gate("gate-a", "bad-token")  # 错误令牌不 resolve
    assert wo.try_advance() == PENDING_APPROVAL
    wo.resolve_gate("gate-a", "APPROVED")
    assert wo.try_advance() == "gate.resolved"


def test_loop_detector_break_loop_after_3():
    d = LoopDetector(max_rounds=3)
    assert d.track("t", "i") is None
    assert d.track("t", "i") is None
    assert "BREAK-LOOP" in d.track("t", "i")


# ---- W66-06 EDA 寄生控制链 ----
def test_eda_typed_action_mock():
    c = EDACommander(api_available=False)
    r = c.typed_action("place_symbol", ref="R1")
    assert r["ok"] is True and r.get("mock") is True
    assert c.typed_action("bad_action")["ok"] is False


def test_eda_replica_plan_dual_channel():
    plan = replica_target_plan()
    assert "AntiHunter" in plan["replica"]["node"]
    assert "双通道" in plan["dual_channel"] or "屏幕" in plan["dual_channel"]


# ---- W66-07 PG 查询 MCP ----
def test_pg_mock_degrade_and_p3_status():
    m = PostgresQueryMCP()
    assert m.list_schema() == []  # 未连接 mock 降级
    assert m.query("SELECT 1") is None
    assert "P3" in m.status
