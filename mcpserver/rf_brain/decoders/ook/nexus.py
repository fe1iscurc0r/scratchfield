"""Nexus TH 温湿度解码器（OOK-PPM 距离编码 · 36 bit）。

参考 rtl_433 `src/devices/nexus.c` 文件头协议注释（GPL-2.0-or-later），
仅引用「协议格式」这一公开事实，独立实现，未复制任何 C 解码代码。

帧（36 bit = 9 nibble，MSB 先）：

    [id0][id1][flags][temp0][temp1][temp2][const][humi0][humi1]
      4    4     4      4      4      4      4      4      4

    id   = (id0<<4)|id1                    8bit
    flags= battery(bit3) + test(bit2) + channel(bit1:0 → +1 = CH1..CH3)
    temp = 12bit 有符号二进制补码（temp0..2 三个 nibble），temp_c = signed12 * 0.1
    const= 固定 0xF（完整性判据）
    humi = (humi0<<4)|humi1                 8bit

PPM 时序：脉冲 ~500µs；bit 0 = 脉冲+~1000µs 间隔，bit 1 = 脉冲+~2000µs 间隔；
同步间隔 ~4000µs；每包重复 12 帧。无常规校验和——以 const nibble==0xF 判完整性。
"""
from __future__ import annotations

from . import pulse_demod as pd

PULSE_US = 500.0
SHORT_GAP_US = 1000.0    # bit 0
LONG_GAP_US = 2000.0     # bit 1
SYNC_GAP_US = 4000.0     # 帧间同步间隔


def nexus_pulses_to_bits(pulses: list[pd.Pulse]) -> list[int]:
    """脉冲序列 → bit 流（PPM 距离编码切分）。"""
    return pd.ppm_to_bits(pulses, PULSE_US, SHORT_GAP_US, LONG_GAP_US,
                          sync_gap_us=SYNC_GAP_US)


def _signed12(v: int) -> int:
    """12bit 二进制补码 → 有符号整数。"""
    v &= 0xFFF
    return v - 0x1000 if v & 0x800 else v


def decode_nexus(bits: list[int]) -> dict:
    """36bit bit 流 → 统一 dict。bit 数不足抛 ValueError；const nibble 不符只置 crc_ok=False。"""
    if len(bits) < 36:
        raise ValueError(f"Nexus 需要 36 bit，实际 {len(bits)}")
    nib: list[int] = []
    for i in range(0, 36, 4):
        n = 0
        for b in bits[i:i + 4]:
            n = (n << 1) | b
        nib.append(n)

    device_id = (nib[0] << 4) | nib[1]
    flags = nib[2]
    battery = bool(flags & 0x8)
    test_mode = bool(flags & 0x4)
    channel = (flags & 0x3) + 1
    temp12 = (nib[3] << 8) | (nib[4] << 4) | nib[5]
    temperature = round(_signed12(temp12) * 0.1, 1)
    const = nib[6]
    humidity = (nib[7] << 4) | nib[8]

    return {
        "protocol": "nexus",
        "id": device_id,
        "channel": channel,
        "temperature": temperature,
        "humidity": humidity,
        "battery": "OK" if battery else "LOW",
        "raw_bits": pd.bits_to_str(bits[:36]),
        "crc_ok": const == 0xF,
        "test_mode": test_mode,
    }


def decode_nexus_pulses(pulses: list[pd.Pulse]) -> dict:
    """脉冲序列 → 统一 dict。"""
    bits = nexus_pulses_to_bits(pulses)
    if len(bits) < 36:
        raise ValueError(f"Nexus 从脉冲解出 {len(bits)} bit，不足 36")
    return decode_nexus(bits)


def encode_nexus(*, device_id: int, channel: int = 1, battery: bool = True,
                 temperature_c: float = 20.0, humidity: int = 50,
                 test_mode: bool = False) -> list[pd.Pulse]:
    """字段 → OOK-PPM 脉冲序列（测试合成用）。"""
    if not 0 <= device_id < 256:
        raise ValueError(f"device_id 越界: {device_id}（0..255）")
    if not 1 <= channel <= 3:
        raise ValueError(f"channel 越界: {channel}（1..3）")
    temp12 = int(round(temperature_c * 10)) & 0xFFF   # 12bit 补码
    if not 0 <= humidity < 256:
        raise ValueError(f"humidity 越界: {humidity}（0..255）")

    flags = ((1 if battery else 0) << 3) | ((1 if test_mode else 0) << 2) | (channel - 1)
    nibbles = [
        (device_id >> 4) & 0xF, device_id & 0xF,
        flags,
        (temp12 >> 8) & 0xF, (temp12 >> 4) & 0xF, temp12 & 0xF,
        0xF,
        (humidity >> 4) & 0xF, humidity & 0xF,
    ]
    bits: list[int] = []
    for n in nibbles:
        for k in range(3, -1, -1):
            bits.append((n >> k) & 1)

    pulses: list[pd.Pulse] = []
    for bit in bits:
        pulses.append((1, PULSE_US))
        pulses.append((0, SHORT_GAP_US if bit == 0 else LONG_GAP_US))
    return pulses
