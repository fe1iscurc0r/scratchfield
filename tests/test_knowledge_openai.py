"""工单217-A · /v1/knowledge/chat/completions 端到端测试。

验证：鉴权 / 消息校验 / 检索注入逻辑（monkeypatch 检索与上游）/ 上游错误人话分类 /
OpenAI 格式归一。不发真实上游请求（monkeypatch httpx）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # 工单224：_LUMO_PROXY_TOKEN 是 lumo_proxy 的模块级常量——合跑时先加载的测试可能已把它
    # 固化（env 后设无效）→ 直接 patch 常量，不依赖 env 生效时序。
    import apiserver.routes.lumo_proxy as LP
    import apiserver.routes.knowledge_openai as KO

    monkeypatch.setattr(LP, "_LUMO_PROXY_TOKEN", "kt-123", raising=False)
    monkeypatch.setattr(KO, "get_config", lambda: _Cfg())
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(KO.router)
    return TestClient(app), KO


class _Cfg:
    class api:
        base_url = "http://fake-upstream.test/v1"
        api_key = "sk-test"
        model = "test-model"


def _msgs(q="你好", n=1):
    return [{"role": "user", "content": q}] if n == 1 else [
        {"role": "system", "content": "x"}, {"role": "user", "content": q}]


def test_requires_token(client):
    c, _ = client
    assert c.post("/v1/knowledge/chat/completions", json={"messages": _msgs()}).status_code == 401


def test_empty_messages_rejected(client):
    c, _ = client
    r = c.post("/v1/knowledge/chat/completions", json={"messages": []},
               headers={"Authorization": "Bearer kt-123"})
    assert r.status_code == 400


def test_nonstream_with_knowledge_injected(client, monkeypatch):
    """检索命中 → system 注入 upstream messages。"""
    c, KO = client
    injected = {}

    async def fake_retrieval(q):
        return "木质素 NPs 的粒径控制在 100-200nm"

    monkeypatch.setattr(KO, "_query_rag_standalone", fake_retrieval)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            injected["url"] = url
            injected["messages"] = json["messages"]
            return FakeResp()

    monkeypatch.setattr(KO.httpx, "AsyncClient", FakeClient)
    r = c.post("/v1/knowledge/chat/completions", json={"messages": _msgs("粒径多少")},
               headers={"Authorization": "Bearer kt-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion" and body["model"] == "test-model"
    # system 注入在最前且含检索内容
    assert injected["messages"][0]["role"] == "system"
    assert "木质素 NPs" in injected["messages"][0]["content"]


def test_no_injection_when_retrieval_empty(client, monkeypatch):
    c, KO = client
    sent = {}

    async def empty_retrieval(q):
        return ""

    monkeypatch.setattr(KO, "_query_rag_standalone", empty_retrieval)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": []}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent["messages"] = json["messages"]
            return FakeResp()

    monkeypatch.setattr(KO.httpx, "AsyncClient", FakeClient)
    r = c.post("/v1/knowledge/chat/completions", json={"messages": _msgs("闲聊")},
               headers={"Authorization": "Bearer kt-123"})
    assert r.status_code == 200
    assert sent["messages"][0]["role"] == "user"  # 未注入 system


def test_upstream_error_human_hint(client, monkeypatch):
    """402 → 人话'账户欠费'（对齐工单221 分类口径）。"""
    c, KO = client

    async def no_ret(q):
        return ""

    monkeypatch.setattr(KO, "_query_rag_standalone", no_ret)

    class FakeResp:
        status_code = 402
        text = '{"error":"insufficient quota"}'

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResp()

    monkeypatch.setattr(KO.httpx, "AsyncClient", FakeClient)
    r = c.post("/v1/knowledge/chat/completions", json={"messages": _msgs()},
               headers={"Authorization": "Bearer kt-123"})
    assert r.status_code == 402
    assert "欠费" in r.json()["detail"]


def test_retrieval_failure_degrades_to_passthrough(client, monkeypatch):
    """检索抛异常 → 不炸、不注入（铁律5：降级不阻断）。"""
    c, KO = client
    sent = {}

    async def broken(q):
        raise RuntimeError("rag down")

    monkeypatch.setattr(KO, "_query_rag_standalone", broken)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent["messages"] = json["messages"]
            return FakeResp()

    monkeypatch.setattr(KO.httpx, "AsyncClient", FakeClient)
    r = c.post("/v1/knowledge/chat/completions", json={"messages": _msgs()},
               headers={"Authorization": "Bearer kt-123"})
    assert r.status_code == 200
    assert sent["messages"][0]["role"] == "user"
