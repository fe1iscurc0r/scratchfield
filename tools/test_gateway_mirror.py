# -*- coding: utf-8 -*-
"""LoRaCanary v1.5 · 网关镜像 + v1 十二例补齐 pytest（工单 AB-04）。

用例编号对照（v1 SPEC 第七节 12 例 → V-xx；v1.5 新增 → G/M/S 系列，见另两个测试文件）：
  v1-1 帧编码往返        → G-01/G-11
  v1-2 帧类型分派        → G-11
  v1-3 坏帧 magic 错     → G-09
  v1-4 CRC 错误          → G-09（网关侧 V-08）
  v1-5 超长 payload 拒绝 → V-01
  v1-6 seq 乱序/重复     → V-02
  v1-7 重传 ≤2 次放弃    → V-03
  v1-8 采集 mock 标注    → V-04（节点侧另有 M-04 JSON 形状）
  v1-9 地址探测          → V-05
  v1-10 网关 JSON 校验   → V-06/V-07
  v1-11 OLED mock        → v1.5 C3 轻量节点无 OLED，N/A（诚实标注，见 README）
  v1-12 RadioLib 环回    → 需双模块实物，真机项留用户（README 步骤）
"""
import json
from pathlib import Path

import pytest
from lora_frame import (
    MAX_PAYLOAD,
    TYPE_HEARTBEAT,
    decode,
    encode,
    encode_geo,
)
from loracanary_gateway import GatewayMirror
from loracanary_node import Bme280Probe, TxRetry, sensor_sample

REPO = Path(__file__).resolve().parents[1]
GOOD_GEO = encode_geo(node_id=1, seq=1, t=26.3, h=55, p=1013.2,
                      lat=39.9042, lng=116.4074, alt=52, sat=8)


class TestMirrorSync:
    def test_v10_frame_mirror_copies_identical(self):
        """V-10 镜像副本守卫：节点/网关草图内的 loracanary_frame 与正本逐字节一致。"""
        canonical_h = REPO / "firmware/loracanary/loracanary_frame.h"
        canonical_c = REPO / "firmware/loracanary/loracanary_frame.cpp"
        for base in ("loracanary_c3_node", "loracanary_gateway_s3"):
            sketch = REPO / "firmware/loracanary" / base / "loracanary_frame.h"
            cpp = REPO / "firmware/loracanary" / base / "loracanary_frame.cpp"
            assert sketch.read_bytes() == canonical_h.read_bytes(), \
                f"{base} 的 loracanary_frame.h 与正本漂移——同步后再改"
            assert cpp.read_bytes() == canonical_c.read_bytes(), \
                f"{base} 的 loracanary_frame.cpp 与正本漂移——同步后再改"


