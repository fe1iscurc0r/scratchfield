"""OOK 脉冲解调 + 433MHz 传感器协议解码器（独立实现）。

参考 rtl_433（GPL-2.0-or-later）协议文档，仅引用「协议格式」公开事实，
未复制任何 C 代码。本包不主动注册解码器，由上层 decoders/__init__.py
统一导入触发注册（与 aprs/psk31/dtmf/pocsag 同构）。

模块：
    pulse_demod  脉冲序列 → bit 流（PWM/PPM/Manchester）+ CRC/奇偶工具
    acurite      Acurite 592TXR/Tower（OOK-PWM 56bit）
    nexus        Nexus TH（OOK-PPM 36bit）
    kerui        Kerui/EV1527（OOK-PWM 24bit）
"""
from __future__ import annotations

from . import acurite, kerui, nexus, pulse_demod  # noqa: F401

__all__ = ["pulse_demod", "acurite", "nexus", "kerui"]
