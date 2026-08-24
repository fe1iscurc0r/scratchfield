"""HealthServer 测试：真实 ThreadingHTTPServer 探活。"""

from __future__ import annotations

import httpx

from agentserver.lumo_gateway.health import HealthServer


class _FakeAdapter:
    def __init__(self, connected: bool) -> None:
        self.connected = connected


def test_health_endpoint_reports_adapter_status() -> None:
    """GET /health → {status: ok, adapters: {name: connected|down}}。"""
    server = HealthServer(
        "127.0.0.1",
        0,
        {"qqbot": _FakeAdapter(True), "lumo": _FakeAdapter(False)},
    )
    port = server.start()
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["adapters"] == {"qqbot": "connected", "lumo": "down"}
    finally:
        server.stop()


def test_health_unknown_path_404() -> None:
    """非 /health 路径 → 404。"""
    server = HealthServer("127.0.0.1", 0, {})
    port = server.start()
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/other")
        assert resp.status_code == 404
    finally:
        server.stop()
