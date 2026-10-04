"""W120-01 验收：全链路 trace（生成/沿用、span 嵌套与耗时、落盘回放、信封联动、端点查询）。

对应工单验收：
- 发一次带工具调用的链路 → 能用 trace_id 查到完整 span 链（≥3 span）
- trace_id 在 Lumo 事件信封里一致（信封 trace_id 缺省取当前链路）
- 无记录时查询返回 404 语义（not_found）
"""
from __future__ import annotations

import asyncio

import pytest

from apiserver.event_bus import build_envelope
from apiserver.event_bus import trace as bus_trace
from apiserver.event_bus.event_store import EventStore, reset_event_store_for_tests


@pytest.fixture(autouse=True)
def _isolated_trace_store(tmp_path):
    """trace 落盘隔离到 tmp，避免写进用户目录。"""
    store = EventStore(tmp_path / "trace_store" / "traces.jsonl", buffer_lines=1)
    bus_trace.reset_trace_store_for_tests(store)
    bus_trace.reset_for_tests()
    try:
        yield store
    finally:
        store.close(timeout=1.0)
        bus_trace.reset_trace_store_for_tests(None)
        bus_trace.reset_for_tests()


def test_trace_id_created_and_reused_within_context():
    bus_trace.reset_for_tests()
    assert bus_trace.current_trace_id() is None
    first = bus_trace.get_or_create_trace_id()
    assert len(first) == 32
    assert bus_trace.get_or_create_trace_id() == first  # 同一上下文内沿用

    token = bus_trace.start_trace()
    assert bus_trace.current_trace_id() != first  # 新链路
    assert bus_trace.get_or_create_trace_id() == bus_trace.current_trace_id()
    bus_trace.end_trace(token)


def test_span_nesting_duration_and_error():
    token = bus_trace.start_trace()
    trace_id = bus_trace.current_trace_id()
    try:
        with (
            bus_trace.trace_span("chat.request", session_id="s1") as outer,
            bus_trace.trace_span("tool:exec", tool="exec") as inner,
        ):
                assert inner.parent_id == outer.span_id
        with pytest.raises(RuntimeError), bus_trace.trace_span("tool:boom") as boom:
            raise RuntimeError("炸了")
        assert boom.error.startswith("RuntimeError")
    finally:
        bus_trace.end_trace(token)

    record = bus_trace.get_trace(trace_id)
    assert record is not None and record["span_count"] == 3
    names = [s["name"] for s in record["spans"]]
    assert names == ["chat.request", "tool:exec", "tool:boom"]
    assert all(s["duration_ms"] is not None and s["duration_ms"] >= 0 for s in record["spans"])
    assert record["spans"][0]["attributes"]["session_id"] == "s1"


def test_traces_persist_and_replay_after_memory_reset():
    token = bus_trace.start_trace(path="/api/chat")
    with bus_trace.trace_span("http:POST /api/chat"), bus_trace.trace_span("tool:read", tool="read"):
        pass
    trace_id = bus_trace.end_trace(token)
    bus_trace.flush_traces(timeout=3.0)

    # 清掉内存（模拟进程重启）
    bus_trace.reset_for_tests()
    record = bus_trace.get_trace(trace_id)
    assert record is not None
    assert record["source"] == "store"
    assert [s["name"] for s in record["spans"]] == ["http:POST /api/chat", "tool:read"]


def test_envelope_trace_id_follows_current_trace():
    token = bus_trace.start_trace()
    trace_id = bus_trace.current_trace_id()
    try:
        envelope = build_envelope("lumo.user.input.received", "emit", {"x": 1})
        assert envelope["trace_id"] == trace_id  # W119-02 信封与 W120-01 链路同源
    finally:
        bus_trace.end_trace(token)

    # 无上下文时自动生成，不抛
    bus_trace.reset_for_tests()
    standalone = build_envelope("lumo.reserved", "emit", None)
    assert len(standalone["trace_id"]) == 32


def test_traced_decorator_covers_sync_and_async():
    token = bus_trace.start_trace()
    trace_id = bus_trace.current_trace_id()

    @bus_trace.traced("sync.work")
    def sync_work() -> int:
        return 7

    @bus_trace.traced()
    async def async_work() -> int:
        return 8

    try:
        assert sync_work() == 7
        assert asyncio.run(async_work()) == 8
    finally:
        bus_trace.end_trace(token)

    record = bus_trace.get_trace(trace_id)
    names = [s["name"] for s in record["spans"]]
    assert "sync.work" in names
    assert any(n.endswith("async_work") for n in names)


def test_unknown_trace_returns_none():
    bus_trace.reset_for_tests()
    assert bus_trace.get_trace("deadbeef" * 4) is None
    assert bus_trace.get_trace("") is None
