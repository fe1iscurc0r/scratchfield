"""W119-01 路由级验收：GET /debug/dump/bus 与 /debug/dump/bus/events。

用最小 FastAPI 应用挂载 debug_dump 路由并覆盖鉴权依赖——验证路由存在、返回形状正确、
鉴权确实生效（无 token 401）。不拉起完整 api_server（避免重依赖）。
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apiserver.event_bus import get_bus
from apiserver.routes.bus_dump import router
from apiserver.routes.lumo_proxy import require_proxy_token


def _client(*, authorized: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if authorized:
        app.dependency_overrides[require_proxy_token] = lambda: {"ok": True}
    return TestClient(app)


def test_dump_bus_returns_topic_level_counts():
    bus = get_bus()
    bus.on("w119.probe", lambda e: None)
    bus.emit("w119.probe", {"i": 1})
    bus.emit("w119.probe", {"i": 2})

    resp = _client().get("/debug/dump/bus")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    snapshot = body["bus"]
    assert snapshot["dispatch_total"] >= 2
    assert snapshot["topics"]["w119.probe"]["dispatches"] >= 2
    assert "mode_counts" in snapshot and "ring_size" in snapshot


def test_dump_bus_events_returns_recent_list():
    bus = get_bus()
    bus.on("w119.events", lambda e: None)
    for i in range(3):
        bus.emit("w119.events", {"i": i})

    resp = _client().get("/debug/dump/bus/events", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["count"] == 2
    assert len(body["events"]) == 2
    assert {"topic", "mode", "timestamp", "error"} <= set(body["events"][0])


def test_dump_bus_requires_token():
    resp = _client(authorized=False).get("/debug/dump/bus")
    assert resp.status_code in (401, 403, 503)


def test_dump_bus_history_replays_from_event_store(tmp_path):
    """W119-02：/debug/dump/bus/history 从 event_store 回放（topic 过滤 + 尾部窗口）。"""
    from apiserver.event_bus import build_envelope
    from apiserver.event_bus.event_store import EventStore, reset_event_store_for_tests

    store = EventStore(tmp_path / "event_store" / "events.jsonl", buffer_lines=1)
    for i in range(4):
        store.append(build_envelope("hist.topic", "emit", {"i": i}))
    store.append(build_envelope("hist.other", "emit", {"i": 99}))
    store.flush(timeout=3.0)

    reset_event_store_for_tests(store)
    try:
        resp = _client().get("/debug/dump/bus/history", params={"topic": "hist.topic", "limit": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["scanned"] == 4
        assert body["count"] == 2
        # 尾部窗口：最近两条、新→旧
        assert [e["payload"]["i"] for e in body["events"]] == [3, 2]
        assert body["store"]["written"] == 5
    finally:
        reset_event_store_for_tests(None)


def test_debug_trace_endpoint(tmp_path):
    """W120-01：/debug/trace/<id> 查得到 span 链；未知 id 返回 not_found。"""
    from apiserver.event_bus import trace as bus_trace
    from apiserver.event_bus.event_store import EventStore as _Store

    store = _Store(tmp_path / "traces.jsonl", buffer_lines=1)
    bus_trace.reset_trace_store_for_tests(store)
    bus_trace.reset_for_tests()
    try:
        token = bus_trace.start_trace(path="/api/chat")
        trace_id = bus_trace.current_trace_id()
        with bus_trace.trace_span("http:POST /api/chat"), bus_trace.trace_span("tool:read", tool="read"):
            pass
        bus_trace.end_trace(token)

        resp = _client().get(f"/debug/trace/{trace_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["trace"]["span_count"] == 2
        assert [s["name"] for s in body["trace"]["spans"]] == ["http:POST /api/chat", "tool:read"]

        missing = _client().get("/debug/trace/" + "0" * 32)
        assert missing.status_code == 200
        assert missing.json()["status"] == "not_found"
    finally:
        store.close(timeout=1.0)
        bus_trace.reset_trace_store_for_tests(None)
        bus_trace.reset_for_tests()
