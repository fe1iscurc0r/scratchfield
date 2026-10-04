"""N-04 边缘频谱哨兵桥验收测试（sentinel_bridge）

覆盖工单验收点：
1. NDJSON 上报 → schema 校验 → SQLite 入库 → sentinel_query/sentinel_status 可查
2. 三协议（acurite/nexus/kerui）各自字段保真（含负温、battery LOW、cmd）
3. 降级不崩：坏 JSON / 未知协议 / 缺字段 → 跳过计数，不抛异常（串口流不能停摆）
4. mock 模式：未配置串口时 open_serial() 返回 None（无 pyserial 依赖可跑）
5. 未知工具 → error 状态（fail-fast）
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.sentinel_bridge import (  # noqa: E402
    SentinelBridge,
    SentinelStore,
    get_store,
    open_serial,
    reset_store,
)

ACURITE_LINE = json.dumps({
    "src": "sentinel", "protocol": "acurite", "id": 12345,
    "channel": "B", "temperature": 21.5, "humidity": 55,
    "battery": "OK", "crc_ok": True, "rssi_dbm": -60,
    "raw_bits": "10101010",
})
NEXUS_LINE = json.dumps({
    "src": "sentinel", "protocol": "nexus", "id": 99,
    "channel": 1, "temperature": -5.0, "humidity": 40,
    "battery": "LOW", "crc_ok": True, "rssi_dbm": -70,
})
KERUI_LINE = json.dumps({
    "src": "sentinel", "protocol": "kerui", "id": 98765,
    "cmd": 2, "crc_ok": None, "rssi_dbm": -55,
})


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    """每个用例独立 SQLite：环境变量指向临时文件 + 重置模块单例。"""
    monkeypatch.setenv("SENTINEL_DB", str(tmp_path / "sentinel_test.db"))
    monkeypatch.delenv("SENTINEL_SERIAL_PORT", raising=False)
    reset_store()
    yield
    reset_store()


def _handoff(tool_call: dict) -> dict:
    return json.loads(asyncio.run(SentinelBridge().handle_handoff(tool_call)))


# --------------------------------------------------------------------------- #
# 入库 + 查询（happy path）
# --------------------------------------------------------------------------- #

def test_ingest_acurite_and_query_roundtrip():
    r = _handoff({"tool_name": "sentinel_ingest", "line": ACURITE_LINE})
    assert r["status"] == "ok" and r["result"]["ok"] is True
    assert r["result"]["stored"] == 1 and r["result"]["total"] == 1

    q = _handoff({"tool_name": "sentinel_query"})
    assert q["result"]["count"] == 1
    row = q["result"]["readings"][0]
    assert row["protocol"] == "acurite" and row["id"] == 12345
    assert row["channel"] == "B" and row["temperature"] == 21.5
    assert row["humidity"] == 55 and row["battery"] == "OK"
    assert row["crc_ok"] is True and row["rssi_dbm"] == -60
    assert "seq" in row and "ts" in row  # 时序索引


def test_pump_three_protocols_all_stored():
    bridge = SentinelBridge()
    summary = bridge.pump([ACURITE_LINE, NEXUS_LINE, KERUI_LINE])
    assert summary == {"ok": 3, "bad": 0, "total": 3}
    assert get_store().count() == 3


def test_query_filter_by_protocol_and_id():
    bridge = SentinelBridge()
    bridge.pump([ACURITE_LINE, NEXUS_LINE, KERUI_LINE])

    q = _handoff({"tool_name": "sentinel_query", "protocol": "acurite"})
    assert q["result"]["count"] == 1 and q["result"]["readings"][0]["id"] == 12345

    q = _handoff({"tool_name": "sentinel_query", "id": 99})
    assert q["result"]["count"] == 1 and q["result"]["readings"][0]["protocol"] == "nexus"

    q = _handoff({"tool_name": "sentinel_query", "protocol": "kerui"})
    row = q["result"]["readings"][0]
    assert row["cmd"] == 2 and row.get("crc_ok") is None  # kerui 无校验位 → 键省略


def test_status_counts_and_recent():
    bridge = SentinelBridge()
    bridge.pump([ACURITE_LINE, NEXUS_LINE])
    r = _handoff({"tool_name": "sentinel_status", "limit": 5})
    assert r["result"]["count"] == 2
    assert len(r["result"]["readings"]) == 2
    # 最近优先：nexus（后入）在 nexus 之前
    assert r["result"]["readings"][0]["protocol"] == "nexus"


# --------------------------------------------------------------------------- #
# 降级不崩（坏行跳过）
# --------------------------------------------------------------------------- #

def test_bad_json_degraded_skipped():
    bridge = SentinelBridge()
    r = bridge.ingest_line("{ 这不是 JSON")
    assert r["ok"] is False and r["skipped"] == 1
    assert get_store().count() == 0  # 未入库

    # 坏行混在好行之间：好行照常入库，坏行计数跳过，不崩
    summary = bridge.pump([ACURITE_LINE, "{bad", NEXUS_LINE])
    assert summary["ok"] == 2 and summary["bad"] == 1 and summary["total"] == 2


def test_unknown_protocol_degraded():
    bad = json.dumps({"src": "sentinel", "protocol": "no_such_proto", "id": 1})
    bridge = SentinelBridge()
    r = bridge.ingest_line(bad)
    assert r["ok"] is False and "未知协议" in r["error"]
    assert get_store().count() == 0


def test_missing_field_degraded():
    # acurite 缺 temperature（必填）→ 校验拒绝，不崩
    bad = json.dumps({"src": "sentinel", "protocol": "acurite",
                      "id": 1, "humidity": 50})
    bridge = SentinelBridge()
    r = bridge.ingest_line(bad)
    assert r["ok"] is False and get_store().count() == 0


# --------------------------------------------------------------------------- #
# fail-fast 与 mock 模式
# --------------------------------------------------------------------------- #

def test_unknown_tool_returns_error():
    r = _handoff({"tool_name": "sentinel_bogus"})
    assert r["status"] == "error"
    assert "sentinel_bogus" in r["error"]


def test_ingest_missing_line_returns_error():
    r = _handoff({"tool_name": "sentinel_ingest"})
    assert r["status"] == "error"


def test_mock_mode_open_serial_none():
    # 未配置 SENTINEL_SERIAL_PORT → mock 模式，无串口对象（不 import pyserial）
    assert open_serial() is None


if __name__ == "__main__":
    test_ingest_acurite_and_query_roundtrip()
    test_pump_three_protocols_all_stored()
    test_query_filter_by_protocol_and_id()
    test_status_counts_and_recent()
    test_bad_json_degraded_skipped()
    test_unknown_protocol_degraded()
    test_missing_field_degraded()
    test_unknown_tool_returns_error()
    test_ingest_missing_line_returns_error()
    test_mock_mode_open_serial_none()
    print("\n🎉 N-04 哨兵桥全部自测通过")
