"""dcp 帧协议 · 消息类型与字段枚举（int 编码 1B，与 C 侧逐字节兼容）。

参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。
协议常量与 sentinel_bridge._KNOWN_PROTOCOLS 对齐，字段名对齐其 NDJSON schema。
"""
from __future__ import annotations

from enum import IntEnum


class MsgType(IntEnum):
    """消息类型（frame.py 头部 type 字段，1B int 编码）。"""
    REPORT = 0x01      # 上报（传感器数据）
    COMMAND = 0x02     # 命令（下发）
    ACK = 0x03         # 确认
    HEARTBEAT = 0x04   # 心跳

    @classmethod
    def valid(cls, value: int) -> bool:
        return value in cls._value2member_map_


class Protocol(IntEnum):
    """传感器协议枚举（REPORT payload 第 6 字节），对齐 sentinel_bridge。"""
    ACURITE_TOWER = 0          # acurite-tower
    ACURITE_515 = 1            # acurite-515
    LACROSSE_TX141TH_BV2 = 2   # lacrosse-tx141th-bv2
    ACURITE_5N1 = 3            # acurite-5n1（预留）
    ACURITE_ATLAS = 4          # acurite-atlas（预留）
    UNKNOWN = 255              # 保留 / 未知

    @classmethod
    def from_name(cls, name: str) -> "Protocol":
        return _PROTOCOL_BY_NAME.get(name, cls.UNKNOWN)

    @property
    def name_str(self) -> str:
        return _PROTOCOL_NAME.get(self, "unknown")


_PROTOCOL_BY_NAME = {
    "acurite-tower": Protocol.ACURITE_TOWER,
    "acurite-515": Protocol.ACURITE_515,
    "lacrosse-tx141th-bv2": Protocol.LACROSSE_TX141TH_BV2,
    "acurite-5n1": Protocol.ACURITE_5N1,
    "acurite-atlas": Protocol.ACURITE_ATLAS,
}
_PROTOCOL_NAME = {v: k for k, v in _PROTOCOL_BY_NAME.items()}


class Battery(IntEnum):
    """电池状态枚举（REPORT payload 第 3 字节）。"""
    OK = 0
    LOW = 1


# 各消息类型的 payload 定长（字节）；None 表示变长（COMMAND 由上层自声明）。
# 帧总长 = 7 + payload_len（magic 2 + type 1 + seq 2 + crc 2 = 7）。
PAYLOAD_LEN = {
    MsgType.REPORT: 9,
    MsgType.COMMAND: None,
    MsgType.ACK: 0,
    MsgType.HEARTBEAT: 0,
}

# REPORT payload 定长 9B 的字段布局（frame.py build/parse_report_payload 使用）。
REPORT_PAYLOAD_LEN = 9
