# -*- coding: utf-8 -*-
"""
rtl_433 哨兵协议解码器 — W66-04

独立实现（不复制 rtl_433 GPL 代码），只引用协议格式事实：
- Acurite 592TXR/Tower：56-bit OOK-PWM，温湿度站
- Nexus TH（TFA 30.3209 等）：36-bit OOK-PPM，简单温湿度
- Kerui/EV1527：24-bit OOK-PWM，门磁/PIR 安防

SX1278 OOK 模式寄存器配置建议以常量表导出。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

# =============================================================================
# SX1278 OOK 模式寄存器配置建议（来源：Semtech SX1276/77/78 Datasheet
# + RadioLib SX127x.h 公开常量）
# =============================================================================

class SX1278Register(NamedTuple):
    addr: int
    name: str
    value: int
    hex: str
    description: str


# 与 RadioLib SX127x.h 常量一致（MIT License）
REG_OPMODE         = 0x01  # 模式控制：LongRangeMode=0, ModulationType=OOK
REG_RX_BW          = 0x12  # 接收带宽
REG_LNA            = 0x0C  # LNA 控制
REG_OOK_PEAK       = 0x14  # OOK 峰值门限
REG_OOK_FIX        = 0x15  # OOK 固定门限
REG_RSSI_CONFIG    = 0x0E  # RSSI 配置
REG_RSSI_THRESH    = 0x10  # RSSI 门限
REG_RSSI_VALUE_FSK = 0x11  # RSSI 只读值

# Acurite/Kerui（~4.8 kbps）→ RxBw = 32MHz/(20·2^(4+2)) = 25 kHz
# Mant=0b10(20), Exp=0b100(4) → BW=25 kHz
SX1278_ACURITE_CONFIG: list[SX1278Register] = [
    SX1278Register(REG_OPMODE,    "RegOpMode",    0x00,
                    "0x00",
                    "进入 FSK/OOK 模式（LongRangeMode=0, ModulationType[6:5]=b01 OOK）"),
    SX1278Register(REG_LNA,        "RegLna",       0xC0,
                    "0xC0",
                    "LnaBoost=11(150%电流) + LnaGain=001(G1最大增益)，提高OOK灵敏度"),
    SX1278Register(REG_RX_BW,      "RegRxBw",      0x8B,
                    "0x8B",
                    "Mant=10(20), Exp=100(4) → BW=25 kHz，适合 Acurite/Kerui ~4.8kbps"),
    SX1278Register(REG_OOK_PEAK,    "RegOokPeak",   0x00,
                    "0x00",
                    "ThreshType[4:3]=00(fixed 固定门限)，PeakStep=000，避免峰值漂移"),
    SX1278Register(REG_OOK_FIX,    "RegOokFix",    0x08,
                    "0x08",
                    "固定门限值 0x08（按底噪标定，建议范围 0x06~0x0A）"),
    SX1278Register(REG_RSSI_CONFIG, "RegRssiConfig", 0x00,
                    "0x00",
                    "RssiSmoothing=000(2 样本最快响应)，脉冲边沿时延最小"),
    SX1278Register(REG_RSSI_THRESH, "RegRssiThresh", 0x80,
                    "0x80",
                    "RssiThreshold = 0x80/2 = -64 dBm（可根据底噪调整）"),
]

# Nexus TH（PPM 距离编码，~2 kbps）→ 收窄到 12.5 kHz 提升灵敏度
# Mant=10(20), Exp=101(5) → BW=12.5 kHz
SX1278_NEXUS_CONFIG: list[SX1278Register] = [
    SX1278Register(REG_OPMODE,    "RegOpMode",    0x00,
                    "0x00",
                    "进入 FSK/OOK 模式（LongRangeMode=0, ModulationType[6:5]=b01 OOK）"),
    SX1278Register(REG_LNA,        "RegLna",       0xC0,
                    "0xC0",
                    "LnaBoost=11(150%电流) + LnaGain=001(G1最大增益)"),
    SX1278Register(REG_RX_BW,      "RegRxBw",      0x97,
                    "0x97",
                    "Mant=10(20), Exp=101(5) → BW=12.5 kHz，适合 Nexus ~2kbps"),
    SX1278Register(REG_OOK_PEAK,    "RegOokPeak",   0x00,
                    "0x00",
                    "ThreshType=00(fixed)，固定门限判 OOK 电平"),
    SX1278Register(REG_OOK_FIX,    "RegOokFix",    0x06,
                    "0x06",
                    "固定门限值 0x06（2kbps 脉冲更窄，门限稍低）"),
    SX1278Register(REG_RSSI_CONFIG, "RegRssiConfig", 0x00,
                    "0x00",
                    "RssiSmoothing=000(2 样本最快响应)"),
    SX1278Register(REG_RSSI_THRESH, "RegRssiThresh", 0x80,
                    "0x80",
                    "RssiThreshold = -64 dBm"),
]


def sx1278_register_table(protocol: str = "acurite") -> list[SX1278Register]:
    """返回指定协议的 SX1278 OOK 寄存器配置表。"""
    if protocol.lower() in ("nexus", "th", "ppm"):
        return SX1278_NEXUS_CONFIG
    return SX1278_ACURITE_CONFIG


def sx1278_register_doc() -> str:
    """导出 SX1278 OOK 配置文档（用于 Arduino 固件参考）。"""
    lines = [
        "=== SX1278 OOK 模式寄存器配置参考 ===",
        "来源：Semtech SX1276/77/78 Datasheet + RadioLib SX127x.h（MIT）",
        "",
        "--- Acurite 592TXR / Kerui（~4.8 kbps，RxBw=25kHz）---",
    ]
    for r in SX1278_ACURITE_CONFIG:
        lines.append(f"  {r.name:<20} [{r.hex}]  {r.description}")
    lines += [
        "",
        "--- Nexus TH（~2 kbps，RxBw=12.5kHz）---",
    ]
    for r in SX1278_NEXUS_CONFIG:
        lines.append(f"  {r.name:<20} [{r.hex}]  {r.description}")
    return "\n".join(lines)


# =============================================================================
# 位流解析工具
# =============================================================================

class BitStream:
    """MSB-first 位流操作助手。"""

    def __init__(self, bits: list[int] | bytes | int | None = None):
        if bits is None:
            self._bits: list[int] = []
        elif isinstance(bits, int):
            self._bits = [(bits >> (7 - i)) & 1 for i in range(8)]
        elif isinstance(bits, (list, tuple)):
            self._bits = list(bits)
        elif isinstance(bits, bytes):
            self._bits = []
            for b in bits:
                self._bits.extend([(b >> (7 - i)) & 1 for i in range(8)])
        else:
            self._bits = []

    def __len__(self) -> int:
        return len(self._bits)

    def __getitem__(self, i: int) -> int:
        return self._bits[i]

    def to_bytes(self) -> bytes:
        result = bytearray()
        for i in range(0, len(self._bits), 8):
            byte = 0
            for j in range(8):
                if i + j < len(self._bits):
                    byte = (byte << 1) | (self._bits[i + j] & 1)
                else:
                    byte <<= 1
            result.append(byte)
        return bytes(result)

    @classmethod
    def from_bytes(cls, data: bytes) -> "BitStream":
        bs = cls()
        for b in data:
            bs._bits.extend([(b >> (7 - i)) & 1 for i in range(8)])
        return bs

    def invert(self) -> "BitStream":
        """整体取反（Acurite 协议需要）。"""
        bs = BitStream()
        bs._bits = [1 - b for b in self._bits]
        return bs

    def hex_str(self) -> str:
        return self.to_bytes().hex().upper()


# =============================================================================
# 设备类型枚举
# =============================================================================

class DeviceType(Enum):
    ACURITE_592TXR = "acurite_592txr"
    NEXUS_TH = "nexus_th"
    KERUI_EV1527 = "kerui_ev1527"
    UNKNOWN = "unknown"


@dataclass
class DeviceEvent:
    device_type: DeviceType
    id: int
    raw_bytes: bytes
    # 通用字段（存在则为有效值，不存在为 None）
    temperature_c: float | None = None  # 摄氏度
    humidity: int | None = None          # 相对湿度 %
    battery_ok: bool | None = None
    channel: int | None = None
    flags: int | None = None
    cmd: int | None = None               # Kerui 命令码
    checksum_ok: bool | None = None
    protocol_name: str | None = None

    def summary(self) -> str:
        parts = [f"type={self.device_type.value}"]
        if self.temperature_c is not None:
            parts.append(f"temp={self.temperature_c:.1f}°C")
        if self.humidity is not None:
            parts.append(f"humi={self.humidity}%")
        if self.battery_ok is not None:
            parts.append(f"batt={'OK' if self.battery_ok else 'LOW'}")
        if self.channel is not None:
            parts.append(f"ch={self.channel}")
        if self.cmd is not None:
            parts.append(f"cmd=0x{self.cmd:X}")
        if self.id is not None:
            parts.append(f"id=0x{id(self):X}")
        return " | ".join(parts)


# =============================================================================
# 校验工具
# =============================================================================

def _checksum_8(data: bytes) -> int:
    return sum(data) & 0xFF


def _parity_byte(b: int) -> bool:
    """整字节偶校验：1 的个数为偶数返回 True。"""
    return bin(b).count("1") % 2 == 0


# =============================================================================
# Acurite 592TXR 解码器
# 帧长：56 bit (7 字节)，OOK-PWM 短220µs/长408µs
# 字段：channel(2) + id(14) + battery(1) + type(6) + humidity(7) + temp(14) + checksum(8)
# 来源：rtl_433 devices/acurite.c 文件头协议注释（GPL-2.0，仅引用格式事实）
# =============================================================================

def decode_acurite_592txr(raw_bits: BitStream) -> DeviceEvent | None:
    """解码 Acurite 592TXR 56-bit 帧。

    参数为 OOK-PWM 位流（已还原为 56 bit 原始字节）。
    协议要求解码前整体取反。

    返回 DeviceEvent（temperature_c / humidity / battery_ok）或 None（校验失败）。
    """
    if len(raw_bits) < 56:
        return None

    # 取反（协议规定）
    bits = raw_bits.invert()
    data = bits.to_bytes()[:7]

    # 校验 checksum
    cs = _checksum_8(data[:6])
    if cs != data[6]:
        return None

    # 校验偶校验位（bb[2]~bb[5] 每个字节 bit7 为低 7 位偶校验）
    for i in range(2, 6):
        if not _parity_byte(data[i]):
            return None

    # ---- 字段解析 ----
    bb = data

    # channel: bb[0] bit7:6 → 00=C, 10=B, 11=A
    ch_bits = (bb[0] >> 6) & 0x03
    channel_map = {0b00: 3, 0b10: 2, 0b11: 1}  # A=1, B=2, C=3
    channel = channel_map.get(ch_bits, 0)

    # id: bb[0] bit5:0 + bb[1] → 14 bit
    sensor_id = ((bb[0] & 0x3F) << 8) | bb[1]

    # battery: bb[2] bit6 → 1=OK, 0=LOW
    battery_ok = bool((bb[2] >> 6) & 1)

    # message_type: bb[2] bit5:0 → Tower 固定 0x04
    message_type = bb[2] & 0x3F

    # humidity: bb[3] bit6:0 → 1-99 %
    humidity = bb[3] & 0x7F
    if humidity > 100:
        return None

    # temperature: bb[4] bit6:0 + bb[5] bit6:0 → 14 bit(raw) → 11 bit(有效)
    temp_raw = ((bb[4] & 0x7F) << 7) | (bb[5] & 0x7F)
    temperature_c = (temp_raw - 1000) * 0.1

    event = DeviceEvent(
        device_type=DeviceType.ACURITE_592TXR,
        id=sensor_id,
        raw_bytes=data,
        temperature_c=round(temperature_c, 1),
        humidity=humidity,
        battery_ok=battery_ok,
        channel=channel,
        checksum_ok=True,
        protocol_name="Acurite 592TXR/Tower (56-bit OOK-PWM)",
    )
    return event


# =============================================================================
# Nexus TH 解码器
# 帧长：36 bit (9 nibble)，OOK-PPM 脉冲500µs/bit0:1000µs/bit1:2000µs
# 字段：id(8) + flags(4) + temp(12) + const(4=0xF) + humidity(8)
# 来源：rtl_433 devices/nexus.c 文件头协议注释（GPL-2.0，仅引用格式事实）
# =============================================================================

def _parse_nibble_bits(bits: BitStream, start: int, count: int = 4) -> int:
    """从 MSB-first 位流提取 count 个 bit（从 start 开始），返回整数值。"""
    val = 0
    for i in range(count):
        val = (val << 1) | (bits[start + i] & 1)
    return val


def decode_nexus_th(raw_bits: BitStream) -> DeviceEvent | None:
    """解码 Nexus TH 36-bit 帧（PPM 距离编码）。

    参数为已还原的 36 bit 原始位流（MSB-first）。

    返回 DeviceEvent（temperature_c / humidity / battery_ok）或 None（const nibble 不合法）。
    """
    if len(raw_bits) < 36:
        return None

    # ---- nibble 解析（MSB-first，4 bit/nibble）----
    # nibble 0: id high nibble
    # nibble 1: id low nibble
    # nibble 2: flags [battery:test3:test2:channel1:channel0]
    # nibble 3-5: temperature 12-bit 有符号（MSB 先）
    # nibble 6: const（固定 0xF）
    # nibble 7-8: humidity 8-bit

    const_nibble = _parse_nibble_bits(raw_bits, 6 * 4, 4)
    if const_nibble != 0xF:
        return None  # 协议校验：固定 nibble 必须为 0xF

    id_high = _parse_nibble_bits(raw_bits, 0, 4)
    id_low  = _parse_nibble_bits(raw_bits, 4, 4)
    sensor_id = (id_high << 4) | id_low

    flags_nibble = _parse_nibble_bits(raw_bits, 8, 4)
    battery_ok = bool((flags_nibble >> 3) & 1)   # bit3: 1=OK, 0=LOW
    # test_bit = (flags_nibble >> 2) & 1          # bit2: 0=正常
    channel = (flags_nibble & 0x03) + 1          # bit1:0 → 0=CH1,1=CH2,2=CH3

    # Temperature: 12-bit 有符号，MSB-first 二进制补码
    temp_bits = (_parse_nibble_bits(raw_bits, 12, 4) << 8 |
                 _parse_nibble_bits(raw_bits, 16, 4) << 4 |
                 _parse_nibble_bits(raw_bits, 20, 4))
    # 有符号扩展
    if temp_bits & 0x800:
        temp_bits -= 0x1000
    temperature_c = round(temp_bits * 0.1, 1)

    humi_high = _parse_nibble_bits(raw_bits, 28, 4)
    humi_low  = _parse_nibble_bits(raw_bits, 32, 4)
    humidity = (humi_high << 4) | humi_low

    event = DeviceEvent(
        device_type=DeviceType.NEXUS_TH,
        id=sensor_id,
        raw_bytes=raw_bits.to_bytes()[:5],
        temperature_c=temperature_c,
        humidity=humidity,
        battery_ok=battery_ok,
        channel=channel,
        checksum_ok=True,  # 无校验；以 const=0xF 替代
        protocol_name="Nexus TH (36-bit OOK-PPM)",
    )
    return event


# =============================================================================
# Kerui/EV1527 解码器
# 帧长：24 bit，OOK-PWM 短304-560µs/长860-1016µs
# 字段：id(20) + cmd(4)
# 来源：rtl_433 devices/kerui.c 文件头协议注释（GPL-2.0，仅引用格式事实）
# =============================================================================

def decode_kerui_ev1527(raw_bits: BitStream) -> DeviceEvent | None:
    """解码 Kerui/EV1527 24-bit 帧。

    参数为已还原的 24 bit 原始位流（MSB-first）。

    返回 DeviceEvent（cmd / id）或 None（全零/全一非法）。
    """
    if len(raw_bits) < 24:
        return None

    # 提取 24 bit
    val = 0
    for i in range(24):
        val = (val << 1) | (raw_bits[i] & 1)

    # 协议校验：全零或全一非法（EV1527 芯片最小跳变要求）
    if val == 0x000000 or val == 0xFFFFFF:
        return None

    # id: 高 20 bit（EV1527 为 20-bit 编码 id）
    sensor_id = (val >> 4) & 0xFFFFF

    # cmd: 低 4 bit
    cmd = val & 0x0F

    # 门磁/PIR 常见命令：0x01=开门，0x02=关门，0x04=报警，0x08=电池低
    # 详情由业务层解释

    event = DeviceEvent(
        device_type=DeviceType.KERUI_EV1527,
        id=sensor_id,
        raw_bytes=raw_bits.to_bytes()[:3],
        cmd=cmd,
        checksum_ok=True,  # 无校验；以 25 帧重复一致性替代
        protocol_name="Kerui/EV1527 (24-bit OOK-PWM)",
    )
    return event


# =============================================================================
# 合成位流生成（测试用）
# =============================================================================

def _make_bits(value: int, width: int) -> list[int]:
    """整数 → MSB-first bit list。"""
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def synthesize_acurite_bitstream(
    sensor_id: int,
    temperature_c: float,
    humidity: int,
    channel: int = 1,
    battery_ok: bool = True,
) -> BitStream:
    """为 Acurite 592TXR 合成 56-bit OOK 位流（测试用）。"""
    # channel 映射逆推
    ch_map_inv = {3: 0b00, 2: 0b10, 1: 0b11}
    ch_bits = ch_map_inv.get(channel, 0b11)

    # temperature → raw
    temp_raw = int(round(temperature_c * 10 + 1000)) & 0x3FFF

    # humidity 限幅
    humidity = max(1, min(99, humidity))

    # 构造 6 字节数据
    bb0 = (ch_bits << 6) | ((sensor_id >> 8) & 0x3F)
    bb1 = sensor_id & 0xFF
    # battery 在 bit6（1=OK），message_type=0x04 在 bit5:0
    bb2 = ((1 if battery_ok else 0) << 6) | 0x04
    bb3 = humidity & 0x7F
    bb4 = (temp_raw >> 7) & 0x7F
    bb5 = temp_raw & 0x7F

    # 先加偶校验位（bit7：使整个字节 1 的个数为偶数）
    raw = bytearray([bb0, bb1, bb2, bb3, bb4, bb5, 0])
    for idx in range(2, 6):
        if bin(raw[idx]).count("1") % 2 != 0:  # 当前奇数个1 → 置 bit7 补偶
            raw[idx] |= 0x80
    # 再算 checksum（对含偶校验位的实际字节求和）
    raw[6] = sum(raw[:6]) & 0xFF

    data = bytes(raw)
    bs = BitStream.from_bytes(data)
    return bs.invert()  # 协议要求取反


def synthesize_nexus_bitstream(
    sensor_id: int,
    temperature_c: float,
    humidity: int,
    channel: int = 1,
    battery_ok: bool = True,
) -> BitStream:
    """为 Nexus TH 合成 36-bit PPM 位流（测试用）。"""
    # temperature: 有符号 12-bit × 0.1
    temp_val = int(round(temperature_c * 10))
    if temp_val < 0:
        temp_val = (1 << 12) + temp_val  # 二进制补码

    ch = max(1, min(3, channel)) - 1  # 0=CH1,1=CH2,2=CH3
    flags = ((1 if battery_ok else 0) << 3) | (ch & 0x03)  # bit3=battery, bit1:0=channel

    bits: list[int] = []
    # nibble 0-1: id
    bits += _make_bits((sensor_id >> 4) & 0xFF, 8)
    # nibble 2: flags
    bits += _make_bits(flags, 4)
    # nibble 3-5: temperature 12-bit
    bits += _make_bits(temp_val, 12)
    # nibble 6: const = 0xF
    bits += [1, 1, 1, 1]
    # nibble 7-8: humidity
    bits += _make_bits(humidity & 0xFF, 8)

    return BitStream(bits)


def synthesize_kerui_bitstream(sensor_id: int, cmd: int) -> BitStream:
    """为 Kerui/EV1527 合成 24-bit PWM 位流（测试用）。"""
    # EV1527: 20-bit id + 4-bit cmd
    val = ((sensor_id & 0xFFFFF) << 4) | (cmd & 0x0F)
    return BitStream(_make_bits(val, 24))


# =============================================================================
# 主解码入口
# =============================================================================

def decode_rtl433_frame(bits: BitStream) -> DeviceEvent | None:
    """自动检测协议并解码。

    尝试顺序：Acurite 592TXR → Nexus TH → Kerui/EV1527。
    返回第一个校验通过的 DeviceEvent，或 None（均不匹配）。
    """
    # Acurite：要求 56 bit，校验 checksum + 偶校验
    if len(bits) >= 56:
        ev = decode_acurite_592txr(bits)
        if ev is not None:
            return ev

    # Nexus：要求 36 bit，校验 const nibble = 0xF
    if len(bits) >= 36:
        ev = decode_nexus_th(bits)
        if ev is not None:
            return ev

    # Kerui：要求 24 bit
    if len(bits) >= 24:
        ev = decode_kerui_ev1527(bits)
        if ev is not None:
            return ev

    return None
