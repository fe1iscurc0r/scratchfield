"""dcp 帧协议测试：编解码往返 / 帧长<50B / CRC 错帧丢弃 / 重传超时 / 去重 / 枚举边界 / 字段对齐 / mock 传输层。"""

from __future__ import annotations

from mcpserver.rf_brain.dcp import (
    Battery,
    Deduplicator,
    MsgType,
    Protocol,
    Transmitter,
    build_report_payload,
    crc16_modbus,
    decode,
    encode,
    parse_report_payload,
)
from mcpserver.rf_brain.dcp.frame import _MAX_PAYLOAD, MAGIC

# ---------- 编解码与 CRC ----------

def test_crc16_modbus_standard_vector() -> None:
    """MODBUS CRC-16 标准向量：b"123456789" → 0x4B37。"""
    assert crc16_modbus(b"123456789") == 0x4B37


def test_report_roundtrip() -> None:
    """REPORT 编解码往返：字段无损。"""
    payload = build_report_payload(
        temperature_c=25.0, humidity_pct=50, battery=Battery.OK,
        rssi_dbm=-85.0, channel="C", protocol="acurite-tower", device_id=4660,
    )
    frame = encode(MsgType.REPORT, seq=1, payload=payload)
    decoded = decode(frame)
    assert decoded is not None
    msg_type, seq, p = decoded
    assert msg_type == MsgType.REPORT
    assert seq == 1
    assert p == payload


def test_frame_max_len_under_50() -> None:
    """所有类型帧长 < 50B（含 COMMAND 最大 payload 42B）。"""
    report = build_report_payload(25.0, 50, Battery.OK, -85.0, "C", "acurite-tower", 4660)
    assert len(encode(MsgType.REPORT, 1, report)) == 16
    assert len(encode(MsgType.ACK, 1)) == 7
    assert len(encode(MsgType.HEARTBEAT, 1)) == 7
    assert len(encode(MsgType.COMMAND, 1, b"\x00" * _MAX_PAYLOAD)) == 49
    # 硬约束：最大帧长 < 50
    assert len(encode(MsgType.COMMAND, 1, b"\x00" * _MAX_PAYLOAD)) < 50


def test_crc_error_returns_none() -> None:
    """CRC 错帧 → decode 返回 None（不抛错）。"""
    payload = build_report_payload(25.0, 50, Battery.OK, -85.0, "C", "acurite-tower", 4660)
    frame = bytearray(encode(MsgType.REPORT, 1, payload))
    frame[5] ^= 0xFF  # 翻转 payload 首字节，破坏 CRC
    assert decode(bytes(frame)) is None


def test_magic_error_returns_none() -> None:
    """magic 错帧 → decode 返回 None。"""
    payload = build_report_payload(25.0, 50, Battery.OK, -85.0, "C", "acurite-tower", 4660)
    frame = bytearray(encode(MsgType.REPORT, 1, payload))
    frame[0] = 0x4D  # 破坏 magic
    frame[1] = 0x52
    assert decode(bytes(frame)) is None


def test_decode_short_frame_returns_none() -> None:
    """过短帧 / 非 bytes → decode 返回 None。"""
    assert decode(b"") is None
    assert decode(b"\xd0\xcc\x01") is None
    assert decode("not-bytes") is None  # type: ignore[arg-type]


# ---------- 重传 / 去重 ----------

class _MockTransport:
    """mock 传输层：send 记录帧，recv 按序吐预设帧（耗尽返回 None=超时）。"""

    def __init__(self, acks: list[bytes] | None = None) -> None:
        self.sent: list[bytes] = []
        self._acks = list(acks or [])

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    def recv(self, timeout: float) -> bytes | None:
        if self._acks:
            return self._acks.pop(0)
        return None  # 超时


def test_retry_timeout() -> None:
    """无 ACK → 重传 retries+1 次仍失败，返回 False。"""
    t = _MockTransport(acks=[])
    tx = Transmitter(t, retries=3, timeout=0.01)
    assert tx.send_with_retry(MsgType.HEARTBEAT, b"", seq=1) is False
    assert tx.tx_attempts == 4  # 1 首传 + 3 重传


