"""dcp 帧协议 · 编解码核心（纯 Python 标准库，与 C 侧 dcp_frame.cpp 逐字节兼容）。

参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。

帧格式（工单强制）：
    magic(2B) + type(1B) + seq(2B LE) + payload(N) + crc(2B LE)
    总长 = 7 + N

完整性：
  - magic = b"\\xd0\\xcc"（与 mesh_layer 的 b"MR" 无交集）
  - CRC-16 MODBUS（poly 0x8005 / init 0xFFFF / refin/refout true），
    覆盖 type + seq + payload（不含 magic，同步字不进 CRC）
  - decode 校验 magic + crc，任一失败返回 None，不抛异常
"""
from __future__ import annotations

from .types import (
    PAYLOAD_LEN,
    REPORT_PAYLOAD_LEN,
    Battery,
    MsgType,
    Protocol,
)

MAGIC = b"\xd0\xcc"
MAGIC_LEN = 2
TYPE_LEN = 1
SEQ_LEN = 2
CRC_LEN = 2
HEADER_LEN = MAGIC_LEN + TYPE_LEN + SEQ_LEN  # 5
FRAME_OVERHEAD = HEADER_LEN + CRC_LEN        # 7

_MAX_PAYLOAD = 42  # 帧长 <50 的硬上限：7 + 42 = 49


# ---- CRC-16 MODBUS（查表法，纯标准库）----
_CRC16_TABLE: list[int] = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xA001 if _c & 1 else _c >> 1
    _CRC16_TABLE.append(_c)


def crc16_modbus(data: bytes) -> int:
    """CRC-16 MODBUS，标准向量 crc16_modbus(b"123456789") == 0x4B37。"""
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ b) & 0xFF]
    return crc


# ---- 编解码 ----
def encode(msg_type: int | MsgType, seq: int, payload: bytes = b"") -> bytes:
    """编码一帧：magic + type + seq(LE) + payload + crc(LE)。"""
    t = int(msg_type)
    if len(payload) > _MAX_PAYLOAD:
        raise ValueError(f"payload 超长: {len(payload)} > {_MAX_PAYLOAD}")
    body = bytes([t]) + (int(seq) & 0xFFFF).to_bytes(2, "little") + payload
    crc = crc16_modbus(body)
    return MAGIC + body + crc.to_bytes(2, "little")


def decode(frame: bytes) -> tuple[int, int, bytes] | None:
    """解码一帧 → (type, seq, payload)；magic/crc 校验失败返回 None（不抛错）。

    payload 长度由帧总长反推（总长 = 7 + N）；定长类型（REPORT/ACK/HEARTBEAT）
    额外校验 payload 长度与类型表一致。
    """
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < FRAME_OVERHEAD:
        return None
    if bytes(frame[:MAGIC_LEN]) != MAGIC:
        return None
    msg_type = frame[MAGIC_LEN]
    seq = int.from_bytes(frame[MAGIC_LEN + TYPE_LEN:HEADER_LEN], "little")
    payload = bytes(frame[HEADER_LEN:-CRC_LEN])
    crc = int.from_bytes(frame[-CRC_LEN:], "little")

    # CRC 覆盖 type + seq + payload（frame[2:-2]）
    if crc16_modbus(bytes(frame[MAGIC_LEN:-CRC_LEN])) != crc:
        return None
    if not MsgType.valid(msg_type):
        return None
    expected = PAYLOAD_LEN.get(MsgType(msg_type))
    if expected is not None and len(payload) != expected:
        return None
    return (msg_type, seq, payload)


# ---- REPORT 载荷字段编解码（定长 9B，对齐 sentinel_bridge NDJSON）----
def build_report_payload(
    temperature_c: float,
    humidity_pct: int,
    battery: int | Battery,
    rssi_dbm: float,
    channel: str,
    protocol: int | Protocol | str,
    device_id: int,
) -> bytes:
    """构造 REPORT 的 9B 定长 payload。

    布局：temp(int16 LE ×10) + humidity(uint8) + battery(uint8) +
          rssi(int8) + channel(uint8 ASCII) + protocol(uint8) + id(uint16 LE)
    """
    temp = round(temperature_c * 10)
    if not (-32768 <= temp <= 32767):
        raise ValueError(f"temperature_c 超出 int16 范围: {temperature_c}")
    if not (-128 <= round(rssi_dbm) <= 127):
        raise ValueError(f"rssi_dbm 超出 int8 范围: {rssi_dbm}")
    if not (0 <= int(humidity_pct) <= 255):
        raise ValueError(f"humidity_pct 超出 uint8 范围: {humidity_pct}")
    if isinstance(protocol, str):
        protocol = Protocol.from_name(protocol)
    ch = ord(channel[0]) if channel else 0
    if not (0 <= ch <= 255):
        raise ValueError(f"channel 非单字节可编码: {channel!r}")

    return (
        temp.to_bytes(2, "little", signed=True)
        + bytes([int(humidity_pct) & 0xFF, int(battery) & 0xFF, round(rssi_dbm) & 0xFF])
        + bytes([ch, int(protocol) & 0xFF])
        + (int(device_id) & 0xFFFF).to_bytes(2, "little")
    )


def parse_report_payload(payload: bytes) -> dict:
    """解析 REPORT 的 9B payload → 字段 dict；长度不足返回空 dict（降级）。"""
    if len(payload) != REPORT_PAYLOAD_LEN:
        return {}
    temp = int.from_bytes(payload[0:2], "little", signed=True) / 10.0
    humidity = payload[2]
    battery = Battery(payload[3]) if payload[3] in (0, 1) else payload[3]
    rssi = int.from_bytes(payload[4:5], "little", signed=True)
    channel = chr(payload[5]) if 32 <= payload[5] <= 126 else ""
    protocol = Protocol(payload[6]) if payload[6] in Protocol._value2member_map_ else Protocol.UNKNOWN
    device_id = int.from_bytes(payload[7:9], "little")
    return {
        "temperature_c": temp,
        "humidity_pct": humidity,
        "battery": battery,
        "rssi_dbm": float(rssi),
        "channel": channel,
        "protocol": protocol,
        "device_id": device_id,
    }


__all__ = [
    "MAGIC", "HEADER_LEN", "FRAME_OVERHEAD",
    "crc16_modbus", "encode", "decode",
    "build_report_payload", "parse_report_payload",
]
