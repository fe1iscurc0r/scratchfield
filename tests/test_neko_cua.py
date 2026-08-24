"""M4 neko_cua 工具测试（mock httpx，不依赖真 NEKO）。"""
from __future__ import annotations

import asyncio
from unittest import mock

import httpx
import pytest

from apiserver import neko_cua


class _FakeResp:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def raise_for_status(self):
        if self.status_code >= 400:
            req = mock.MagicMock()
            resp = mock.MagicMock()
            resp.status_code = self.status_code
            raise httpx.HTTPStatusError("err", request=req, response=resp)

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, responses: dict):
        self._responses = responses
        self.last_path = None
        self.last_headers = None

    async def post(self, path, json=None, headers=None):
        self.last_path = path
        self.last_headers = headers
        status, data = self._responses.get(path, (500, {}))
        return _FakeResp(status, data)


def _patch_client(monkeypatch, responses):
    client = _FakeClient(responses)
    monkeypatch.setattr(neko_cua, "_get_client", lambda: client)
    return client


def test_no_token_failsafe(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "")
    r = asyncio.run(neko_cua.run_neko_action("computer_use", {}))
    assert r["success"] is False
    assert "fail-safe" in r["error"]


def test_unknown_action(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "t")
    r = asyncio.run(neko_cua.run_neko_action("rm_rf", {}))
    assert r["success"] is False
    assert "未知" in r["error"]


def test_success_transparent(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "secret")
    client = _patch_client(monkeypatch, {"/computer_use/run": (200, {"task_id": "t1"})})
    r = asyncio.run(neko_cua.run_neko_action("computer_use", {"instruction": "x"}))
    assert r["success"] is True
    assert r["task_id"] == "t1"
    assert client.last_path == "/computer_use/run"
    assert client.last_headers["Authorization"] == "Bearer secret"


def test_http_error(monkeypatch):
    monkeypatch.setattr(neko_cua, "NEKO_EXEC_TOKEN", "secret")
    _patch_client(monkeypatch, {"/browser_use/run": (401, {})})
    r = asyncio.run(neko_cua.run_neko_action("browser_use", {}))
    assert r["success"] is False
    assert "401" in r["error"]
