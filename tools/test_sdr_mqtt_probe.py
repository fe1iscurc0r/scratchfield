"""sdr_mqtt_probe 验收硬线（卷102 W102-04）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sdr_mqtt_probe import (  # noqa: E402
    MeterReading,
    SdrMqttBridge,
    SpectrumSample,
    attributes_topic,
    availability_topic,
    parse_rtlamr_line,
    state_topic,
)


def test_parse_rtlamr_line():
    """读数行解析：字段齐全解析成功，残缺/坏数值返回 None。"""
    r = parse_rtlamr_line("2026-09-11T12:00:00 12345678 SCM 42.31 kWh")
    assert r is not None
    assert r.meter_id == "12345678" and r.meter_type == "SCM"
    assert r.value == 42.31 and r.unit == "kWh"
    assert parse_rtlamr_line("2026-09-11T12:00:00 12345678 SCM") is None
    assert parse_rtlamr_line("t 1 T x v") is None  # value 非数值


def test_meter_topic_spec():
    """topic 三分法：state/attributes/status 与发现载荷互相引用一致。"""
    r = MeterReading("12345678", "SCM", 42.31, "kWh", "t0")
    assert state_topic(r.meter_id) == "sdr/meter/12345678/state"
    assert attributes_topic(r.meter_id) == "sdr/meter/12345678/attributes"
    assert availability_topic() == "sdr/status"
    bridge = SdrMqttBridge()
    disc = bridge.discover_payload(r)
    assert disc["state_topic"] == state_topic(r.meter_id)
    assert disc["availability_topic"] == availability_topic()
    assert disc["unit"] == "kWh"


def test_publish_meter_and_spectrum():
    """表计与频谱两类记录均归一为 topic+JSON，载荷字段齐。"""
    bridge = SdrMqttBridge()
    t1, p1 = bridge.publish_meter(MeterReading("m1", "SCM", 7.4, "kWh", "t1"))
    assert t1 == "sdr/meter/m1/state"
    d1 = json.loads(p1)
    assert d1["value"] == 7.4 and d1["meter_id"] == "m1"

    t2, p2 = bridge.publish_spectrum(SpectrumSample("20m", 14.074e6, -103.5, "t2"))
    assert t2 == "sdr/spectrum/20m/state"
    d2 = json.loads(p2)
    assert d2["freq_hz"] == 14.074e6 and d2["dbm"] == -103.5

    assert len(bridge.published) == 2