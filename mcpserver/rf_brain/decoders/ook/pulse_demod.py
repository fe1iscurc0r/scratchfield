"""OOK 脉冲解调原语（独立实现）。

参考 rtl_433（GPL-2.0-or-later）协议文档，仅引「协议格式/脉冲时序」这一公开事实，
未复制其 C 解码代码。本模块把 SX1278 OOK 包络采样得到的高低电平脉冲序列
转换成 bit 流，支持三种编码：PWM（脉宽编码）、PPM（距离编码）、Manchester。

脉冲表示约定：
    Pulse = (level, width_us)
    level   : 1 = 高电平（载波在），0 = 低电平（静默）
    width_us: 该电平持续时长（微秒）
脉冲列表以高电平开头，高低交替。
"""
from __future__ import annotations

import numpy as np

Pulse = tuple[int, float]


# ---------------------------------------------------------------- 包络提取

def extract_pulses(iq, sample_rate: float, *,
                   threshold_db: float = -30.0,
                   hysteresis_db: float = 6.0,
                   min_pulse_us: float = 40.0,
                   max_pulse_us: float = 60000.0) -> list[Pulse]:
    """从 OOK 复包络 IQ 提取 (level, width_us) 脉冲序列。

    |iq| 归一化后取 dB 包络，带迟滞阈值比较（防边沿抖动）：
    高于 threshold_db 判高、低于 threshold_db - hysteresis_db 判低。
    """
    x = np.abs(np.asarray(iq, dtype=np.complex128))
    x = x / (np.max(x) + 1e-12)
    eps = 1e-12
    db = 20.0 * np.log10(x + eps)
    hi = threshold_db
    lo = threshold_db - hysteresis_db

    dt_us = 1e6 / sample_rate
    pulses: list[Pulse] = []
    # 从第一个高于门限的样本开始
    start = 0
    while start < db.size and db[start] < hi:
        start += 1
    if start >= db.size:
        return pulses

    level = 1
    run_start = start
    for i in range(start, db.size):
        v = db[i]
        if level == 1 and v < lo:
            pulses.append((1, (i - run_start) * dt_us))
            level = 0
            run_start = i
        elif level == 0 and v > hi:
            pulses.append((0, (i - run_start) * dt_us))
            level = 1
            run_start = i
    pulses.append((level, (db.size - run_start) * dt_us))

    # 过滤极短毛刺与超长尾迹
    out = []
    for lvl, w in pulses:
        if min_pulse_us <= w <= max_pulse_us:
            out.append((lvl, w))
    return out


# ---------------------------------------------------------------- 位切分

def _close(w: float, ref: float, tolerance: float) -> bool:
    return abs(w - ref) <= tolerance * ref


def classify_pwm(pulse_widths_us, short_us: float, long_us: float, *,
                 tolerance: float = 0.30):
    """把一组高脉冲宽度(µs)按 PWM 门限向量化分类：短=0，长=1，其它=-1（未知）。

    与 pwm_to_bits 互补：后者吃高低交替的脉冲对并按同步/包尾切分，本函数
    面向「已提取的高脉冲宽度数组」做整帧 bit 分类，供 lacrosse 等协议骨架调用。
    判据与 _close 一致（|w-ref| <= tolerance*ref）。
    """
    w = np.asarray(pulse_widths_us, dtype=float)
    bits = np.full(w.shape, -1, dtype=int)
    bits[np.abs(w - short_us) <= tolerance * short_us] = 0
    bits[np.abs(w - long_us) <= tolerance * long_us] = 1
    return bits


def pwm_to_bits(pulses: list[Pulse], short_us: float, long_us: float, *,
                sync_us: float | None = None,
                reset_us: float | None = None,
                tolerance: float = 0.30) -> list[int]:
    """PWM 编码：bit 由「高脉冲宽度」决定，短脉冲=0、长脉冲=1。

    - sync_us：帧头同步脉冲宽度（若给定，则跳过该脉冲及其后间隔）
    - reset_us：包结束间隔宽度（该宽度的低电平间隔视为包尾，停止）
    """
    bits: list[int] = []
    n = len(pulses)
    i = 0
    while i < n:
        lvl, w = pulses[i]
        if lvl != 1:
            i += 1
            continue
        if sync_us is not None and _close(w, sync_us, tolerance):
            i += 2  # 跳过同步脉冲 + 其间隔
            continue
        if _close(w, short_us, tolerance):
            bit = 0
        elif _close(w, long_us, tolerance):
            bit = 1
        else:
            break  # 未知宽度：噪声或采样异常，停止
        bits.append(bit)
        # 检查其后间隔是否到达包尾
        if i + 1 < n and pulses[i + 1][0] == 0:
            gap = pulses[i + 1][1]
            if reset_us is not None and gap >= reset_us * (1.0 - tolerance):
                break
        i += 2
    return bits


