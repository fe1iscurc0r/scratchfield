"""X-01 验收测试：CI-V 串口控制 + HamLog 联动。

覆盖：
  1. 频率 BCD 编解码（已知字节 + round-trip）
  2. CI-V 帧构造 / 解析 round-trip
  3. Mock 串口（无真机降级）：设频 / 读频 / 模式 / PTT
  4. 模式映射（名称 ↔ 码对称）
  5. 设频率白名单（越界拒绝）
  6. 端点集成（mock）：status / frequency / mode / ptt
  7. HamLog 联动：通联完成一键进日志库（临时 SQLite）
  8. QSL 卡债角标数据源
  9. 坏数据：非法频率 / 非法模式 / 非法 PTT state

运行：python -m pytest apiserver/routes/tests/test_radio.py -q
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth
from apiserver.routes import radio as radio_module
from apiserver.routes.radio import (
    CIV_CTRL,
    CIV_RADIO,
    CMD_OK,
    CMD_PTT,
    CMD_READ_FREQ,
    CMD_READ_MODE,
    CMD_SET_FREQ,
    CMD_SET_MODE,
    MODE_CODES,
    MODE_NAMES,
    MockSerial,
    RadioError,
    assert_allowed_freq,
    build_frame,
    decode_freq_bcd,
    encode_freq_bcd,
    parse_frame,
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + mock 串口 + 隔离 HamLog 数据目录 + 真实 app。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    monkeypatch.setenv("IC705_PORT", "mock")
    monkeypatch.delenv("HAMLOG_API_URL", raising=False)
    monkeypatch.setenv("HAMLOG_DB_PATH", str(tmp_path / "Log.db"))
    radio_module._reset_radio()
    from apiserver.api_server import app

    return TestClient(app)


def _make_hamlog_db(db_path: Path) -> None:
    """建最小 HamLog log 表（字段与 hamlog_adapter 一致）。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Callsign TEXT, Freq TEXT, Year INTEGER, Month INTEGER, Day INTEGER,
            Time TEXT, Mode TEXT, Power_self TEXT, Power_side TEXT,
            Rst_self TEXT, Rst_side TEXT, QTH TEXT, Device TEXT,
            QSL_RX TEXT, QSL_SEND TEXT, Remarks TEXT, CreateTime TEXT
        )"""
    )
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings (key, value) VALUES ('my_callsign', 'BG5TEST')")
    conn.execute("INSERT INTO settings (key, value) VALUES ('my_grid', 'PL02')")
    conn.commit()
    conn.close()


# ============ 1. 频率 BCD ============


def test_freq_bcd_known_value():
    """7.074 MHz → 已知 5 字节 BCD（LSB first）。"""
    assert encode_freq_bcd(7_074_000) == bytes([0x00, 0x40, 0x07, 0x07, 0x00])
    assert decode_freq_bcd(bytes([0x00, 0x40, 0x07, 0x07, 0x00])) == 7_074_000


@pytest.mark.parametrize(
    "hz", [1_800_000, 3_500_000, 7_074_000, 14_074_000, 50_000_000, 145_500_000, 148_000_000]
)
def test_freq_bcd_roundtrip(hz):
    """encode → decode 还原原频率。"""
    assert len(encode_freq_bcd(hz)) == 5
    assert decode_freq_bcd(encode_freq_bcd(hz)) == hz


def test_freq_bcd_out_of_range():
    """超出 10 位 BCD 范围拒绝。"""
    with pytest.raises(RadioError):
        encode_freq_bcd(10_000_000_000)


# ============ 2. 帧构造 / 解析 ============


def test_build_parse_frame_roundtrip():
    """构造请求帧后解析还原 (to/from/cmd/data)。"""
    frame = build_frame(CMD_SET_FREQ, encode_freq_bcd(14_074_000))
    parsed = parse_frame(frame)
    assert parsed == (CIV_RADIO, CIV_CTRL, CMD_SET_FREQ, encode_freq_bcd(14_074_000))
    assert frame[:2] == b"\xfe\xfe" and frame[-1] == 0xFD


def test_build_frame_with_sub_ptt():
    """PTT 请求带 sub 字节：cmd=0x1C sub=0x00 data=0x01。"""
    frame = build_frame(CMD_PTT, b"\x01", sub=0x00)
    # FE FE A4 E0 1C 00 01 FD
    assert frame == b"\xfe\xfe\xa4\xe0\x1c\x00\x01\xfd"


def test_parse_frame_garbage():
    """坏数据 / 不完整帧返回 None。"""
    assert parse_frame(b"\xfe\xfe") is None
    assert parse_frame(b"garbage") is None
    assert parse_frame(b"\xfe\xfe\xa4\xe0\x03") is None  # 缺 EOM


# ============ 3. Mock 串口（无真机降级） ============


def test_mock_serial_freq():
    """Mock 串口设频 / 读频 round-trip。"""
    m = MockSerial()
    m.write(build_frame(CMD_READ_FREQ))
    assert parse_frame(m.read(99))[3] == encode_freq_bcd(7_074_000)  # 默认 40m

    m.write(build_frame(CMD_SET_FREQ, encode_freq_bcd(145_500_000)))
    assert parse_frame(m.read(99))[2] == CMD_OK
    m.write(build_frame(CMD_READ_FREQ))
    assert decode_freq_bcd(parse_frame(m.read(99))[3]) == 145_500_000


def test_mock_serial_mode_ptt():
    """Mock 串口模式切换 + PTT。"""
    m = MockSerial()
    m.write(build_frame(CMD_SET_MODE, bytes([0x06, 0x01])))  # FM
    m.read(99)
    m.write(build_frame(CMD_READ_MODE))
    _, _, _, data = parse_frame(m.read(99))
    assert data[0] == 0x06  # FM

    m.write(build_frame(CMD_PTT, b"\x01", sub=0x00))
    m.read(99)
    assert m.get_state()["ptt"] is True
    m.write(build_frame(CMD_PTT, b"\x00", sub=0x00))
    m.read(99)
    assert m.get_state()["ptt"] is False


# ============ 4. 模式映射 ============


def test_mode_mapping_symmetric():
    """名称 ↔ 码双向对称。"""
    assert MODE_CODES["USB"] == 0x02
    assert MODE_NAMES[0x02] == "USB"
    assert set(MODE_NAMES) == set(MODE_CODES.values())


# ============ 5. 白名单 ============


@pytest.mark.parametrize("hz", [1_800_000, 14_074_000, 54_000_000, 144_000_000])
def test_whitelist_allowed(hz):
    assert_allowed_freq(hz)  # 不抛异常


@pytest.mark.parametrize("hz", [500_000, 40_000_000, 100_000_000, 1_000_000_000])
def test_whitelist_rejected(hz):
    with pytest.raises(RadioError):
        assert_allowed_freq(hz)


# ============ 6. 端点集成（mock 串口） ============


def test_endpoint_status(client):
    resp = client.get("/api/radio/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["mock"] is True
    assert body["freq_mhz"] == 7.074
    assert body["mode"] == "USB"


def test_endpoint_set_frequency_and_mode(client):
    resp = client.post("/api/radio/frequency", json={"freq_mhz": 14.074})
    assert resp.status_code == 200
    assert resp.json()["freq_mhz"] == 14.074

    resp = client.post("/api/radio/mode", json={"mode": "FM"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "FM"

    resp = client.get("/api/radio/status")
    assert resp.json()["freq_mhz"] == 14.074
    assert resp.json()["mode"] == "FM"


def test_endpoint_set_frequency_out_of_band(client):
    """越界频率 400 MHz（非业余段）→ 422。"""
    resp = client.post("/api/radio/frequency", json={"freq_mhz": 400.0})
    assert resp.status_code == 422


def test_endpoint_ptt(client):
    resp = client.post("/api/radio/ptt", json={"state": "TX"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "TX"
    resp = client.post("/api/radio/ptt", json={"state": "RX"})
    assert resp.json()["state"] == "RX"


# ============ 7. HamLog 联动 ============


def test_endpoint_log_qso_to_hamlog(client, tmp_path):
    _make_hamlog_db(tmp_path / "Log.db")
    resp = client.post(
        "/api/radio/log",
        json={"callsign": "bg8abc", "rst_sent": "59", "rst_rcvd": "57", "remarks": "test qso"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["callsign"] == "BG8ABC"
    assert body["mode"] == "USB"
    assert body["freq_mhz"] == 7.074

    # 校验确实写入 SQLite（callsign 自动转大写、freq/mode 自动填）
    conn = sqlite3.connect(tmp_path / "Log.db")
    row = conn.execute(
        "SELECT Callsign, Freq, Mode, Rst_side, Rst_self, Remarks FROM log"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "BG8ABC"
    assert row[1] == "7.074"
    assert row[2] == "USB"
    assert row[3] == "59"  # Rst_side = 我发给对方 (rst_sent)
    assert row[4] == "57"  # Rst_self = 对方发给我 (rst_rcvd)
    assert row[5] == "test qso"


def test_endpoint_log_qso_no_db(client):
    """HamLog 数据库缺失 → fail-fast 502，绝不静默。"""
    resp = client.post("/api/radio/log", json={"callsign": "BG8ABC"})
    assert resp.status_code == 502
    assert "HamLog" in resp.json()["detail"]


# ============ 8. QSL 卡债 ============


def test_endpoint_qsl_debts(client, tmp_path):
    _make_hamlog_db(tmp_path / "Log.db")
    conn = sqlite3.connect(tmp_path / "Log.db")
    conn.execute(
        "INSERT INTO log (Callsign, Freq, Year, Month, Day, Mode, QSL_SEND, QSL_RX) "
        "VALUES ('BG1AAA', '7.074', 2026, 8, 1, 'USB', '', '')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/api/radio/qsl-debts", params={"direction": "owed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["count"] >= 1
    assert any(d["callsign"] == "BG1AAA" for d in body["debts"])


# ============ 9. 坏数据 ============


def test_bad_mode_rejected(client):
    resp = client.post("/api/radio/mode", json={"mode": "BOGUS"})
    assert resp.status_code == 422


def test_bad_ptt_state_rejected(client):
    resp = client.post("/api/radio/ptt", json={"state": "HOLD"})
    assert resp.status_code == 422
