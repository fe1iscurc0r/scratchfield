import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
# -*- coding: utf-8 -*-
"""
TB04：OpenAI Realtime 适配器 connect/disconnect/is_active 测试。

覆盖：mock 诚实降级（无 key / 握手失败）、realtime 成功路径、
disconnect 清理、manual_interrupt response.cancel 发送、api_key 占位符识别。
全部离线运行（WebSocket 用 FakeWS 打桩，不访问网络）。
"""

import json

import pytest

from voice.input.voice_realtime.adapters.openai_adapter import OpenAIVoiceClientAdapter


class FakeWS:
    """FakeWS：websockets 连接打桩对象，记录发送内容并可控关闭。"""

    def __init__(self):
        self.sent = []
        self.closed = False
        self.close_code = None

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def close(self):
        self.closed = True
        self.close_code = 1000


@pytest.fixture
def adapter():
    """默认适配器实例（无 key → mock 路径由各用例自行控制）"""
    return OpenAIVoiceClientAdapter(api_key="", base_url="wss://test.local/v1/realtime")


# ---------- mock 诚实降级路径 ----------

@pytest.mark.parametrize("bad_key", ["", "your-api-key", "sk-xxx", "  "])
def test_placeholder_key_falls_back_to_mock(bad_key):
    """api_key 缺失或为占位符时，connect 诚实降级为 mock 并显式标注"""
    ad = OpenAIVoiceClientAdapter(api_key=bad_key)
    assert ad.connect() is True
    assert ad.mode == 'mock'
    status = ad.get_status()
    assert status['mode'] == 'mock'
    assert 'MOCK' in status['note']
    assert ad.is_active() is True  # mock 模式连接后接口可用


def test_handshake_failure_falls_back_to_mock(monkeypatch):
    """有 key 但握手失败（网络/认证）→ 降级 mock + 错误回调触发"""
    ad = OpenAIVoiceClientAdapter(api_key="sk-real", base_url="wss://test.local/v1/realtime")
    monkeypatch.setattr(
        ad, "_open_realtime_ws",
        lambda: (_ for _ in ()).throw(ConnectionRefusedError("boom")),
    )
    errors = []
    ad.set_callbacks(on_error=lambda e: errors.append(e))
    assert ad.connect() is True
    assert ad.mode == 'mock'
    assert isinstance(errors[0], ConnectionRefusedError)


# ---------- realtime 真实路径 ----------

def test_realtime_connect_success(monkeypatch):
    """握手成功 → realtime 模式、session.update 已发送、is_active 为真"""
    ad = OpenAIVoiceClientAdapter(api_key="sk-real", model="gpt-4o-realtime-preview",
                                  voice="echo", base_url="wss://test.local/v1/realtime")
    fake = FakeWS()
    statuses = []
    ad.set_callbacks(on_status=lambda s: statuses.append(s))

    async def fake_open():
        await fake.send(json.dumps({"type": "session.update", "session": {}}))
        return fake

    monkeypatch.setattr(ad, "_open_realtime_ws", fake_open)
    assert ad.connect() is True
    assert ad.mode == 'realtime'
    assert ad.is_active() is True
    assert fake.sent[0]["type"] == "session.update"
    assert 'connected' in statuses


def test_realtime_manual_interrupt_sends_cancel(monkeypatch):
    """realtime 模式下 manual_interrupt 发送 response.cancel 事件"""
    ad = OpenAIVoiceClientAdapter(api_key="sk-real", base_url="wss://test.local/v1/realtime")
    fake = FakeWS()

    async def fake_open():
        return fake

    monkeypatch.setattr(ad, "_open_realtime_ws", fake_open)
    ad.connect()
    assert ad.manual_interrupt() is True
    assert fake.sent[-1] == {"type": "response.cancel"}


def test_mock_mode_manual_interrupt_returns_false(adapter):
    """mock 模式下 manual_interrupt 诚实返回 False（无真实会话）"""
    adapter.connect()  # 无 key → mock
    assert adapter.manual_interrupt() is False


# ---------- disconnect 清理 ----------

def test_realtime_disconnect_closes_ws(monkeypatch):
    """realtime 模式 disconnect 关闭 WebSocket、状态回调 disconnected、is_active 翻转"""
    ad = OpenAIVoiceClientAdapter(api_key="sk-real", base_url="wss://test.local/v1/realtime")
    fake = FakeWS()
    statuses = []
    ad.set_callbacks(on_status=lambda s: statuses.append(s))

    async def fake_open():
        return fake

    monkeypatch.setattr(ad, "_open_realtime_ws", fake_open)
    ad.connect()
    assert ad.is_active() is True

    ad.disconnect()
    assert fake.closed is True
    assert ad.is_active() is False
    assert ad.get_status()['mode'] == 'stub'
    assert 'disconnected' in statuses


def test_mock_disconnect_deactivates(adapter):
    """mock 模式 disconnect 后不再活跃"""
    adapter.connect()
    assert adapter.is_active() is True
    adapter.disconnect()
    assert adapter.is_active() is False


def test_repeated_connect_is_idempotent(monkeypatch):
    """已连接时重复 connect 不重复握手"""
    ad = OpenAIVoiceClientAdapter(api_key="sk-real", base_url="wss://test.local/v1/realtime")
    calls = {"n": 0}
    fake = FakeWS()

    async def fake_open():
        calls["n"] += 1
        return fake

    monkeypatch.setattr(ad, "_open_realtime_ws", fake_open)
    assert ad.connect() is True
    assert ad.connect() is True
    assert calls["n"] == 1
