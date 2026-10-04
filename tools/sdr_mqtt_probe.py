"""SDR/表计读数 → MQTT 总线桥最小探针（卷102 W102-04 · MIT 可参考，独立实现）。

模拟 rtlamr2mqtt 的「解码读数 → 统一 topic → MQTT 发布」语义：
表计读数与频谱读数两种记录都归一成 topic+JSON 载荷，形成统一总线出口。

源结构对照（allangood/rtlamr2mqtt，HA addon Python 版）：
- 读数解析：rtlamr2mqtt-addon/app/helpers/read_output.py:43 read_rtlamr_output、:52 get_message_for_ids
- 发现/主题规范：helpers/ha_messages.py:8 meter_discover_payload、
  :19 json_attributes_topic（{base_topic}/{meter_id}/attributes）、
  :57 state_topic（{base_topic}/{meter_id}/state）、:58 availability_topic（{base_topic}/status）
本探针不依赖 broker：发布落本地 sink 列表，topic 命名沿用「基础/对象/分层」三分法。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class MeterReading:
    """表计读数（rtlamr 解码输出行的结构化形式）。"""
    meter_id: str
    meter_type: str      # SCM / SCM+ / R900 / IDM ...
    value: float
    unit: str
    ts: str


@dataclass
class SpectrumSample:
    """频谱读数（rf_brain/频谱站感知层输出的总线化形式）。"""
    band: str
    freq_hz: float
    dbm: float
    ts: str


def parse_rtlamr_line(line: str) -> MeterReading | None:
    """解析一行 rtlamr 风格输出：`ts meter_id type value unit`，容错返回 None。"""
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        value = float(parts[3])
    except ValueError:
        return None
    return MeterReading(
        meter_id=parts[1], meter_type=parts[2], value=value, unit=parts[4], ts=parts[0],
    )


def attributes_topic(meter_id: str) -> str:
    """属性主题（对照 ha_messages.py:19 的 attributes 层级）。"""
    return f"sdr/meter/{meter_id}/attributes"


def state_topic(meter_id: str) -> str:
    """数值状态主题（对照 ha_messages.py:57 的 state 层级）。"""
    return f"sdr/meter/{meter_id}/state"


def availability_topic() -> str:
    """总线在线状态主题（对照 ha_messages.py:58 的 /status）。"""
    return "sdr/status"


class SdrMqttBridge:
    """SDR/表计 → 总线桥：读数归一化后按 topic 规范发布到 sink。"""

    def __init__(self, base_topic: str = "sdr"):
        self.base_topic = base_topic
        self.published: list[tuple[str, str]] = []

    def discover_payload(self, reading: MeterReading) -> dict[str, Any]:
        """发现载荷：表计元信息（对照 meter_discover_payload 的发现语义）。"""
        return {
            "meter_id": reading.meter_id,
            "meter_type": reading.meter_type,
            "unit": reading.unit,
            "state_topic": state_topic(reading.meter_id),
            "availability_topic": availability_topic(),
        }

    def publish_meter(self, reading: MeterReading) -> tuple[str, str]:
        """发布表计读数：state 主题 + JSON 载荷，返回 (topic, payload)。"""
        topic = state_topic(reading.meter_id)
        payload = json.dumps(
            {"meter_id": reading.meter_id, "type": reading.meter_type,
             "value": reading.value, "unit": reading.unit, "ts": reading.ts},
            ensure_ascii=False,
        )
        self.published.append((topic, payload))
        return topic, payload

    def publish_spectrum(self, sample: SpectrumSample) -> tuple[str, str]:
        """发布频谱读数：sdr/spectrum/{band}/state 主题（统一总线出口示例）。"""
        topic = f"{self.base_topic}/spectrum/{sample.band}/state"
        payload = json.dumps(
            {"band": sample.band, "freq_hz": sample.freq_hz, "dbm": sample.dbm, "ts": sample.ts},
            ensure_ascii=False,
        )
        self.published.append((topic, payload))
        return topic, payload