def test_send_success_with_ack() -> None:
    """收到对应 seq 的 ACK → 一次成功，无重传。"""
    ack = encode(MsgType.ACK, seq=7)
    t = _MockTransport(acks=[ack])
    tx = Transmitter(t, retries=2, timeout=1.0)
    assert tx.send_with_retry(MsgType.HEARTBEAT, b"", seq=7) is True
    assert tx.tx_attempts == 1
    # 发出的帧能被 decode 且 seq 匹配
    sent = decode(t.sent[0])
    assert sent is not None and sent[1] == 7


def test_wrong_ack_does_not_stop_retry() -> None:
    """收到其它 seq 的 ACK → 不算成功，继续重传。"""
    wrong_ack = encode(MsgType.ACK, seq=99)
    t = _MockTransport(acks=[wrong_ack])  # 只有一个错 ACK，后续超时
    tx = Transmitter(t, retries=2, timeout=0.01)
    assert tx.send_with_retry(MsgType.HEARTBEAT, b"", seq=7) is False
    assert tx.tx_attempts == 3


def test_dedup_lru() -> None:
    """LRU 去重：重复 seq 命中，满容量淘汰最旧。"""
    dd = Deduplicator(capacity=2)
    assert dd.is_duplicate(1) is False
    assert dd.is_duplicate(1) is True  # 重复命中
    assert dd.is_duplicate(2) is False
    assert dd.is_duplicate(3) is False  # 淘汰 1
    assert dd.is_duplicate(1) is False  # 1 已被淘汰
    assert len(dd) == 2


# ---------- 枚举边界 / 字段对齐 ----------

def test_msg_type_enum_boundary() -> None:
    """消息类型枚举边界：REPORT=1 HEARTBEAT=4，非法 type 解码返回 None。"""
    assert int(MsgType.REPORT) == 0x01
    assert int(MsgType.HEARTBEAT) == 0x04
    assert MsgType.valid(0x05) is False
    # CRC 正确但 type 非法 → decode 返回 None
    body = bytes([0x05]) + (1).to_bytes(2, "little") + b""
    crc = crc16_modbus(body)
    frame = MAGIC + body + crc.to_bytes(2, "little")
    assert decode(frame) is None


def test_payload_field_alignment() -> None:
    """REPORT payload 字段对齐 sentinel_bridge schema（温度/湿度/电池/RSSI/信道/协议/ID）。"""
    payload = build_report_payload(
        temperature_c=25.0, humidity_pct=50, battery=Battery.OK,
        rssi_dbm=-85.0, channel="C", protocol="acurite-tower", device_id=4660,
    )
    assert len(payload) == 9
    fields = parse_report_payload(payload)
    assert fields["temperature_c"] == 25.0
    assert fields["humidity_pct"] == 50
    assert fields["battery"] == Battery.OK
    assert fields["rssi_dbm"] == -85.0
    assert fields["channel"] == "C"
    assert fields["protocol"] == Protocol.ACURITE_TOWER
    assert fields["device_id"] == 4660


def test_payload_negative_temperature_and_low_battery() -> None:
    """负温度（int16 有符号）与 LOW 电池状态。"""
    payload = build_report_payload(
        temperature_c=-12.5, humidity_pct=88, battery=Battery.LOW,
        rssi_dbm=-110.0, channel="A", protocol="acurite-515", device_id=1,
    )
    fields = parse_report_payload(payload)
    assert fields["temperature_c"] == -12.5
    assert fields["battery"] == Battery.LOW
    assert fields["rssi_dbm"] == -110.0
    assert fields["protocol"] == Protocol.ACURITE_515


def test_parse_short_payload_returns_empty() -> None:
    """payload 长度不足 9B → parse 返回空 dict（降级）。"""
    assert parse_report_payload(b"\x00\x01") == {}
