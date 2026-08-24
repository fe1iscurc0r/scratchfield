"""Acurite 433MHz 传感器解码器（Tower 592TXR + 515 冰箱/冷冻）

协议格式事实来源：公开 gist《Acurite Sensor Message Format》
（https://gist.github.com/rct/b144c4c873aaa469545b06052c8f4136）。
rtl_433（GPL-2.0）仅作协议文档参照，本模块为独立实现，不复制其 C 代码。

帧格式（Tower 592TXR，msg type 0x04，7 字节 56bit）：
    Byte 0    Byte 1    Byte 2    Byte 3    Byte 4    Byte 5    Byte 6
    CCII IIII | IIII IIII | pB00 0100 | pHHH HHHH | p??T TTTT | pTTT TTTT | KKKK KKKK
    C=channel(2b) I=ID(14b) p=parity B=battery(1b) M=type(6b)
    H=湿度(7b, %)  T=温度(11b 可用, 编码 (C+1000)*10)  K=checksum(8b)

515 冰箱/冷冻（msg type 0x08/0x09，6 字节 48bit）：
    Byte 0    Byte 1    Byte 2    Byte 3    Byte 4    Byte 5
    CCII IIII | IIII IIII | pBMM MMMM | bTTT TTTT | bTTT TTTT | KKKK KKKK
    T=温度 Fahrenheit(14b, 编码 (F+1480)*10)

诚实标注：
- 校验 = 8bit 求和（byte0..n-1 求和取低 8 位）+ 每字节（除 0/1/末）偶校验 —— 确定。
- 温度 bit 拼接：gist 自标 @todo/TBD，本文档与 rtl_433 源码对 Tower 温度
  位数有分歧（11/12/14bit）。本实现采用 11bit 自洽解读（Byte4 低 4bit 高位
  + Byte5 低 7bit 低位），物理量换算 celsius = raw/10 - 1000 标注「待真机
  校准」。真机样本到位后只需改 _temp_from_raw 一个函数，不影响解码框架。
"""
from __future__ import annotations

import numpy as np

from .pulse_demod import bits_to_bytes, check_even_parity, classify_pwm

# Acurite PWM 时序（微秒）：短脉冲=0，长脉冲=1
_SHORT_US = 500.0
_LONG_US = 1000.0

# msg type
_MSGTYPE_TOWER = 0x04
_MSGTYPE_515_FRIDGE = 0x08
_MSGTYPE_515_FREEZER = 0x09


def _checksum_ok(raw_bytes: np.ndarray) -> bool:
    """8bit 求和校验：前 n-1 字节求和取低 8 位 == 末字节。"""
    return bool((np.uint8(raw_bytes[:-1].sum(dtype=np.uint64)) == raw_bytes[-1]))


def _parity_ok(raw_bytes: np.ndarray) -> bool:
    """奇偶校验：除字节 0/1/末字节外，每字节偶校验成立。"""
    if len(raw_bytes) <= 3:
        return True
    for b in raw_bytes[2:-1]:
        if not check_even_parity(int(b)):
            return False
    return True


def _temp_from_raw_tower(raw: int) -> float:
    """Tower 温度 raw(11bit) → Celsius。编码 C*10 + 1000，待真机校准。"""
    return (raw - 1000.0) / 10.0


def _decode_tower(raw_bytes: np.ndarray) -> dict:
    """解码 Tower 592TXR 温湿度帧（7 字节）。"""
    b = [int(x) for x in raw_bytes]  # int() 转 Python int，避免 uint8 位移溢出
    channel_code = (b[0] >> 6) & 0x03
    channel = {0: "C", 2: "B", 3: "A"}.get(channel_code, "?")
    device_id = ((b[0] & 0x3F) << 8) | b[1]
    battery = "OK" if (b[2] & 0x40) else "low"
    humidity = b[3] & 0x7F
    # 温度 11bit：Byte4 低 4bit（高位）| Byte5 低 7bit（低位）
    raw_temp = ((b[4] & 0x0F) << 7) | (b[5] & 0x7F)
    temperature = _temp_from_raw_tower(raw_temp)
    return {
        "protocol": "acurite-tower",
        "id": device_id,
        "channel": channel,
        "temperature_c": round(temperature, 1),
        "humidity_pct": humidity,
        "battery": battery,
        "raw_bits": len(raw_bytes) * 8,
        "crc_ok": bool(_checksum_ok(raw_bytes)),
    }


def _decode_515(raw_bytes: np.ndarray) -> dict:
    """解码 515 冰箱/冷冻帧（6 字节）。"""
    b = [int(x) for x in raw_bytes]
    msgtype = b[2] & 0x3F
    kind = {_MSGTYPE_515_FRIDGE: "fridge", _MSGTYPE_515_FREEZER: "freezer"}.get(msgtype, "?")
    channel_code = (b[0] >> 6) & 0x03
    channel = {0: "C", 2: "B", 3: "A"}.get(channel_code, "?")
    device_id = ((b[0] & 0x3F) << 8) | b[1]
    battery = "OK" if (b[2] & 0x40) else "low"
    # 温度 Fahrenheit 14bit：Byte3 低 7bit（高位）| Byte4 低 7bit（低位）
    raw_temp = ((b[3] & 0x7F) << 7) | (b[4] & 0x7F)
    temperature_f = (raw_temp - 1480.0) / 10.0  # 编码 F*10 + 1480，待真机校准
    return {
        "protocol": "acurite-515",
        "kind": kind,
        "id": device_id,
        "channel": channel,
        "temperature_f": round(temperature_f, 1),
        "battery": battery,
        "raw_bits": len(raw_bytes) * 8,
        "crc_ok": bool(_checksum_ok(raw_bytes)),
    }


def decode_acurite(pulse_widths_us: np.ndarray) -> dict | None:
    """入口：脉冲宽度序列 → 解码结果 dict（失败返回 None）。

    自动区分 Tower(56bit) / 515(48bit) 帧，校验不过返回 None。
    """
    bits = classify_pwm(np.asarray(pulse_widths_us, dtype=float), _SHORT_US, _LONG_US)
    if np.any(bits == -1):
        return None
    raw = bits_to_bytes(bits)
    if not _parity_ok(raw):
        return None
    if len(raw) == 7 and (raw[2] & 0x3F) == _MSGTYPE_TOWER:
        return _decode_tower(raw)
    if len(raw) == 6 and (raw[2] & 0x3F) in (_MSGTYPE_515_FRIDGE, _MSGTYPE_515_FREEZER):
        return _decode_515(raw)
    return None
