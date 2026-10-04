"""卷189-B 验收测试：调用画像（P50/P95/失败率）+ 熔断（半开/豁免）。

工单验收：
- 熔断：连续失败的工具，5 次失败后第 6 次被短路（tool_circuit_open），冷却后半开；
- 画像：产生 ≥50 条记录后聚合正确；
- 内置核心 agent 不熔断。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver import telemetry  # noqa: E402
from mcpserver.telemetry import (  # noqa: E402
    COOLDOWN_S,
    MIN_SAMPLES,
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CallRecorder,
    CircuitBreaker,
    parse_window,
)

# ---------------------------------------------------------------- 时间源

class FakeClock:
    def __init__(self, t0: float = 1_000_000.0):
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ---------------------------------------------------------------- 画像

def test_recorder_aggregates_50_rows(tmp_path):
    db = tmp_path / "tc.db"
    rec = CallRecorder(db, flush_interval=999)
    for i in range(50):
        ok = i % 10 != 0                    # 每 10 条 1 条失败 → 5 失败
        rec.record("tool_a", duration_ms=100 + i, status="ok" if ok else "error",
                   error_kind="" if ok else "ValueError")
    assert rec.flush() == 50

    st = rec.stats("7d")
    a = st["tool_a"]
    assert a["calls"] == 50
    assert a["errors"] == 5
    assert abs(a["error_rate"] - 0.1) < 1e-6
    assert a["p50_ms"] > 0 and a["p95_ms"] >= a["p50_ms"]
    assert "ValueError" in a["last_error"]


def test_recorder_non_blocking_on_full_queue(tmp_path):
    rec = CallRecorder(tmp_path / "q.db", max_queue=2, flush_interval=999)
    for i in range(5):
        rec.record("t", duration_ms=i)     # 队列满后静默丢弃
    assert rec.dropped >= 3                # 不抛异常、不阻塞


def test_recorder_window_filter(tmp_path):
    rec = CallRecorder(tmp_path / "w.db", flush_interval=999)
    rec.record("t", duration_ms=1)
    rec.flush()
    assert rec.stats("7d")["t"]["calls"] == 1
    assert "t" not in rec.stats("0s")      # 窗口为 0 → 无数据


def test_parse_window():
    assert parse_window("7d") == 7 * 86400
    assert parse_window("24h") == 86400
    assert parse_window("30m") == 1800
    assert parse_window("90s") == 90
    assert parse_window("120") == 120
    assert parse_window("garbage") == 7 * 86400


# ---------------------------------------------------------------- 熔断

def test_breaker_opens_after_min_samples():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    # 前 4 次失败不够样本 → 仍放行
    for _ in range(MIN_SAMPLES - 1):
        assert cb.allow("ext", "adapter") is True
        cb.record("ext", False, source="adapter", error="boom")
    assert cb.state("ext")["state"] == STATE_CLOSED
    # 第 5 次失败 → 达到样本且失败率 100% → 熔断
    cb.record("ext", False, source="adapter", error="boom")
    assert cb.state("ext")["state"] == STATE_OPEN
    # 第 6 次调用被短路
    assert cb.allow("ext", "adapter") is False


def test_breaker_half_open_after_cooldown():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for _ in range(MIN_SAMPLES):
        cb.record("ext", False, source="adapter", error="boom")
    assert cb.allow("ext", "adapter") is False
    clk.advance(COOLDOWN_S + 1)
    assert cb.allow("ext", "adapter") is True           # 半开：放行一次探测
    assert cb.state("ext")["state"] == STATE_HALF_OPEN
    cb.record("ext", True, source="adapter")            # 探测成功 → 复位
    assert cb.state("ext")["state"] == STATE_CLOSED
    assert cb.allow("ext", "adapter") is True


def test_breaker_half_open_probe_failure_reopens():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for _ in range(MIN_SAMPLES):
        cb.record("ext", False, source="adapter", error="boom")
    clk.advance(COOLDOWN_S + 1)
    assert cb.allow("ext", "adapter") is True
    cb.record("ext", False, source="adapter", error="boom2")  # 探测失败
    assert cb.allow("ext", "adapter") is False                # 立即重新熔断


def test_builtin_core_agent_never_breaks():
    """内置（manifest）来源不熔断——防止把自己脑子断了。"""
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for _ in range(50):
        cb.record("academic", False, source="manifest", error="x")
    assert cb.allow("academic", "manifest") is True
    assert cb.state("academic")["state"] == STATE_CLOSED


def test_breaker_success_ratio_below_threshold_keeps_closed():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for i in range(10):
        cb.record("ext", i % 3 != 0, source="adapter")   # 33% 失败 < 50%
    assert cb.state("ext")["state"] == STATE_CLOSED


def test_breaker_window_slides():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for _ in range(MIN_SAMPLES):
        cb.record("ext", False, source="adapter")
    clk.advance(301)                      # 滑出 5 分钟窗口
    assert cb.state("ext")["samples"] == 0


def test_states_lists_non_closed():
    clk = FakeClock()
    cb = CircuitBreaker(now_fn=clk)
    for _ in range(MIN_SAMPLES):
        cb.record("bad", False, source="adapter")
    cb.record("good", True, source="adapter")
    st = cb.states()
    assert "bad" in st and st["bad"]["state"] == STATE_OPEN
    assert "good" not in st


# ---------------------------------------------------------------- unified_call 集成

def _fake_agent_raising():
    class A:
        async def handle_handoff(self, _tool_call):
            raise RuntimeError("kaboom")
    return A()


def test_unified_call_returns_circuit_open(monkeypatch, tmp_path):
    """外部工具连续失败 → 第 6 次 unified_call 直接返回 tool_circuit_open。"""
    from mcpserver import mcp_manager, mcp_registry

    monkeypatch.setenv("MCP_TELEMETRY", "1")
    rec = telemetry.reset_for_tests(tmp_path / "c.db")
    clk = FakeClock()
    telemetry._BREAKER = CircuitBreaker(now_fn=clk)

    mcp_registry.MCP_REGISTRY["fake_ext"] = _fake_agent_raising()
    mcp_registry.MANIFEST_CACHE["fake_ext"] = {"name": "fake_ext", "source": "mcporter"}

    mgr = mcp_manager.get_mcp_manager()
    for _ in range(MIN_SAMPLES):
        out = asyncio.run(mgr.unified_call("fake_ext", {}))
        assert "调用失败" in out or "error" in out
    # 第 6 次：熔断短路
    out = asyncio.run(mgr.unified_call("fake_ext", {}))
    payload = json.loads(out)
    assert payload["error_type"] == "tool_circuit_open"
    mcp_registry.MCP_REGISTRY.pop("fake_ext", None)
    mcp_registry.MANIFEST_CACHE.pop("fake_ext", None)


def test_unified_call_records_profile(monkeypatch, tmp_path):
    """一次调用后画像有记录（tool_calls 表可见）。"""
    from mcpserver import mcp_manager, mcp_registry

    monkeypatch.setenv("MCP_TELEMETRY", "1")
    rec = telemetry.reset_for_tests(tmp_path / "p.db")

    class A:
        async def handle_handoff(self, _tool_call):
            return '{"status": "ok"}'
    mcp_registry.MCP_REGISTRY["ok_tool"] = A()
    mcp_registry.MANIFEST_CACHE["ok_tool"] = {"name": "ok_tool"}

    mgr = mcp_manager.get_mcp_manager()
    asyncio.run(mgr.unified_call("ok_tool", {"tool_name": "x"}))
    rec.flush()
    assert "ok_tool" in rec.stats("7d")
    mcp_registry.MCP_REGISTRY.pop("ok_tool", None)
    mcp_registry.MANIFEST_CACHE.pop("ok_tool", None)