class TestGatewayUplink:
    def test_v06_geo_uplink_json_shape(self):
        """V-06 GEO 上行 JSON：工单 AB-04 示例字段逐项一致 + json.loads 合规。"""
        gw = GatewayMirror()
        out = gw.handle_frame(GOOD_GEO, rssi=-87.0)
        obj = json.loads(out)  # 必须可解析
        assert obj["node_id"] == 1 and obj["t"] == 26.3
        assert obj["h"] == 55.0 and obj["p"] == 1013.2
        assert abs(obj["lat"] - 39.9042) < 1e-6
        assert abs(obj["lng"] - 116.4074) < 1e-6
        assert obj["alt"] == 52 and obj["sat"] == 8
        assert obj["gps_fix"] is True and obj["rssi"] == -87.0
        # 字段集合恰好等于示例（不多不少，防上游乱加字段）
        assert set(obj) == {"node_id", "t", "h", "p", "lat", "lng", "alt",
                            "sat", "gps_fix", "rssi"}

    def test_v07_no_fix_still_uplinked(self):
        """V-07 sat=0 → gps_fix=false 照常上行，不丢帧（工单 AB-04 第 2 条）。"""
        gw = GatewayMirror()
        frame = encode_geo(node_id=2, seq=5, t=26.3, h=55, p=1013.2,
                           lat=0.0, lng=0.0, alt=0, sat=0)
        out = gw.handle_frame(frame, rssi=-95.0)
        obj = json.loads(out)
        assert obj["gps_fix"] is False and obj["sat"] == 0
        assert obj["lat"] == 0.0 and obj["lng"] == 0.0 and obj["alt"] == 0
        assert gw.uplink_count == 1  # 降级帧也计数上行

    def test_v01_env_uplink_v1_compat(self):
        """V-01(v1-10) ENV 上行：v1 字段 {node_id,t,h,p,rssi}，v1.5 未破坏。"""
        gw = GatewayMirror()
        frame = encode(env=3, seq=9, t=26.3, h=55, p=1013.2)
        obj = json.loads(gw.handle_frame(frame, rssi=-80.0))
        assert obj == {"node_id": 3, "t": 26.3, "h": 55.0, "p": 1013.2,
                       "rssi": -80.0}

    def test_v08_bad_frame_dropped_counted(self):
        """V-08(v1-4) 坏帧：网关丢弃 + 计数 + 事件日志，不上行。"""
        gw = GatewayMirror()
        bad = bytearray(GOOD_GEO)
        bad[-2] ^= 0xFF  # 破坏 CRC
        assert gw.handle_frame(bytes(bad), rssi=-80.0) is None
        assert gw.handle_frame(b"\x00" * 25, rssi=-80.0) is None
        assert gw.bad_count == 2 and gw.uplink_count == 0
        assert any("bad_frame" in line for line in gw.log)

    def test_v02_out_of_order_and_duplicate_seq(self):
        """V-02(v1-6) seq 乱序/重复：记 seq_gap 日志，帧照常上行不崩。"""
        gw = GatewayMirror()
        seqs = [1, 3, 3, 2, 200, 200]  # 乱序 + 重复 + uint8 回卷乱序
        for i, sq in enumerate(seqs):
            frame = encode_geo(node_id=1, seq=sq, t=26.3, h=55, p=1013.2,
                               lat=39.9042, lng=116.4074, alt=52, sat=8)
            out = gw.handle_frame(frame, rssi=-80.0)
            assert out is not None  # 全部照常上行
            json.loads(out)
        assert gw.uplink_count == len(seqs)
        gaps = [line for line in gw.log if "seq_gap" in line]
        assert len(gaps) >= 3  # 1→3 / 3→3 / 3→2 至少三次 gap

    def test_heartbeat_no_data_uplink(self):
        """V-09 HEARTBEAT/ACK/ERR：心跳记事件，无数据上行 JSON。"""
        gw = GatewayMirror()
        assert gw.handle_frame(encode(TYPE_HEARTBEAT, seq=2, node_id=1),
                               rssi=-80.0) is None
        assert gw.rx_count == 1 and gw.uplink_count == 0


class TestV1NodeCases:
    def test_v01_oversize_payload_rejected(self):
        """V-01(v1-5) 超长 payload：encode 抛 ValueError，伪造帧 decode 拒绝。"""
        with pytest.raises(ValueError):
            encode(TYPE_HEARTBEAT, seq=0, node_id=1,
                   payload=b"\x00" * (MAX_PAYLOAD + 1))  # 121B > 120B
        fake = (b"\xd0\xcc" + b"\x02" + b"\x00\x01"
                + b"\x00" * (MAX_PAYLOAD + 1) + b"\x00\x00")  # 超长整帧
        assert decode(fake) is None

    def test_v03_retry_gives_up_after_two(self):
        """V-03(v1-7) 重传：无 ACK 重发 ≤2 次后放弃（共 3 次发送），不阻塞。"""
        tx = TxRetry()
        tx.send_once()                  # 首次
        assert tx.should_retry is True
        tx.send_once()                  # 重试 1
        assert tx.should_retry is True
        tx.send_once()                  # 重试 2（上限）
        assert tx.should_retry is False
        assert tx.gave_up is True       # 放弃，等下一周期

        tx_ok = TxRetry()               # 收到 ACK 即停
        tx_ok.send_once()
        tx_ok.on_ack()
        assert tx_ok.should_retry is False and tx_ok.gave_up is False

    def test_v04_sensor_mock_marked(self):
        """V-04(v1-8) 采集 mock：无传感器 → MOCK 采样 + mock_bme=True 显式标注。"""
        online = sensor_sample(True, {"t": 26.3, "h": 55.0, "p": 1013.2})
        assert online["mock_bme"] is False and online["t"] == 26.3
        offline = sensor_sample(False)
        assert offline["mock_bme"] is True
        assert offline == {"t": 25.0, "h": 55.0, "p": 1013.2, "mock_bme": True}

    def test_v05_bme_addr_probe_order(self):
        """V-05(v1-9) 地址探测：0x76 优先，不在则 0x77，全不在 MOCK。"""
        p1 = Bme280Probe(present_addrs=(0x76,))
        assert p1.probe() is True and p1.addr == 0x76 and p1.mock is False
        p2 = Bme280Probe(present_addrs=(0x77,))
        assert p2.probe() is True and p2.addr == 0x77
        assert p2.tried == [0x76, 0x77]  # 先试 0x76 失败再 0x77（探测顺序固化）
        p3 = Bme280Probe(present_addrs=())
        assert p3.probe() is False and p3.mock is True
