"""Acurite 592TXR / Tower 温湿度解码器（OOK-PWM · 56 bit）。

参考 rtl_433 `src/devices/acurite.c` 文件头协议注释（GPL-2.0-or-later），
仅引用「协议格式」这一公开事实，独立实现，未复制任何 C 解码代码。

帧（56 bit = 7 字节，MSB 先，解码前对 bit 流整体取反）：

    Byte0  CCII IIII   channel(2bit: 00=C 10=B 11=A, 01 非法) + id 高 6bit
    Byte1  IIII IIII   id 低 8bit
    Byte2  pBm mmmm    偶校验 + battery(1=OK) + message_type(6bit, Tower=0x04)
    Byte3  pHHH HHHH   偶校验 + humidity(7bit)
    Byte4  pTTT TTTT   偶校验 + temp 高 7bit
    Byte5  pTTT TTTT   偶校验 + temp 低 7bit
    Byte6  KKKK KKKK   前 6 字节加和 mod 256

校验：加和校验 sum(bb[0..5])&0xFF == bb[6]；bb[2..5] 每个字节 bit7 为其
低 7 位的偶校验位。温度 temp_raw=((bb[4]&0x7F)<<7)|(bb[5]&0x7F)，
temp_c=(temp_raw-1000)*0.1（分辨率 0.1°C）。
"""
from __future__ import annotations

from . import pulse_demod as pd

# OOK-PWM 时序（µs）
SHORT_US = 220.0        # 短脉冲 = 原始 bit 0（取反后逻辑 1）
LONG_US = 408.0         # 长脉冲 = 原始 bit 1（取反后逻辑 0）
SYNC_US = 620.0         # 帧头同步脉冲
SYNC_GAP_US = 596.0
GAP_LONG_US = 392.0     # 短脉冲后的长间隔
GAP_SHORT_US = 204.0    # 长脉冲后的短间隔
RESET_US = 2192.0       # 包结束间隔

CHANNEL_TO_CODE = {"A": 0b11, "B": 0b10, "C": 0b00}
CODE_TO_CHANNEL = {0b00: "C", 0b10: "B", 0b11: "A", 0b01: None}  # 0b01 非法


def acurite_pulses_to_bits(pulses: list[pd.Pulse]) -> list[int]:
    """脉冲序列 → 逻辑 bit 流（PWM 切分 + 整体取反）。"""
    raw = pd.pwm_to_bits(pulses, SHORT_US, LONG_US,
                         sync_us=SYNC_US, reset_us=RESET_US)
    return pd.invert_bits(raw)


def decode_acurite(bits: list[int]) -> dict:
    """56bit 逻辑 bit 流 → 统一 dict。

    结构错误（bit 数不足）抛 ValueError；校验不过只置 crc_ok=False，仍返回字段。
    """
    if len(bits) < 56:
        raise ValueError(f"Acurite 需要 56 bit，实际 {len(bits)}")
    b = pd.bits_to_bytes(bits[:56])

    checksum_ok = (sum(b[0:6]) & 0xFF) == b[6]
    parity_ok = all(pd.even_parity_ok(b[i]) for i in range(2, 6))
    crc_ok = checksum_ok and parity_ok

    channel = CODE_TO_CHANNEL.get((b[0] >> 6) & 0b11)
    sensor_id = ((b[0] & 0x3F) << 8) | b[1]
    battery = (b[2] & 0x40) != 0
    humidity = b[3] & 0x7F
    temp_raw = ((b[4] & 0x7F) << 7) | (b[5] & 0x7F)
    temperature = round((temp_raw - 1000) * 0.1, 1)

    return {
        "protocol": "acurite",
        "id": sensor_id,
        "channel": channel,
        "temperature": temperature,
        "humidity": humidity,
        "battery": "OK" if battery else "LOW",
        "raw_bits": pd.bits_to_str(bits[:56]),
        "crc_ok": crc_ok,
    }


def decode_acurite_pulses(pulses: list[pd.Pulse]) -> dict:
    """脉冲序列 → 统一 dict（合成/实采脉冲入口）。"""
    bits = acurite_pulses_to_bits(pulses)
    if len(bits) < 56:
        raise ValueError(f"Acurite 从脉冲解出 {len(bits)} bit，不足 56")
    return decode_acurite(bits)


def encode_acurite(*, sensor_id: int, channel: str = "A", battery: bool = True,
                   temperature_c: float = 20.5, humidity: int = 50) -> list[pd.Pulse]:
    """字段 → OOK-PWM 脉冲序列（测试合成用，真实帧样例的参数化表达）。"""
    if channel not in CHANNEL_TO_CODE:
        raise ValueError(f"非法 channel: {channel!r}（A/B/C）")
    if not 0 <= sensor_id < (1 << 14):
        raise ValueError(f"sensor_id 越界: {sensor_id}（0..16383）")
    temp_raw = int(round(temperature_c * 10)) + 1000
    if not 0 <= temp_raw < (1 << 14):
        raise ValueError(f"temperature_c 越界: {temperature_c}（temp_raw {temp_raw}）")
    if not 0 <= humidity < (1 << 7):
        raise ValueError(f"humidity 越界: {humidity}（0..127）")

    bb = [0] * 7
    bb[0] = (CHANNEL_TO_CODE[channel] << 6) | ((sensor_id >> 8) & 0x3F)
    bb[1] = sensor_id & 0xFF
    bb[2] = ((1 if battery else 0) << 6) | 0x04      # message_type = 0x04 (Tower)
    bb[3] = humidity & 0x7F
    bb[4] = (temp_raw >> 7) & 0x7F
    bb[5] = temp_raw & 0x7F
    for i in range(2, 6):                            # 偶校验位（覆盖低 7 位）
        bb[i] |= (pd.even_parity_bit(bb[i]) << 7)
    bb[6] = sum(bb[0:6]) & 0xFF

    logical: list[int] = []
    for byte in bb:
        for k in range(7, -1, -1):
            logical.append((byte >> k) & 1)

    raw = pd.invert_bits(logical)                    # 发射前整体取反
    pulses: list[pd.Pulse] = [(1, SYNC_US), (0, SYNC_GAP_US)]
    for bit in raw:
        if bit == 0:
            pulses += [(1, SHORT_US), (0, GAP_LONG_US)]
        else:
            pulses += [(1, LONG_US), (0, GAP_SHORT_US)]
    return pulses
