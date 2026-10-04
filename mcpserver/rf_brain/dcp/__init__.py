"""dcp 极简二进制帧协议（rf_brain Phase5，LoRa 窄带通讯）。

参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。

- types.py    : 消息类型（REPORT/COMMAND/ACK/HEARTBEAT）与字段枚举
- frame.py    : 编解码 + CRC-16 MODBUS（magic 2B + type 1B + seq 2B + payload + crc 2B）
- transmit.py : 超时重传 + LRU 去重（传输层可 mock）

帧长硬约束：总长 = 7 + payload，payload ≤ 42B，最大帧长 49B < 50B。
"""
from __future__ import annotations

from .frame import (
    FRAME_OVERHEAD,
    HEADER_LEN,
    MAGIC,
    build_report_payload,
    crc16_modbus,
    decode,
    encode,
    parse_report_payload,
)
from .transmit import Deduplicator, Transmitter, Transport
from .types import Battery, MsgType, Protocol

__all__ = [
    "MAGIC", "FRAME_OVERHEAD", "HEADER_LEN",
    "crc16_modbus", "encode", "decode",
    "build_report_payload", "parse_report_payload",
    "Deduplicator", "Transmitter", "Transport",
    "Battery", "MsgType", "Protocol",
]
