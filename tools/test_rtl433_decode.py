# -*- coding: utf-8 -*-
"""
rtl_433 哨兵协议解码器测试 — W66-04

验收硬线：
- ≥5 个 pytest 用例，全部通过
- 断言「合成位流解码出正确温湿度/门磁事件」
"""
from __future__ import annotations

import pytest

from tools.rtl433_decode import (
    BitStream,
    DeviceType,
    decode_acurite_592txr,
    decode_kerui_ev1527,
    decode_nexus_th,
    decode_rtl433_frame,
    sx1278_register_doc,
    sx1278_register_table,
    synthesize_acurite_bitstream,
    synthesize_kerui_bitstream,
    synthesize_nexus_bitstream,
)


class TestBitStream:
    """BitStream 工具类基础测试。"""

    def test_from_bytes_roundtrip(self):
        data = b"\xAB\xCD\xEF"
        bs = BitStream.from_bytes(data)
        assert len(bs) == 24
        assert bs.to_bytes() == data

    def test_int_ctor(self):
        bs = BitStream(0b10110011)
        assert len(bs) == 8
        assert bs[0] == 1

    def test_invert(self):
        bs = BitStream.from_bytes(b"\xFF\x00")
        inv = bs.invert()
        assert inv.to_bytes() == b"\x00\xFF"

    def test_hex_str(self):
        bs = BitStream.from_bytes(b"\x12\x34")
        assert bs.hex_str() == "1234"


class TestAcurite592TXR:
    """Acurite 592TXR 56-bit OOK-PWM 温湿度站解码测试。"""

    def test_synthetic_temp_humidity(self):
        """合成位流：25.3°C / 65% / 电池OK / CH-A"""
        bs = synthesize_acurite_bitstream(
            sensor_id=0x1234,
            temperature_c=25.3,
            humidity=65,
            channel=1,
            battery_ok=True,
        )
        ev = decode_acurite_592txr(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.ACURITE_592TXR
        assert ev.temperature_c == pytest.approx(25.3, abs=0.1)
        assert ev.humidity == 65
        assert ev.battery_ok is True
        assert ev.channel == 1
        assert ev.id == 0x1234
        assert ev.checksum_ok is True

    def test_synthetic_battery_low(self):
        """电池低：battery_ok=False"""
        bs = synthesize_acurite_bitstream(
            sensor_id=0x9999,
            temperature_c=10.0,
            humidity=80,
            battery_ok=False,
        )
        ev = decode_acurite_592txr(bs)
        assert ev is not None
        assert ev.battery_ok is False

    def test_checksum_fail_rejected(self):
        """校验和错误帧必须拒绝（返回 None）"""
        bs = synthesize_acurite_bitstream(
            sensor_id=0x1234,
            temperature_c=20.0,
            humidity=50,
        )
        # 篡改一 bit 破坏 checksum
        bits = bs._bits[:]
        bits[10] ^= 1  # flip bit 10
        corrupted = BitStream(bits)
        ev = decode_acurite_592txr(corrupted)
        assert ev is None

    def test_auto_detect_acurite(self):
        """主入口 auto-detect 识别 Acurite"""
        bs = synthesize_acurite_bitstream(0xABCD, 18.5, 55)
        ev = decode_rtl433_frame(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.ACURITE_592TXR
        assert ev.temperature_c == pytest.approx(18.5, abs=0.1)

    def test_temperature_negative(self):
        """负温度：-5.2°C"""
        bs = synthesize_acurite_bitstream(
            sensor_id=0x100,
            temperature_c=-5.2,
            humidity=40,
        )
        ev = decode_acurite_592txr(bs)
        assert ev is not None
        assert ev.temperature_c == pytest.approx(-5.2, abs=0.1)


class TestNexusTH:
    """Nexus TH 36-bit OOK-PPM 温湿度传感器解码测试。"""

    def test_synthetic_nexus_temp_humidity(self):
        """合成位流：22.1°C / 58% / 电池OK / CH2"""
        bs = synthesize_nexus_bitstream(
            sensor_id=0xAB,
            temperature_c=22.1,
            humidity=58,
            channel=2,
            battery_ok=True,
        )
        ev = decode_nexus_th(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.NEXUS_TH
        assert ev.temperature_c == pytest.approx(22.1, abs=0.1)
        assert ev.humidity == 58
        assert ev.channel == 2
        assert ev.battery_ok is True
        assert ev.checksum_ok is True  # 无校验，以 const=0xF 替代

    def test_const_nibble_rejects_invalid(self):
        """const nibble != 0xF 时必须拒绝"""
        bs = synthesize_nexus_bitstream(0x10, 20.0, 50)
        # 破坏 const nibble（nibble 6，从 bit 24 开始，持续 4 bit）
        bits = bs._bits[:]
        bits[24] ^= 1  # flip MSB of nibble 6
        bad = BitStream(bits)
        ev = decode_nexus_th(bad)
        assert ev is None

    def test_auto_detect_nexus(self):
        """主入口 auto-detect 识别 Nexus"""
        bs = synthesize_nexus_bitstream(0x55, 15.0, 70)
        ev = decode_rtl433_frame(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.NEXUS_TH
        assert ev.temperature_c == pytest.approx(15.0, abs=0.1)


class TestKeruiEV1527:
    """Kerui/EV1527 24-bit OOK-PWM 门磁/PIR 安防解码测试。"""

    def test_synthetic_door_open(self):
        """合成位流：开门事件（cmd=0x01）"""
        bs = synthesize_kerui_bitstream(sensor_id=0x54321, cmd=0x01)
        ev = decode_kerui_ev1527(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.KERUI_EV1527
        assert ev.cmd == 0x01
        assert ev.id == 0x54321
        assert ev.checksum_ok is True

    def test_synthetic_pir_motion(self):
        """合成位流：PIR 报警（cmd=0x04）"""
        bs = synthesize_kerui_bitstream(sensor_id=0xABCDE, cmd=0x04)  # 20-bit 合法 id
        ev = decode_kerui_ev1527(bs)
        assert ev is not None
        assert ev.cmd == 0x04
        assert ev.id == 0xABCDE

    def test_all_zero_rejected(self):
        """全零帧必须拒绝（EV1527 芯片最小跳变要求）"""
        bs = BitStream([0] * 24)
        ev = decode_kerui_ev1527(bs)
        assert ev is None

    def test_auto_detect_kerui(self):
        """主入口 auto-detect 识别 Kerui"""
        bs = synthesize_kerui_bitstream(0xABCDE, 0x02)
        ev = decode_rtl433_frame(bs)
        assert ev is not None
        assert ev.device_type == DeviceType.KERUI_EV1527


class TestSX1278Config:
    """SX1278 OOK 寄存器配置表测试。"""

    def test_acurite_config_regs(self):
        regs = sx1278_register_table("acurite")
        assert len(regs) == 7
        assert all(r.addr > 0 for r in regs)

    def test_nexus_config_regs(self):
        regs = sx1278_register_table("nexus")
        assert len(regs) == 7
        # Nexus 应比 Acurite 带宽更窄
        acurite_bw = next(r for r in sx1278_register_table("acurite") if r.name == "RegRxBw")
        nexus_bw = next(r for r in regs if r.name == "RegRxBw")
        # 数值越大带宽越窄
        assert nexus_bw.value > acurite_bw.value

    def test_register_doc_generated(self):
        doc = sx1278_register_doc()
        assert "RegOpMode" in doc
        assert "RegRxBw" in doc
        assert "Acurite" in doc
        assert "Nexus" in doc
