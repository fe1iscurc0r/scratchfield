# -*- coding: utf-8 -*-
"""LoRaCanary 帧协议 pytest（tools/lora_frame.py 契约测试）。

用例编号对照：
  AB-01（v1.5 GEO 扩增）    —— 本文件 G-xx 用例
  AB-04（v1 12 例 + 睡眠）  —— V-xx / S-xx 用例（见 test_lora_frame_v1.py / test_sleep_state.py）

黄金向量与 firmware/loracanary/loracanary_frame_test.cpp 同源（Python 生成、C++ 断言），
两镜像任何一侧破坏逐字节兼容，这里即红。
"""
import pytest
from lora_frame import (
    ENV_PAYLOAD_LEN,
    GEO_FRAME_LEN,
    GEO_PAYLOAD_LEN,
    MAGIC,
    TYPE_ACK,
    TYPE_ENV,
    TYPE_ERR,
    TYPE_GEO,
    TYPE_HEARTBEAT,
    build_env_payload,
    build_geo_payload,
    crc16_modbus,
    decode,
    decode_geo,
    encode,
    parse_geo_payload,
)

# ---- AB-01 · GEO 编解码 ----

class TestGeoRoundTrip:
    def test_g01_geo_full_roundtrip(self):
        """G-01 GEO 全字段往返：t/h/p/lat/lng/alt/sat 一致。"""
        b = encode(geo=True, seq=7, node_id=2, t=26.3, h=55, p=1013.2,
                   lat=39.9042, lng=116.4074, alt=52, sat=8)
        d = decode(b)
        assert d is not None
        assert d["type"] == TYPE_GEO and d["type_name"] == "geo"
        assert d["seq"] == 7 and d["node_id"] == 2
        assert abs(d["t"] - 26.3) < 0.01 and d["h"] == 55
        assert abs(d["p"] - 1013.2) < 0.01
        assert abs(d["lat"] - 39.9042) < 1e-6
        assert abs(d["lng"] - 116.4074) < 1e-6
        assert d["alt"] == 52 and d["sat"] == 8 and d["gps_fix"] is True

    def test_g02_spec_acceptance_oneliner(self):
        """G-02 工单验收一行命令（逐字照抄）。"""
        b = encode(geo=True, t=26.3, h=55, p=1013.2, lat=39.9042,
                   lng=116.4074, alt=52, sat=8)
        d = decode(b)
        assert abs(d["lat"] - 39.9042) < 1e-6 and abs(d["lng"] - 116.4074) < 1e-6

    def test_g03_geo_golden_vector_bytes(self):
        """G-03 黄金向量逐字节（C++ 镜像 loracanary_frame_test.cpp 同源）。"""
        b = encode(geo=True, seq=0, node_id=1, t=26.3, h=55, p=1013.2,
                   lat=39.9042, lng=116.4074, alt=52, sat=8)
        assert b.hex() == "d0cc030001460a37c88b0100d0e5c817105c6245340008ab6a"
        assert len(b) == GEO_FRAME_LEN  # 25B = 7 + 18
        assert len(b) - 7 == GEO_PAYLOAD_LEN

    def test_g04_geo_negative_and_boundary(self):
        """G-04 负值/边界：南半球/东经 151/负海拔/满量程 seq。"""
        b = encode(geo=True, seq=200, node_id=7, t=-12.5, h=99, p=870.5,
                   lat=-33.865143, lng=151.2099, alt=-15, sat=12)
        d = decode_geo(b)
        assert d is not None
        assert abs(d["lat"] - (-33.865143)) < 1e-6
        assert abs(d["lng"] - 151.2099) < 1e-6
        assert d["alt"] == -15 and d["sat"] == 12

    def test_g05_geo_payload_field_offsets(self):
        """G-05 定长结构逐字段偏移（SPEC v1.5 第二节，防重排）。"""
        payload = build_geo_payload(26.3, 55, 1013.2, 39.9042, 116.4074, 52, 8)
        assert len(payload) == GEO_PAYLOAD_LEN == 18
        assert payload[0:2] == (2630).to_bytes(2, "little", signed=True)   # t ×100
        assert payload[2] == 55                                            # h
        assert payload[3:7] == (101320).to_bytes(4, "little")              # p ×100
        assert payload[7:11] == (399042000).to_bytes(4, "little", signed=True)   # lat ×1e7
        assert payload[11:15] == (1164074000).to_bytes(4, "little", signed=True)  # lng ×1e7
        assert payload[15:17] == (52).to_bytes(2, "little", signed=True)   # alt
        assert payload[17] == 8                                            # sat


# ---- AB-01 · 降级（诚实标注） ----

