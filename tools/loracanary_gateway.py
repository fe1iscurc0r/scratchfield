# -*- coding: utf-8 -*-
"""LoRaCanary · S3 网关解析/上行镜像（pytest 用，与网关固件行为逐项对应）。

镜像 firmware/loracanary/loracanary_gateway_s3/loracanary_gateway_s3.ino：
  - ENV(0x01) → {"node_id","t","h","p","rssi"}（v1 兼容）；
  - GEO(0x03) → {"node_id","t","h","p","lat","lng","alt","sat","gps_fix","rssi"}
    （工单 AB-04 第 1 条示例字段逐项一致）；
  - sat=0 → gps_fix=false 照常上行（第 2 条，不丢帧）；
  - 坏帧 → 丢弃计数（v1 第 4 例）；seq 乱序/重复 → 记日志不崩不丢（v1 第 6 例）；
  - HEARTBEAT/ACK/ERR → 不产生数据上行 JSON。
"""
import json

from lora_frame import TYPE_ENV, TYPE_GEO, TYPE_HEARTBEAT, decode


class GatewayMirror:
    """收帧 → 校验 → 上行 JSON（串口/MQTT 上行文本，返回给测试断言）。"""

    def __init__(self) -> None:
        self.rx_count = 0
        self.bad_count = 0
        self.uplink_count = 0
        self.last_seq: dict[int, int] = {}
        self.log: list[str] = []

    def handle_frame(self, frame: bytes, rssi: float) -> str | None:
        """处理一帧；返回上行 JSON 文本（None = 无数据上行）。"""
        d = decode(frame)
        if d is None:
            self.bad_count += 1
            self.log.append(f'{{"src":"gw","event":"bad_frame","v":{self.bad_count}}}')
            return None

        self.rx_count += 1
        seq_log = self._seq_check(d["node_id"], d["seq"])  # 只记日志不丢帧

        if d["type"] == TYPE_ENV:
            obj = {"node_id": d["node_id"], "t": d["t"], "h": d["h"],
                   "p": d["p"], "rssi": rssi}
        elif d["type"] == TYPE_GEO:
            obj = {"node_id": d["node_id"], "t": d["t"], "h": d["h"],
                   "p": d["p"], "lat": d["lat"], "lng": d["lng"],
                   "alt": d["alt"], "sat": d["sat"], "gps_fix": d["gps_fix"],
                   "rssi": rssi}
        elif d["type"] == TYPE_HEARTBEAT:
            self.log.append(f'{{"src":"gw","event":"heartbeat","node_id":{d["node_id"]}}}')
            return None
        else:  # ACK/ERR：无数据上行
            return None

        self.uplink_count += 1
        if seq_log:
            self.log.append(seq_log)
        return json.dumps(obj, ensure_ascii=False)

    def _seq_check(self, node_id: int, seq: int) -> str | None:
        """期望 seq = 上次+1（uint8 回卷）；乱序/重复只记 event（v1 第 6 例）。"""
        last = self.last_seq.get(node_id)
        self.last_seq[node_id] = seq
        if last is not None and seq != ((last + 1) & 0xFF):
            return f'{{"src":"gw","event":"seq_gap","node_id":{node_id},' \
                   f'"last":{last},"seq":{seq}}}'
        return None
