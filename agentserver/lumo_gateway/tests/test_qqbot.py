"""QQBotAdapter 单元测试：退避 / 去重 / 事件归一化 / 出站发送 / 握手。"""

from __future__ import annotations

import asyncio
import json
import random

import httpx

from agentserver.lumo_gateway.adapters.qqbot import (
    DEFAULT_INTENTS,
    EVENT_C2C_MESSAGE_CREATE,
    EVENT_GROUP_AT_MESSAGE_CREATE,
    QQBotAdapter,
    reconnect_delay,
)
from agentserver.lumo_gateway.models import InboundMessage, OutboundMessage


def _make_adapter(**kw) -> QQBotAdapter:
    return QQBotAdapter("123456", "secret-token", **kw)


# ---------- 指数退避 ----------


def test_reconnect_delay_exponential_backoff(monkeypatch) -> None:
    """退避：1s → 2s → 4s，封顶 60s（jitter 归零验证确定性部分）。"""
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
    assert reconnect_delay(1, 1.0, 60.0) == 1.0
    assert reconnect_delay(2, 1.0, 60.0) == 2.0
    assert reconnect_delay(3, 1.0, 60.0) == 4.0
    assert reconnect_delay(8, 1.0, 60.0) == 60.0


def test_reconnect_delay_jitter_bounded() -> None:
    """带 jitter 时结果不超过 cap + 0.5，且不小于确定性部分。"""
    for attempt in (1, 2, 3, 8):
        d = reconnect_delay(attempt, 1.0, 60.0)
        raw = min(1.0 * (2 ** (attempt - 1)), 60.0)
        assert raw <= d <= raw + 0.5


# ---------- 鉴权 / 去重 ----------


def test_auth_header() -> None:
    """Bot {appid}.{token} 头格式。"""
    assert _make_adapter()._auth_header() == "Bot 123456.secret-token"


def test_msg_dedup_lru() -> None:
    """同 msg_id 第二次命中；LRU 超容量淘汰最旧。"""
    ad = _make_adapter(dedup_cache=2)
    assert ad._is_dup("a") is False
    assert ad._is_dup("a") is True  # 重复命中
    assert ad._is_dup("b") is False
    assert ad._is_dup("c") is False  # 触发淘汰 a
    assert "a" not in ad._dedup
    assert list(ad._dedup) == ["b", "c"]


# ---------- 入站事件归一化 ----------


def test_dispatch_c2c_emits_inbound() -> None:
    """C2C 事件 → InboundMessage 且同 msg_id 去重不重复投递。"""

    async def _run() -> None:
        ad = _make_adapter()
        got: list[InboundMessage] = []

        async def cb(msg: InboundMessage) -> None:
            got.append(msg)

        ad.set_on_message(cb)
        frame = {
            "op": 0, "t": EVENT_C2C_MESSAGE_CREATE, "s": 1,
            "d": {"id": "m1", "author": {"id": "u1"}, "content": "你好"},
        }
        await ad._dispatch(frame)
        assert len(got) == 1
        m = got[0]
        assert isinstance(m, InboundMessage)
        assert m.platform == "qq"
        assert m.user_id == "u1"
        assert m.msg_id == "m1"
        assert m.content == "你好"
        assert m.group_id is None
        # 同 msg_id 重复事件 → 去重跳过
        await ad._dispatch(frame)
        assert len(got) == 1
        await ad.close()

    asyncio.run(_run())


def test_dispatch_group_at_sets_group_id() -> None:
    """群@ 事件 → group_id 取自 group_openid。"""

    async def _run() -> None:
        ad = _make_adapter()
        got: list[InboundMessage] = []

        async def cb(msg: InboundMessage) -> None:
            got.append(msg)

        ad.set_on_message(cb)
        frame = {
            "op": 0, "t": EVENT_GROUP_AT_MESSAGE_CREATE, "s": 2,
            "d": {"id": "m2", "author": {"id": "u2"}, "group_openid": "grp1", "content": "@bot 你好"},
        }
        await ad._dispatch(frame)
        assert len(got) == 1
        assert got[0].group_id == "grp1"
        assert got[0].user_id == "u2"
        await ad.close()

    asyncio.run(_run())


