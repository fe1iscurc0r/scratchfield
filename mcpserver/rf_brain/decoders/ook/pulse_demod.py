"""OOK 脉冲解调（pulse width → bit 流）

协议无关：只负责脉冲时序分类 → bit，不关心上层协议语义。
SX1278 OOK 模式输出的是解调后的脉冲序列（高低电平持续时间），
不是 IQ 样本——本模块就是"脉冲序列 → bit"这一层，供固件（N-03）
与纯 Python 解码器（N-02）共用同一套分类逻辑。

三种编码（覆盖 rtl_433 常见 433MHz 传感器）：
- PWM：短脉冲 = 0，长脉冲 = 1（Acurite 族、LaCrosse 族）
- PPM：短 gap = 0，长 gap = 1（门磁/遥控类）
- Manchester：上升沿 = 1，下降沿 = 0（少数传感器）

设计纪律：纯 Python、无重依赖、抛 ValueError（由上层注册包装转
DecodeResult）。分类阈值 = 短/长标称中值，容差独立可配。
"""
from __future__ import annotations

import numpy as np


def classify_pwm(
    pulse_widths_us: np.ndarray,
    short_us: float = 500.0,
    long_us: float = 1000.0,
    tolerance: float = 0.30,
) -> np.ndarray:
    """PWM 分类：脉冲宽度 → bit（短=0，长=1）。

    阈值取 short/long 的几何中点，宽度落在 [short*(1-tol), long*(1+tol)]
    之外视为无效（返回 -1，供上层丢弃该帧）。
    """
    widths = np.asarray(pulse_widths_us, dtype=float)
    midpoint = (short_us + long_us) / 2.0
    lo = short_us * (1.0 - tolerance)
    hi = long_us * (1.0 + tolerance)
    bits = np.where(widths < midpoint, 0, 1).astype(np.int8)
    bits[(widths < lo) | (widths > hi)] = -1
    return bits


def classify_ppm(
    gap_widths_us: np.ndarray,
    short_us: float = 500.0,
    long_us: float = 1000.0,
    tolerance: float = 0.30,
) -> np.ndarray:
    """PPM 分类：gap 宽度 → bit（短 gap=0，长 gap=1）。"""
    return classify_pwm(gap_widths_us, short_us, long_us, tolerance)


def classify_manchester(
    transitions: np.ndarray,
) -> np.ndarray:
    """Manchester 分类：跳变方向 → bit（上升沿=1，下降沿=0）。

    输入 transitions 为相邻样本差分符号（+1 上升 / -1 下降）。
    """
    t = np.asarray(transitions, dtype=float)
    return np.where(t > 0, 1, 0).astype(np.int8)


def bits_to_bytes(bits: np.ndarray, msb_first: bool = True) -> np.ndarray:
    """bit 流 → 字节流（MSB-first，不足 8 位左补零）。

    输入为 0/1（或含 -1 无效位），长度不必是 8 的倍数。
    """
    b = np.asarray(bits, dtype=np.int8)
    n = len(b)
    # 左补零到 8 的倍数（MSB-first 时高位在前）
    pad = (-n) % 8
    padded = np.concatenate([np.zeros(pad, dtype=np.int8), b])
    nbytes = len(padded) // 8
    out = np.zeros(nbytes, dtype=np.uint8)
    for i in range(nbytes):
        byte_bits = padded[i * 8:(i + 1) * 8]
        val = 0
        for bit in byte_bits:
            val = (val << 1) | int(bit)
        out[i] = val
    return out


def even_parity(bits7: int) -> int:
    """7bit 数据的偶校验位（返回使总 1 数为偶的 p 位，0/1）。"""
    return int(bin(bits7 & 0x7F).count("1") % 2 == 1)


def check_even_parity(byte: int) -> bool:
    """校验一个 8bit 字节（含 p 位）的偶校验是否成立。"""
    return bin(byte & 0xFF).count("1") % 2 == 0
