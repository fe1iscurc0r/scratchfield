"""LumoClient 单元测试：契约字段 / 成功解析 / 异常降级 / 回复分段。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agentserver.lumo_gateway.lumo_client import LumoClient, split_reply


class _FakeResponse:
    """httpx 响应替身：仅实现用到的 raise_for_status / json。"""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            request = httpx.Request("POST", "http://127.0.0.1:8000")
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=httpx.Response(self._status, request=request),
            )

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """httpx.AsyncClient 替身：记录调用、按序返回预设响应。"""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.is_closed = False
        self.calls: list[dict] = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.responses.pop(0)

    async def aclose(self) -> None:
        self.is_closed = True


def test_build_body_contains_contract_fields() -> None:
    """契约字段：model=lumo / stream=false / session_id / task_type=conversation。"""
    client = LumoClient("http://127.0.0.1:8000", "tok")
    body = client.build_body("你好", "qq_user_1")
    assert body["model"] == "lumo"
    assert body["stream"] is False
    assert body["session_id"] == "qq_user_1"
    assert body["task_type"] == "conversation"
    assert body["messages"] == [{"role": "user", "content": "你好"}]


def test_chat_success_extracts_content() -> None:
    """成功路径：Bearer 头正确、URL 正确、返回 choices[0].message.content。"""

    async def _run() -> None:
        client = LumoClient("http://127.0.0.1:8000", "tok")
        client._client = _FakeClient([_FakeResponse({"choices": [{"message": {"content": "回复"}}]})])
        reply = await client.chat("hi", "s1")
        call = client._client.calls[0]
        assert call["url"] == "http://127.0.0.1:8000/persona/v1/chat/completions"
        assert call["headers"]["Authorization"] == "Bearer tok"
        assert call["json"]["session_id"] == "s1"
        assert reply == "回复"
        fake = client._client
        await client.aclose()
        assert client._client is None
        assert fake.is_closed

    asyncio.run(_run())


def test_chat_http_error_returns_empty() -> None:
    """HTTP 5xx → 降级返回空串（不抛异常）。"""

    async def _run() -> None:
        client = LumoClient("http://127.0.0.1:8000", "tok")
        client._client = _FakeClient([_FakeResponse({}, status=500)])
        assert await client.chat("hi", "s1") == ""
        await client.aclose()

    asyncio.run(_run())


def test_chat_parse_error_returns_empty() -> None:
    """响应缺 choices[0].message.content → 降级返回空串。"""

    async def _run() -> None:
        client = LumoClient("http://127.0.0.1:8000", "tok")
        client._client = _FakeClient([_FakeResponse({"choices": []})])
        assert await client.chat("hi", "s1") == ""
        await client.aclose()

    asyncio.run(_run())


def test_split_reply_segments_long_text() -> None:
    """超长回复按 limit 字分段（中文安全）。"""
    text = "字" * 2001
    segs = split_reply(text, 2000)
    assert segs == ["字" * 2000, "字"]


def test_split_reply_empty_and_short() -> None:
    """空文本返回 []，短文本原样返回。"""
    assert split_reply("") == []
    assert split_reply("hi", 2000) == ["hi"]
