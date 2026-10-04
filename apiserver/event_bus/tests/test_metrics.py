"""W120-04 验收：Telemetry 指标仪表盘（计数/失败率/延迟/脱敏/端点）。

对应工单验收：
- 模拟请求 + 工具调用 + 总线事件后 summary 数值正确
- 失败率/延迟字段存在且单位明确
- 脱敏断言（注入 token/key 字段不出现）
- 不阻塞主路径（计数器为 O(1) 累加，另有实现佐证）
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apiserver.telemetry import METRICS, record_request_metric, record_tool_metric


@pytest.fixture(autouse=True)
def _clean_metrics():
    METRICS.reset()
    try:
        yield
    finally:
        METRICS.reset()


def test_counts_rates_and_latency_units():
    for status, ms in ((200, 10.0), (200, 20.0), (404, 30.0), (500, 40.0)):
        record_request_metric(path="/api/chat", method="POST", status=status, duration_ms=ms)
    record_tool_metric(tool="read", ok=True, duration_ms=5.0)
    record_tool_metric(tool="read", ok=True, duration_ms=15.0)
    record_tool_metric(tool="exec", ok=False, duration_ms=25.0, error="命令被拒")

    summary = METRICS.snapshot(bus={"dispatch_total": 7, "error_total": 1, "waterfall_veto_total": 2,
                                    "mode_counts": {"emit": 7}, "topics": {"lumo.user.input.received": {}}})
    requests = summary["requests"]
    assert requests["total"] == 4
    assert requests["status_2xx"] == 2 and requests["status_4xx"] == 1 and requests["status_5xx"] == 1
    assert requests["avg_latency_ms"] == 25.0  # (10+20+30+40)/4，单位毫秒

    tools = summary["tools"]
    assert tools["total"] == 3 and tools["ok"] == 2 and tools["failed"] == 1
    assert tools["failure_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert tools["avg_latency_ms"] == 15.0

    assert summary["bus"]["dispatch_total"] == 7
    assert summary["bus"]["waterfall_veto_total"] == 2
    assert summary["uptime_s"] >= 0


def test_recent_errors_sanitized_and_truncated():
    secret = "sk-" + "a" * 40
    record_request_metric(
        path="/api/chat?apiKey=" + secret,
        method="POST",
        status=500,
        duration_ms=1.0,
        error=f"Authorization: Bearer {secret} " + "x" * 500,
    )
    record_tool_metric(tool="exec", ok=False, duration_ms=1.0, error=f"token={secret}")

    errors = METRICS.snapshot()["recent_errors"]
    assert len(errors) == 2
    blob = str(errors)
    assert secret not in blob, "敏感值不应出现在指标输出"
    assert all(len(str(e.get("error") or "")) <= 200 for e in errors)
    assert all(len(str(e.get("path") or "")) <= 200 for e in errors)


def test_summary_endpoint_shape_and_bus_section():
    """端点级：挂载 telemetry 路由后能取到 summary，且含 bus 段与 note。"""
    from apiserver.routes.telemetry import router

    record_request_metric(path="/api/chat", method="POST", status=200, duration_ms=5.0)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/system/telemetry/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    summary = body["summary"]
    assert {"requests", "tools", "bus", "recent_errors", "uptime_s", "note"} <= set(summary)
    assert summary["requests"]["total"] == 1
    assert "dispatch_total" in summary["bus"]


def test_counters_reset_clears_state():
    record_request_metric(path="/api/chat", method="POST", status=200, duration_ms=1.0)
    assert METRICS.snapshot()["requests"]["total"] == 1
    METRICS.reset()
    assert METRICS.snapshot()["requests"]["total"] == 0
    assert METRICS.snapshot()["recent_errors"] == []
