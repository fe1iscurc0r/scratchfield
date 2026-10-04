"""LaCrosse TX141TH-Bv2 温湿度传感器解码（骨架）

协议格式事实来源：rtl_433 lacrosse_tx141x.c（GPL-2.0，仅文档参照，
独立实现不复制代码）+ Arduino 论坛解码记录。

OOK PWM 时序（rtl_433 实测）：短脉冲 s=256us，长脉冲 l=500us，
符号周期 r=1888us。帧长 41bit（Bv2）。

诚实标注（重要）：
- Bv2/Bv3/TX141W 多个变体帧长不同（41/33/37bit），字段位序有分歧，
  Arduino 论坛给出的 bit 段（湿度 28-35、校验 36-43）是针对老版
  TX141TH-B（43bit）的，与 Bv2(41bit) 不完全对齐。
- 因此本模块只实现「PWM 分类 + 41bit 帧切分」骨架，字段映射与 CRC
  校验留 TODO，待真机样本（或拿到权威协议文档）后校准。不编造字段。
"""
from __future__ import annotations

import numpy as np

from .pulse_demod import bits_to_bytes, classify_pwm

_SHORT_US = 256.0   # PWM 短脉冲
_LONG_US = 500.0    # PWM 长脉冲
_FRAME_BITS = 41    # Bv2 帧长


def decode_lacrosse(pulse_widths_us: np.ndarray) -> dict | None:
    """骨架：脉冲 → 41bit 帧 → 切分 raw bits（字段映射待校准）。

    返回 raw_bits 便于真机样本到位后对照解析；字段暂不给值。
    """
    bits = classify_pwm(np.asarray(pulse_widths_us, dtype=float), _SHORT_US, _LONG_US)
    if np.any(bits == -1):
        return None
    if len(bits) != _FRAME_BITS:
        return None
    raw = bits_to_bytes(bits)  # 41bit → 6 字节（高 7 位零填充），list[int]
    return {
        "protocol": "lacrosse-tx141th-bv2",
        "raw_bits": int(len(bits)),
        "raw_hex": bytes(raw).hex(),
        "crc_ok": None,  # 字段与 CRC 待真机样本校准
        "_note": "字段映射待校准，勿用于生产",
    }
