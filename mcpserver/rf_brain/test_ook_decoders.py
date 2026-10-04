"""N-02 · OOK 433MHz 传感器解码器验收测试（pulse_demod + acurite/nexus/kerui）

覆盖工单验收点：
1. 脉冲解调：PWM / PPM 三种编码的 bit 流切分正确性（往返：字段→脉冲→bit→字段）
2. Acurite 592TXR：字段（id/channel/temp/humidity/battery）解出 + 精度正确；
   CRC（加和 + 偶校验）对/错两路
3. Nexus TH：字段解出（含负温度有符号 12bit）+ const nibble 校验对/错两路
4. Kerui/EV1527：20bit id + 4bit cmd 解出
5. 注册表：acurite/nexus/kerui 已注册，decode(..., pulses=...) 可走注册表入口
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.decoders import (  # noqa: E402
    decode,
    list_decoders,
)
from mcpserver.rf_brain.decoders.ook import (  # noqa: E402
    acurite,
    kerui,
    nexus,
    pulse_demod,
)

# --------------------------------------------------------------------------- #
# pulse_demod：三种编码 bit 切分
# --------------------------------------------------------------------------- #

def test_pwm_slicer_roundtrip():
    """PWM：短脉冲=0/长脉冲=1 的切分 + 同步脉冲跳过。"""
    pulses = [(1, 620.0), (0, 596.0),        # 同步脉冲 + 间隔
              (1, 220.0), (0, 392.0),        # bit 0
              (1, 408.0), (0, 204.0),        # bit 1
              (1, 220.0), (0, 392.0)]        # bit 0
    bits = pulse_demod.pwm_to_bits(pulses, 220.0, 408.0,
                                   sync_us=620.0, reset_us=2192.0)
    assert bits == [0, 1, 0]


def test_ppm_slicer_roundtrip():
    """PPM：脉冲固定、间隔短=0/长=1。"""
    pulses = [(1, 500.0), (0, 1000.0),       # bit 0
              (1, 500.0), (0, 2000.0),       # bit 1
              (1, 500.0), (0, 1000.0)]       # bit 0
    bits = pulse_demod.ppm_to_bits(pulses, 500.0, 1000.0, 2000.0)
    assert bits == [0, 1, 0]


def test_manchester_slicer_roundtrip():
    """Manchester：高→低=1，低→高=0（half-period 1500µs）。"""
    pulses = [(1, 1500.0), (0, 1500.0),      # 1
              (0, 1500.0), (1, 1500.0),      # 0
              (1, 1500.0), (0, 1500.0)]      # 1
    bits = pulse_demod.manchester_to_bits(pulses, 1500.0)
    assert bits == [1, 0, 1]


# --------------------------------------------------------------------------- #
# Acurite 592TXR：字段 + CRC 对/错两路
# --------------------------------------------------------------------------- #

def _acurite_bits(**kw) -> list[int]:
    pulses = acurite.encode_acurite(**kw)
    return acurite.acurite_pulses_to_bits(pulses)


def test_acurite_roundtrip_fields_and_precision():
    """字段解出 + 温度 0.1°C / 湿度整型精度。"""
    bits = _acurite_bits(sensor_id=12345, channel="B", battery=True,
                         temperature_c=21.5, humidity=55)
    data = acurite.decode_acurite(bits)
    assert data["protocol"] == "acurite"
    assert data["id"] == 12345
    assert data["channel"] == "B"
    assert data["battery"] == "OK"
    assert data["temperature"] == 21.5
    assert data["humidity"] == 55
    assert data["crc_ok"] is True
    assert len(data["raw_bits"]) == 56


def test_acurite_crc_pass_and_fail():
    """CRC 对/错两路：完整帧通过，翻转 1 bit 后加和校验失败。"""
    bits = _acurite_bits(sensor_id=9999, channel="A", temperature_c=0.0,
                         humidity=40)
    assert acurite.decode_acurite(bits)["crc_ok"] is True

    bad = list(bits)
    bad[30] ^= 1                                   # 翻转湿度字段中间位
    assert acurite.decode_acurite(bad)["crc_ok"] is False


def test_acurite_battery_low_and_channel_c():
    """battery=LOW 与 channel=C 的边界映射。"""
    bits = _acurite_bits(sensor_id=0, channel="C", battery=False,
                         temperature_c=25.0, humidity=1)
    data = acurite.decode_acurite(bits)
    assert data["battery"] == "LOW"
    assert data["channel"] == "C"
    assert data["crc_ok"] is True


# --------------------------------------------------------------------------- #
# Nexus TH：字段（含负温度有符号 12bit）+ const nibble 校验
# --------------------------------------------------------------------------- #

def test_nexus_roundtrip_fields_and_negative_temp():
    """字段解出 + 负温度（有符号 12bit 补码）。"""
    pulses = nexus.encode_nexus(device_id=0xAB, channel=2, battery=True,
                                temperature_c=-5.0, humidity=63)
    data = nexus.decode_nexus_pulses(pulses)
    assert data["protocol"] == "nexus"
    assert data["id"] == 0xAB
    assert data["channel"] == 2
    assert data["battery"] == "OK"
    assert data["temperature"] == -5.0
    assert data["humidity"] == 63
    assert data["crc_ok"] is True


def test_nexus_const_nibble_pass_and_fail():
    """const nibble（完整性判据）对/错两路。"""
    pulses = nexus.encode_nexus(device_id=0x12, channel=1, temperature_c=20.0,
                                humidity=50)
    bits = nexus.nexus_pulses_to_bits(pulses)
    assert nexus.decode_nexus(bits)["crc_ok"] is True

    # 破坏 const nibble（第 6 个 nibble，bit 24..27），其余不动
    bad = list(bits)
    bad[24] ^= 1
    assert nexus.decode_nexus(bad)["crc_ok"] is False


# --------------------------------------------------------------------------- #
# Kerui / EV1527：20bit id + 4bit cmd
# --------------------------------------------------------------------------- #

def test_kerui_roundtrip():
    pulses = kerui.encode_kerui(sensor_id=0x3ABCD, cmd=0x2)
    data = kerui.decode_kerui_pulses(pulses)
    assert data["protocol"] == "kerui"
    assert data["id"] == 0x3ABCD
    assert data["cmd"] == 0x2
    assert data["crc_ok"] is None                 # 无校验位
    assert len(data["raw_bits"]) == 24


# --------------------------------------------------------------------------- #
# 注册表接入
# --------------------------------------------------------------------------- #

def test_ook_decoders_registered_and_decodable():
    names = list_decoders()
    assert {"acurite", "nexus", "kerui"} <= set(names)

    pulses = acurite.encode_acurite(sensor_id=77, channel="A",
                                    temperature_c=22.3, humidity=48)
    r = decode("acurite", [0j], 250000.0, pulses=pulses)
    assert r.success, r.message
    assert r.payload["id"] == 77 and r.payload["temperature"] == 22.3


if __name__ == "__main__":
    test_pwm_slicer_roundtrip()
    test_ppm_slicer_roundtrip()
    test_manchester_slicer_roundtrip()
    test_acurite_roundtrip_fields_and_precision()
    test_acurite_crc_pass_and_fail()
    test_acurite_battery_low_and_channel_c()
    test_nexus_roundtrip_fields_and_negative_temp()
    test_nexus_const_nibble_pass_and_fail()
    test_kerui_roundtrip()
    test_ook_decoders_registered_and_decodable()
    print("\n🎉 N-02 OOK 解码器全部自测通过")