class TestGeoDegradation:
    def test_g06_no_fix_zeroes_coords(self):
        """G-06 sat=0 → lat/lng/alt 强制 0，gps_fix=False。"""
        b = encode(geo=True, t=26.3, h=55, p=1013.2,
                   lat=39.9042, lng=116.4074, alt=52, sat=0)
        d = decode(b)
        assert d["sat"] == 0 and d["gps_fix"] is False
        assert d["lat"] == 0.0 and d["lng"] == 0.0 and d["alt"] == 0

    def test_g07_decode_garbage_never_crash(self):
        """G-07 任意垃圾输入 decode 不崩（返回 None 或空 dict）。"""
        assert decode(b"\x00" * 10) is None
        assert decode(b"") is None
        assert decode(MAGIC) is None
        assert parse_geo_payload(b"\x01" * 17) == {}   # 短 1B
        assert parse_geo_payload(b"\x01" * 19) == {}   # 长 1B
        assert decode_geo(b"\xff" * 25) is None


# ---- AB-01 · 坏帧拒绝 ----

class TestGeoBadFrames:
    def _good_geo(self) -> bytes:
        return encode(geo=True, seq=1, node_id=1, t=26.3, h=55, p=1013.2,
                      lat=39.9042, lng=116.4074, alt=52, sat=8)

    def test_g08_geo_short_payload_rejected(self):
        """G-08 GEO payload 非 18B → 拒绝（定长结构破坏）。"""
        good = self._good_geo()
        assert decode(good[:-1]) is None          # 整帧短 1B
        assert decode(good[:-3] + b"\x00\x00") is None  # CRC 后缺字段
        bad = bytearray(good) + b"\x00"           # 多 1B
        assert decode(bytes(bad)) is None

    def test_g09_geo_crc_magic_flipped(self):
        """G-09 CRC 错 / magic 错 / type 未知 → 全拒绝。"""
        good = self._good_geo()
        bad_crc = bytearray(good)
        bad_crc[-1] ^= 0xFF
        assert decode(bytes(bad_crc)) is None
        bad_magic = bytearray(good)
        bad_magic[0] = 0x00
        assert decode(bytes(bad_magic)) is None
        bad_type = bytearray(good)
        bad_type[2] = 0x04   # 未知 type，重算 CRC 使仅 type 非法
        crc = crc16_modbus(bytes(bad_type[2:-2]))
        bad_type[-2:] = crc.to_bytes(2, "little")
        assert decode(bytes(bad_type)) is None

    def test_g10_geo_out_of_range_raises(self):
        """G-10 越界入参：encode 抛 ValueError（不静默截断）。

        注：合法纬度 ±90°/经度 ±180° ×1e7 = ±1.8e9，均在 int32（±2.147e9）内，
        故 int32 溢出只会来自垃圾入参（如 300°）——这本身就是守护测试。
        """
        with pytest.raises(ValueError):
            encode(geo=True, t=26.3, h=55, p=1013.2,
                   lat=300.0, lng=116.4074, alt=52, sat=8)   # lat 300° → ×1e7 溢出 int32
        with pytest.raises(ValueError):
            encode(geo=True, t=26.3, h=55, p=1013.2,
                   lat=0, lng=0, alt=40000, sat=8)           # alt 溢出 int16
        with pytest.raises(ValueError):
            encode(geo=True, t=26.3, h=55, p=1013.2,
                   lat=0, lng=0, alt=0, sat=256)             # sat 溢出 uint8


# ---- v1 兼容回归（AB-01 改动不得破坏 v1） ----

class TestV1Compat:
    def test_g11_v1_types_unchanged(self):
        """G-11 ENV/HEARTBEAT/ACK/ERR 编解码与 v1 全兼容（ENV 用黄金向量）。"""
        e = encode(TYPE_ENV, seq=42, node_id=1,
                   payload=build_env_payload(26.3, 55, 1013.2))
        assert e.hex() == "d0cc012a01460a37c88b01009a1f"   # C++ 测试同源向量（node_id=1）
        assert len(e) == 7 + ENV_PAYLOAD_LEN
        d = decode(e)
        assert (d["type_name"], d["node_id"], d["t"], d["h"], d["p"]) == \
            ("env", 1, 26.3, 55, 1013.2)
        hb = decode(encode(TYPE_HEARTBEAT, seq=3, node_id=1))
        assert hb["type_name"] == "heartbeat"
        ack = decode(encode(TYPE_ACK, seq=3, node_id=1))
        err = decode(encode(TYPE_ERR, seq=3, node_id=1))
        assert (ack["type_name"], err["type_name"]) == ("ack", "err")

    def test_g12_crc_std_vector(self):
        """G-12 CRC-16 MODBUS 标准向量（与 C++ 镜像同表）。"""
        assert crc16_modbus(b"123456789") == 0x4B37
