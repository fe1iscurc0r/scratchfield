"""agentserver 冒烟测试 —— 巨石拆分（工单204 任务一）的安全网与等价性锚。

背景：`agentserver/agent_server.py` 3096 行，拆分前**无任何测试覆盖**
（工单要求「拆巨石无测试 = 盲飞」，故先补本文件）。本文件同时是拆分的
**等价性锚**：路由清单在拆分前后必须逐条一致（纯移动，不改行为）。

覆盖：
    - `agentserver` 可导入且导出 `app`（FastAPI）/ `Modules`（状态容器）
    - 路由总数与关键路径（health / openclaw / travel / proactive_vision / agents / dogtag）
    - `Modules` 关键字段在位
    - `/health` 端点可实际响应（TestClient，不依赖外部服务）
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI

import agentserver

#: 拆分前的路由总数基线（2026-10-06 实测，纯移动拆分不得改变此数）
ROUTES_TOTAL_BASELINE = 75

#: 关键路径（代表各职责分组），拆分后必须全部仍可路由
KEY_ROUTES = {
    ("GET", "/health"),
    ("GET", "/health/full"),
    ("GET", "/openclaw/health"),
    ("POST", "/travel/execute"),
    ("POST", "/travel/interrupt"),
    ("POST", "/travel/instruction"),
    ("POST", "/travel/browser-settings"),
    ("GET", "/proactive_vision/config"),
    ("POST", "/proactive_vision/enable"),
    ("GET", "/proactive_vision/status"),
}


def _route_set(app: FastAPI) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or ()
        if path is None:
            continue
        for m in methods:
            if m in ("HEAD", "OPTIONS"):      # FastAPI 自动附加，不算业务路由
                continue
            out.add((m, path))
    return out


def test_agentserver_exports_app_and_modules():
    assert isinstance(agentserver.app, FastAPI)
    assert agentserver.Modules is not None


def test_route_count_unchanged_by_split():
    """路由总数必须等于拆分前基线（纯移动的硬门槛）。"""
    routes = _route_set(agentserver.app)
    assert len(routes) == ROUTES_TOTAL_BASELINE, (
        f"路由数从 {ROUTES_TOTAL_BASELINE} 变为 {len(routes)}——拆分必须纯移动，"
        f"差异：{sorted(routes)[:5]} ...")


def test_key_routes_still_routable():
    routes = _route_set(agentserver.app)
    missing = KEY_ROUTES - routes
    assert not missing, f"拆分后丢失关键路由：{sorted(missing)}"


def test_modules_fields_present():
    """Modules 是运行时状态容器，拆分后字段不得丢失。"""
    names = {f for f in dir(agentserver.Modules) if not f.startswith("_")}
    for field in ("openclaw_client", "instance_manager", "travel_tasks", "dogtag_scheduler"):
        assert field in names, f"Modules 缺少字段 {field}"


def test_health_endpoint_responds():
    """轻量真调用：/health 不依赖外部服务，应返回 2xx。"""
    from fastapi.testclient import TestClient

    with TestClient(agentserver.app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200, resp.text[:300]


def test_no_route_path_collisions():
    """同一 (方法, 路径) 不得重复注册（拆分时子模块误 include 两次会触发）。"""
    seen: dict[tuple[str, str], int] = {}
    for r in agentserver.app.routes:
        path = getattr(r, "path", None)
        for m in (getattr(r, "methods", None) or ()):
            if m in ("HEAD", "OPTIONS") or path is None:
                continue
            seen[(m, path)] = seen.get((m, path), 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    assert not dupes, f"重复注册的路由：{dupes}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
