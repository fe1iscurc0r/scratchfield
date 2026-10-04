"""Kerui / EV1527（x1527 家族）门磁·PIR·遥控解码器（OOK-PWM · 24 bit）。

参考 rtl_433 `src/devices/kerui.c` 文件头协议注释（GPL-2.0-or-later），
仅引用「协议格式」这一公开事实，独立实现，未复制任何 C 解码代码。

帧（24 bit = 20bit 地址/ID + 4bit 命令，MSB 先）：

    [ 20bit 地址 / ID ] [ 4bit 命令 ]

EV1527/PT2262 家族通用遥控编码：每颗芯片固定 20bit 地址，命令码标识
开门/关门/报警/电池低等。前置一个「宽间隔同步位」（作为第 25 个数据位忽略），
每包重复 25 帧。无校验——以「25 次重复帧一致 + 非全零」做判据。

PWM 时序：短脉冲 ~340µs = bit 0，长脉冲 ~900µs = bit 1；同步位 = 短脉冲 +
极长间隔（~10ms）。
"""
from __future__ import annotations

from . import pulse_demod as pd

SHORT_US = 340.0
LONG_US = 900.0        # 860~1016 取中
SYNC_GAP_US = 10000.0  # 前置同步位的极长间隔


def kerui_pulses_to_bits(pulses: list[pd.Pulse]) -> list[int]:
    """脉冲序列 → bit 流（跳过前置同步位，PWM 切分 24bit）。"""
    bits: list[int] = []
    n = len(pulses)
    i = 0
    while i < n:
        lvl, w = pulses[i]
        if lvl != 1:
            i += 1
            continue
        # 前置同步位：高脉冲 + 极长间隔 → 跳过（不计 bit）
        if i + 1 < n and pulses[i + 1][0] == 0 and pulses[i + 1][1] > LONG_US * 2:
            i += 2
            continue
        if pd._close(w, SHORT_US, 0.30):
            bits.append(0)
        elif pd._close(w, LONG_US, 0.30):
            bits.append(1)
        else:
            break
        i += 2
    return bits


def decode_kerui(bits: list[int]) -> dict:
    """24bit bit 流 → 统一 dict。bit 数不足抛 ValueError。"""
    if len(bits) < 24:
        raise ValueError(f"Kerui 需要 24 bit，实际 {len(bits)}")
    value = 0
    for b in bits[:24]:
        value = (value << 1) | b
    sensor_id = (value >> 4) & 0xFFFFF   # 高 20bit
    cmd = value & 0xF                    # 低 4bit

    return {
        "protocol": "kerui",
        "id": sensor_id,
        "channel": None,                 # EV1527 无 channel 概念
        "temperature": None,
        "humidity": None,
        "battery": None,
        "raw_bits": pd.bits_to_str(bits[:24]),
        "crc_ok": None,                  # 无校验位（重复帧一致性判据见固件层）
        "cmd": cmd,
    }


def decode_kerui_pulses(pulses: list[pd.Pulse]) -> dict:
    """脉冲序列 → 统一 dict。"""
    bits = kerui_pulses_to_bits(pulses)
    if len(bits) < 24:
        raise ValueError(f"Kerui 从脉冲解出 {len(bits)} bit，不足 24")
    return decode_kerui(bits)


def encode_kerui(*, sensor_id: int, cmd: int = 0x2) -> list[pd.Pulse]:
    """字段 → OOK-PWM 脉冲序列（测试合成用）。"""
    if not 0 <= sensor_id < (1 << 20):
        raise ValueError(f"sensor_id 越界: {sensor_id}（0..1048575）")
    if not 0 <= cmd < 16:
        raise ValueError(f"cmd 越界: {cmd}（0..15）")

    value = (sensor_id << 4) | cmd
    bits = [(value >> k) & 1 for k in range(23, -1, -1)]

    pulses: list[pd.Pulse] = [(1, SHORT_US), (0, SYNC_GAP_US)]  # 前置同步位
    for bit in bits:
        if bit == 0:
            pulses += [(1, SHORT_US), (0, LONG_US)]
        else:
            pulses += [(1, LONG_US), (0, SHORT_US)]
    return pulses
