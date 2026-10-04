"""modem73_kiss_bridge 测试（R54 验收：KISS 编解码 + 模拟链路可跑通 + control port）。"""
import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
from modem73_kiss_bridge import (
    FEND,
    FESC,
    TFEND,
    TFESC,
    FakeModem73Server,
    _recv_exact,
    control_get_status,
    frame_to_aprs,
    iter_kiss_frames,
    kiss_decode_frame,
    kiss_encode_frame,
    kiss_escape,
    kiss_unescape,
    run_bridge,
)


def _ax25_addr(call: str, ssid: int = 0, last: bool = True) -> bytes:
    """AX.25 呼号编码：6 字符各左移 1 位 + SSID 字节。"""
    out = bytearray()
    for c in call.ljust(6)[:6]:
        out.append((ord(c) << 1) & 0xFF)
    out.append(((ssid & 0x0F) << 1) | (0x01 if last else 0x00))
    return bytes(out)


def test_kiss_escape_roundtrip():
    payload = bytes([0x00, FEND, FESC, 0x42, TFEND, TFESC])
    assert kiss_unescape(kiss_escape(payload)) == payload


def test_kiss_escape_contains_no_raw_fend():
    escaped = kiss_escape(bytes([FEND, FESC]))
    assert FEND not in escaped


def test_encode_decode_roundtrip():
    payload = b"hello-world-payload"
    frame = kiss_encode_frame(payload, port=0)
    port, decoded = kiss_decode_frame(frame)
    assert port == 0
    assert decoded == payload


def test_iter_kiss_frames_splits_and_leaves_partial():
    buf = bytearray()
    buf += kiss_encode_frame(b"AAA")
    buf += kiss_encode_frame(b"BB")[:4]  # 半帧（截掉末尾 FEND）
    frames = iter_kiss_frames(buf)
    assert len(frames) == 1
    port, payload = kiss_decode_frame(frames[0])
    assert payload == b"AAA"
    assert len(buf) > 0  # 半帧残留，等待后续


def test_frame_to_aprs_raw_fallback():
    # 短载荷走 RAW 十六进制回退
    assert frame_to_aprs(b"\x01\x02").startswith("RAW:")


def test_frame_to_aprs_strips_control_and_pid():
    # 标准 AX.25 UI 帧：dst(7)+src(7)+control(0x03)+pid(0xF0)+info
    payload = _ax25_addr("APRS") + _ax25_addr("N7LEM") + bytes([0x03, 0xF0]) + b"hello world"
    assert frame_to_aprs(payload) == "N7LEM>APRS:hello world"


def test_control_get_status_roundtrip():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 18073))
    srv.listen(1)
    srv.settimeout(5)

    def _serve():
        conn, _ = srv.accept()
        with conn:
            hdr = _recv_exact(conn, 4)
            req = json.loads(_recv_exact(conn, int.from_bytes(hdr, "big")).decode("utf-8"))
            assert req["cmd"] == "get_status"
            resp = json.dumps({"channel_state": "rx", "last_snr": 12.5, "rx_frame_count": 7}).encode("utf-8")
            conn.sendall(len(resp).to_bytes(4, "big") + resp)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    time.sleep(0.1)
    status = control_get_status("127.0.0.1", 18073)
    assert status["channel_state"] == "rx"
    assert status["last_snr"] == 12.5
    assert status["rx_frame_count"] == 7
    srv.close()


def test_simulate_end_to_end():
    """--simulate 的端到端：假 MODEM73 注入 3 帧，桥接脚本全部解出。"""
    server = FakeModem73Server("127.0.0.1", 18001, [b"F1", b"F2", b"F3"])
    server.start()
    import time

    time.sleep(0.1)
    received = run_bridge("127.0.0.1", 18001, out_json=False, json_path=None)
    assert received == 3
