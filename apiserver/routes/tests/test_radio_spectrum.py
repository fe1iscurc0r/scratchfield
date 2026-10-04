"""Y-04 验收测试：SDR 实时频谱 / 瀑布图 WebSocket 端点。

覆盖：
  1. WS 端点推送帧结构完整（type/center_freq_hz/freq_hz/spectrum_db/degraded）
  2. 频率联动：先设频再连 WS，帧的 center 反映新频率
  3. 无真机诚实降级：默认 SPECTRUM_SOURCE=sim → degraded=true, source=sim

运行：python -m pytest apiserver/routes/tests/test_radio_spectrum.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth
from apiserver.routes import radio as radio_module


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + mock 串口 + 仿真频谱源 + 真实 app。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    monkeypatch.setenv("IC705_PORT", "mock")
    monkeypatch.setenv("SPECTRUM_SOURCE", "sim")
    radio_module._reset_radio()
    from apiserver.api_server import app

    return TestClient(app)


def _receive_frame(client: TestClient) -> dict:
    with client.websocket_connect("/api/radio/spectrum/ws") as ws:
        return ws.receive_json()


def test_spectrum_ws_frame_shape(client):
    """帧结构完整且为仿真降级。"""
    frame = _receive_frame(client)
    assert frame["type"] == "spectrum"
    assert frame["center_freq_hz"] > 0
    assert frame["center_freq_mhz"] > 0
    assert frame["sample_rate"] > 0
    assert frame["cols"] > 0
    assert len(frame["freq_hz"]) == frame["cols"]
    assert len(frame["spectrum_db"]) == frame["cols"]
    # 无真机 → 诚实降级
    assert frame["degraded"] is True
    assert frame["source"] == "sim"


def test_spectrum_ws_frequency_linkage(client):
    """设频到 14.074 MHz 后，WS 帧中心频率联动更新。"""
    resp = client.post("/api/radio/frequency", json={"freq_mhz": 14.074})
    assert resp.status_code == 200

    frame = _receive_frame(client)
    assert frame["center_freq_hz"] == 14_074_000
    assert frame["center_freq_mhz"] == 14.074
    # 频率轴围绕 14.074 MHz 展开
    assert min(frame["freq_hz"]) >= 14_074_000 - 1
