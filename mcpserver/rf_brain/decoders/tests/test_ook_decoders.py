"""OOK 解码器测试（N-02 验收）

用 N-01 报告里的真实帧格式合成脉冲序列，断言解出正确字段。
覆盖：PWM 分类 / 奇偶校验对错 / CRC 对错 / Tower 温湿度 / 515 冰箱冷冻 /
LaCrosse 骨架 / 无效脉冲丢弃。
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.decoders.ook.pulse_demod import (
    bits_to_bytes,
    check_even_parity,
    classify_pwm,
    even_parity,
)
from mcpserver.rf_brain.decoders.ook.acurite import decode_acurite
from mcpserver.rf_brain.decoders.ook.lacrosse import decode_lacrosse

_SHORT = 500.0
_LONG = 1000.0


def _bits_to_pulses(bits: list[int], short=_SHORT, long=_LONG) -> np.ndarray:
    """0→短脉冲，1→长脉冲，还原 PWM 脉冲序列。"""
    return np.array([short if b == 0 else long for b in bits], dtype=float)


def _build_tower_frame(channel="C", device_id=0x1234, battery_ok=True,
                       temp_c=25.0, humidity=50) -> np.ndarray:
    """构造合法 Tower 帧的字节流（含奇偶 + 校验和）。

    温度编码 = (C + 1000) * 10，取 11bit（自洽解读）。
    """
    ch = {"C": 0, "B": 2, "A": 3}[channel]
    b0 = (ch << 6) | ((device_id >> 8) & 0x3F)
    b1 = device_id & 0xFF
    b2 = (0 if battery_ok else 0) | 0x04  # battery 位先占 0，parity 稍后填
    if battery_ok:
        b2 |= 0x40
    b3 = humidity & 0x7F
    raw_temp = int(temp_c * 10.0 + 1000.0)  # 编码 C*10 + 1000
    b4 = (raw_temp >> 7) & 0x0F
    b5 = raw_temp & 0x7F
    # 填 parity（偶校验）：byte2/3/4/5 的 MSB
    for idx, val in ((2, b2), (3, b3), (4, b4), (5, b5)):
        if check_even_parity(val):
            pass  # 偶校验已满足，MSB 保持 0
        else:
            # 需要置 MSB 使 1 的个数为偶
            val |= 0x80
        if idx == 2:
            b2 = val
        elif idx == 3:
            b3 = val
        elif idx == 4:
            b4 = val
        else:
            b5 = val
    body = [b0, b1, b2, b3, b4, b5]
    checksum = sum(body) & 0xFF
    return np.array(body + [checksum], dtype=np.uint8)


def _bytes_to_bits(byte_arr: np.ndarray) -> list[int]:
    """字节流 → MSB-first bit 流。"""
    bits = []
    for byte in byte_arr:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def test_classify_pwm_short_long():
    pulses = np.array([500.0, 1000.0, 500.0, 1000.0])
    bits = classify_pwm(pulses, 500.0, 1000.0)
    assert bits.tolist() == [0, 1, 0, 1]


def test_classify_pwm_invalid_out_of_range():
    pulses = np.array([100.0, 500.0, 1000.0, 3000.0])
    bits = classify_pwm(pulses, 500.0, 1000.0)
    assert bits[0] == -1  # 100us 太短
    assert bits[3] == -1  # 3000us 太长
    assert bits[1] == 0
    assert bits[2] == 1


def test_tower_temperature_humidity_crc_ok():
    frame = _build_tower_frame(channel="C", device_id=0x1234,
                               temp_c=25.0, humidity=50)
    pulses = _bits_to_pulses(_bytes_to_bits(frame))
    r = decode_acurite(pulses)
    assert r is not None
    assert r["protocol"] == "acurite-tower"
    assert r["id"] == 0x1234
    assert r["channel"] == "C"
    assert r["humidity_pct"] == 50
    assert abs(r["temperature_c"] - 25.0) < 0.2  # 精度断言
    assert r["crc_ok"] is True


def test_tower_negative_temperature():
    frame = _build_tower_frame(temp_c=-10.0, humidity=80)
    pulses = _bits_to_pulses(_bytes_to_bits(frame))
    r = decode_acurite(pulses)
    assert r is not None
    assert abs(r["temperature_c"] - (-10.0)) < 0.2
    assert r["humidity_pct"] == 80


def test_tower_crc_fail():
    frame = _build_tower_frame(temp_c=25.0)
    frame[-1] ^= 0xFF  # 破坏校验和
    pulses = _bits_to_pulses(_bytes_to_bits(frame))
    r = decode_acurite(pulses)
    # 校验和错 → crc_ok=False，但解码仍返回（上层据 crc_ok 决定丢弃）
    assert r is not None
    assert r["crc_ok"] is False


def test_tower_parity_fail_returns_none():
    frame = _build_tower_frame(temp_c=25.0)
    # 破坏 byte3（湿度）的奇偶：翻转最低位
    frame[3] ^= 0x01
    pulses = _bits_to_pulses(_bytes_to_bits(frame))
    r = decode_acurite(pulses)
    assert r is None  # 奇偶校验不过直接丢弃


def test_515_fridge():
    # 手工构造 515 帧（6 字节）
    ch = 0
    device_id = 0x0ABC
    b0 = (ch << 6) | ((device_id >> 8) & 0x3F)
    b1 = device_id & 0xFF
    b2 = 0x40 | 0x08  # battery OK + msg type fridge
    raw_f = int(32.0 * 10.0 + 1480.0)  # 32°F，编码 F*10 + 1480
    b3 = (raw_f >> 7) & 0x7F
    b4 = raw_f & 0x7F
    # 填 parity
    for idx, val in ((2, b2), (3, b3), (4, b4)):
        if not check_even_parity(val):
            val |= 0x80
        if idx == 2:
            b2 = val
        elif idx == 3:
            b3 = val
        else:
            b4 = val
    body = [b0, b1, b2, b3, b4]
    checksum = sum(body) & 0xFF
    frame = np.array(body + [checksum], dtype=np.uint8)
    pulses = _bits_to_pulses(_bytes_to_bits(frame))
    r = decode_acurite(pulses)
    assert r is not None
    assert r["protocol"] == "acurite-515"
    assert r["kind"] == "fridge"
    assert r["id"] == 0x0ABC
    assert abs(r["temperature_f"] - 32.0) < 0.2


def test_lacrosse_bv2_41bit_skeleton():
    # 41bit 随机帧 → 骨架返回 raw_hex，不编造字段
    bits = [int(b) for b in np.random.default_rng(42).integers(0, 2, 41)]
    pulses = np.array([256.0 if b == 0 else 500.0 for b in bits])
    r = decode_lacrosse(pulses)
    assert r is not None
    assert r["protocol"] == "lacrosse-tx141th-bv2"
    assert r["raw_bits"] == 41
    assert r["crc_ok"] is None  # 待校准，不编造


def test_lacrosse_wrong_length_returns_none():
    pulses = np.array([256.0, 500.0, 256.0])  # 只有 3 个脉冲
    assert decode_lacrosse(pulses) is None


def test_even_parity_util():
    # 偶校验：7bit 数据 1 的个数为奇时 p=1（凑偶），为偶时 p=0
    assert even_parity(0x55) == 0   # 0x55 = 0101 0101 = 4 个 1（偶）
    assert even_parity(0x57) == 1   # 0x57 = 0101 0111 = 5 个 1（奇）
    assert check_even_parity(0x55) is True    # 4 个 1，偶校验成立
    assert check_even_parity(0xD6) is False   # 0xD6 = 1101 0110 = 5 个 1（奇）