def test_dispatch_unknown_event_ignored() -> None:
    """非目标事件（如 MESSAGE_REACT）不投递。"""

    async def _run() -> None:
        ad = _make_adapter()
        got: list[InboundMessage] = []

        async def cb(msg: InboundMessage) -> None:
            got.append(msg)

        ad.set_on_message(cb)
        await ad._dispatch({"op": 0, "t": "MESSAGE_REACT", "s": 3, "d": {"id": "x"}})
        assert got == []
        await ad.close()

    asyncio.run(_run())


# ---------- 出站 REST 发送 ----------


class _FakeRespOK:
    def raise_for_status(self) -> None:
        return None


class _FakeRespFail:
    def raise_for_status(self) -> None:
        request = httpx.Request("POST", "http://127.0.0.1:8000")
        raise httpx.HTTPStatusError(
            "boom",
            request=request,
            response=httpx.Response(500, request=request),
        )


class _FakeHttp:
    def __init__(self, resp) -> None:
        self.resp = resp
        self.is_closed = False
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.calls.append((url, json or {}, headers or {}))
        return self.resp

    async def aclose(self) -> None:
        self.is_closed = True


def test_send_success() -> None:
    """C2C 出站：POST /v2/users/{user_id}/messages，body 含 msg_type/content/msg_id。"""

    async def _run() -> None:
        ad = _make_adapter()
        ad._http = _FakeHttp(_FakeRespOK())
        out = OutboundMessage(platform="qq", user_id="u1", content="你好", msg_id="m1", group_id=None)
        assert await ad.send(out) is True
        url, body, headers = ad._http.calls[0]
        assert url.endswith("/v2/users/u1/messages")
        assert body == {"msg_type": 0, "content": "你好", "msg_id": "m1"}
        assert headers["Authorization"] == "Bot 123456.secret-token"
        await ad.close()

    asyncio.run(_run())


def test_send_group_uses_group_endpoint() -> None:
    """群出站：POST /v2/groups/{group_id}/messages。"""

    async def _run() -> None:
        ad = _make_adapter()
        ad._http = _FakeHttp(_FakeRespOK())
        out = OutboundMessage(platform="qq", user_id="u1", content="hi", msg_id="", group_id="grp1")
        assert await ad.send(out) is True
        assert ad._http.calls[0][0].endswith("/v2/groups/grp1/messages")
        await ad.close()

    asyncio.run(_run())


def test_send_failure_returns_false() -> None:
    """出站 HTTP 错误 → 返回 False（降级纪律，不抛）。"""

    async def _run() -> None:
        ad = _make_adapter()
        ad._http = _FakeHttp(_FakeRespFail())
        out = OutboundMessage(platform="qq", user_id="u1", content="hi")
        assert await ad.send(out) is False
        await ad.close()

    asyncio.run(_run())


# ---------- WS 握手 ----------


class _FakeWS:
    """websockets ClientConnection 替身：按序吐帧、记录发送。"""

    def __init__(self, frames: list[dict]) -> None:
        self._frames = list(frames)
        self.sent: list[dict] = []

    async def recv(self):
        if not self._frames:
            await asyncio.sleep(3600)  # 帧耗尽即阻塞（测试不触发）
        return json.dumps(self._frames.pop(0))

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self) -> None:
        pass


def test_handshake_sequence() -> None:
    """Hello(op10) → Identify(op2) → READY：识别帧 token/intents/shard 正确。"""

    async def _run() -> None:
        ad = _make_adapter()
        ws = _FakeWS([
            {"op": 10, "d": {"heartbeat_interval": 30000}},
            {"op": 0, "t": "READY", "s": 1, "d": {}},
        ])
        ad._ws = ws
        await ad._handshake()
        assert ad._hb_interval == 30.0
        assert len(ws.sent) == 1
        identify = ws.sent[0]
        assert identify["op"] == 2
        assert identify["d"]["token"] == "Bot 123456.secret-token"
        assert identify["d"]["intents"] == DEFAULT_INTENTS
        assert identify["d"]["shard"] == [0, 1]
        assert ad._hb_task is not None
        ad._hb_task.cancel()
        try:
            await ad._hb_task
        except asyncio.CancelledError:
            pass
        ad._hb_task = None
        await ad.close()

    asyncio.run(_run())