def ppm_to_bits(pulses: list[Pulse], pulse_us: float,
                short_gap_us: float, long_gap_us: float, *,
                sync_gap_us: float | None = None,
                tolerance: float = 0.30) -> list[int]:
    """PPM（距离编码）：脉冲宽度固定，bit 由「脉冲后的低电平间隔」决定，
    短间隔=0、长间隔=1。sync_gap_us：同步间隔（跳过，不计入 bit）。
    """
    bits: list[int] = []
    n = len(pulses)
    i = 0
    while i < n:
        lvl, w = pulses[i]
        if lvl != 1:
            i += 1
            continue
        if not _close(w, pulse_us, tolerance):
            i += 1
            continue
        if i + 1 < n and pulses[i + 1][0] == 0:
            gap = pulses[i + 1][1]
            if sync_gap_us is not None and _close(gap, sync_gap_us, tolerance):
                i += 2
                continue
            if _close(gap, short_gap_us, tolerance):
                bits.append(0)
            elif _close(gap, long_gap_us, tolerance):
                bits.append(1)
            else:
                break  # 到达包尾或噪声
            i += 2
        else:
            i += 1
    return bits


def manchester_to_bits(pulses: list[Pulse], half_period_us: float, *,
                       reset_us: float | None = None,
                       tolerance: float = 0.30) -> list[int]:
    """Manchester 编码：每位占 2×half_period_us。

    简化实现（无复杂时钟恢复）：相邻两半周期内「高→低」跳变=1，「低→高」=0，
    半周期宽度 close 到 half_period_us 视为有效沿。
    注：OSv1 类慢速 Manchester 已在本期选型中排除，此实现为完整性保留。
    """
    bits: list[int] = []
    n = len(pulses)
    i = 0
    while i + 1 < n:
        lvl0, w0 = pulses[i]
        lvl1, w1 = pulses[i + 1]
        if reset_us is not None and lvl0 == 0 and w0 >= reset_us * (1 - tolerance):
            break
        if (lvl0 == 1 and lvl1 == 0
                and _close(w0, half_period_us, tolerance)
                and _close(w1, half_period_us, tolerance)):
            bits.append(1)
            i += 2
        elif (lvl0 == 0 and lvl1 == 1
                and _close(w0, half_period_us, tolerance)
                and _close(w1, half_period_us, tolerance)):
            bits.append(0)
            i += 2
        else:
            i += 1
    return bits


# ---------------------------------------------------------------- 通用工具

def invert_bits(bits: list[int]) -> list[int]:
    return [1 - b for b in bits]


def bits_to_str(bits: list[int]) -> str:
    return "".join("1" if b else "0" for b in bits)


def bits_to_bytes(bits: list[int]) -> list[int]:
    """MSB 先，8bit 一组转字节（不足 8bit 丢弃尾部）。"""
    out: list[int] = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        out.append(byte)
    return out


def crc8(data: bytes, poly: int = 0x31, init: int = 0x00) -> int:
    """CRC-8（Dallas/Maxim 风格，poly 反射 0x31），供协议校验参考。"""
    crc = init & 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc >> 1) ^ poly) if (crc & 1) else (crc >> 1)
    return crc & 0xFF


def even_parity_bit(byte7: int) -> int:
    """返回使 8bit 字节中 1 的个数为偶数所需的奇偶位（偶校验）。"""
    return bin(byte7 & 0x7F).count("1") & 1


def even_parity_ok(byte: int) -> bool:
    """校验 byte 是否为偶校验（bit7 = 低 7 位偶校验位）。"""
    return even_parity_bit(byte & 0x7F) == ((byte >> 7) & 1)
