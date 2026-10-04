"""OOK 433MHz 解码器功能到达测试（pulse_demod 原语 + 3 协议编解码闭环）。

历史说明：本套测试源文件曾被删除（仅 __pycache__ 残留 test_ook_decoders.pyc），
导致 OOK 解码链路长期无回归。本轮全仓审查恢复并补齐：
- pulse_demod 原语（classify_pwm / bits_to_bytes / crc8 / 偶校验 / extract_pulses）
- acurite(PWM 56bit) / nexus(PPM 36bit) / kerui(PWM 24bit) 编解码 roundtrip
- lacrosse 可导入回归（其 classify_pwm 依赖曾缺失，导致 ImportError 潜伏）
"""
import numpy as np
import pytest

from mcpserver.rf_brain.decoders import registry
from mcpserver.rf_brain.decoders.ook import acurite, kerui, nexus
from mcpserver.rf_brain.decoders.ook import pulse_demod as pd

# ---------------------------------------------------------------- pulse_demod 原语

def test_classify_pwm_short_long_unknown():
    w = np.array([256.0, 500.0, 9999.0])
    bits = pd.classify_pwm(w, 256.0, 500.0)
    assert list(bits) == [0, 1, -1]  # 短=0 长=1 未知=-1


def test_bits_to_bytes_msb_first():
    bits = [0, 0, 0, 0, 1, 0, 1, 0]  # 0x0A
    assert pd.bits_to_bytes(bits) == [0x0A]


def test_crc8_basic_properties():
    assert pd.crc8(b"") == 0                    # init=0，空输入
    a = pd.crc8(b"123456789")
    assert a == pd.crc8(b"123456789")            # 确定性
    assert 0 <= a <= 0xFF
    assert a != pd.crc8(b"123456788")            # 变更输入 → 变化


def test_even_parity_roundtrip():
    for v in (0x00, 0x55, 0x3F, 0x7F, 0x01):
        p = pd.even_parity_bit(v)
        byte = (p << 7) | (v & 0x7F)
        assert pd.even_parity_ok(byte) is True    # 补位后必为偶校验


def test_extract_pulses_on_carrier_burst():
    # 静默 → 载波突发 → 静默，应提取出以高电平开头的脉冲序列
    fs = 250000.0
    iq = np.concatenate([
        np.zeros(2000, dtype=complex),
        np.ones(2000, dtype=complex),
        np.zeros(2000, dtype=complex),
    ])
    pulses = pd.extract_pulses(iq, fs)
    assert pulses and pulses[0][0] == 1           # 以高电平起始
    assert any(lvl == 0 for lvl, _ in pulses)      # 含静默段


# ---------------------------------------------------------------- 协议编解码闭环

def test_acurite_roundtrip():
    pulses = acurite.encode_acurite(sensor_id=0x1234, channel="B",
                                    battery=True, temperature_c=21.5, humidity=63)
    out = acurite.decode_acurite_pulses(pulses)
    assert out["protocol"] == "acurite"
    assert out["crc_ok"] is True
    assert out["id"] == 0x1234
    assert out["channel"] == "B"
    assert out["temperature"] == 21.5
    assert out["humidity"] == 63
    assert out["battery"] == "OK"


def test_nexus_roundtrip():
    pulses = nexus.encode_nexus(device_id=0x2A, channel=2, battery=True,
                                temperature_c=-7.3, humidity=48)
    out = nexus.decode_nexus_pulses(pulses)
    assert out["protocol"] == "nexus"
    assert out["crc_ok"] is True                   # const nibble == 0xF
    assert out["id"] == 0x2A
    assert out["channel"] == 2
    assert out["temperature"] == -7.3
    assert out["humidity"] == 48


def test_kerui_roundtrip():
    pulses = kerui.encode_kerui(sensor_id=0x54321, cmd=0x7)
    out = kerui.decode_kerui_pulses(pulses)
    assert out["protocol"] == "kerui"
    assert out["id"] == 0x54321
    assert out["cmd"] == 0x7
    assert out["crc_ok"] is None                    # EV1527 无校验位（诚实不判）


def test_lacrosse_importable_and_classifies():
    # 回归：lacrosse.py 曾因 pulse_demod 缺 classify_pwm 而 ImportError
    from mcpserver.rf_brain.decoders.ook import lacrosse
    # 41bit 帧脉冲宽度 → 解码为 raw 骨架（回归：raw.tolist() 曾对 list 报错）
    widths = np.array([256.0 if (i % 3) else 500.0 for i in range(41)])
    out = lacrosse.decode_lacrosse(widths)
    assert out is not None
    assert out["protocol"] == "lacrosse-tx141th-bv2"
    assert out["raw_bits"] == 41
    assert isinstance(out["raw_hex"], str)
    # 长度不符应诚实返回 None
    assert lacrosse.decode_lacrosse(np.array([256.0, 500.0])) is None


def test_registry_has_ook_decoders():
    names = registry.list_decoders()
    for n in ("acurite", "nexus", "kerui"):
        assert n in names
        assert registry.get_decoder(n).demod_mode == "ook"