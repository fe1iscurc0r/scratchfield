"""M4 neko_cua integration 测试（httpx MockTransport，走真实 HTTP 请求链路）。"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio

import httpx

from apiserver import neko_cua


def _install_transport(monkeypatch, handler):
    """用 MockTransport 模拟 NEKO server，替换 _get_client。"""
    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:48915",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(neko_cua, "_get_client", lambda: client)
    return client


def test_end_to_end_computer_use(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "secret")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"task_id": "t123"})

    _install_transport(monkeypatch, handler)
    r = asyncio.run(neko_cua.run_neko_action("computer_use", {"instruction": "打开浏览器"}))

    assert r["success"] is True
    assert r["task_id"] == "t123"
    assert captured["path"] == "/computer_use/run"
    assert captured["auth"] == "Bearer secret"
    assert "instruction" in captured["body"]


def test_end_to_end_browser_use(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    _install_transport(monkeypatch, handler)
    r = asyncio.run(neko_cua.run_neko_action("browser_use", {"url": "https://x.com"}))

    assert r["success"] is True
    assert r["ok"] is True


def test_end_to_end_401(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "wrong")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid credentials"})

    _install_transport(monkeypatch, handler)
    r = asyncio.run(neko_cua.run_neko_action("computer_use", {}))

    assert r["success"] is False
    assert "401" in r["error"]
