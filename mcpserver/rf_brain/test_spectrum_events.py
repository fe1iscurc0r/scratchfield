"""R01 验收测试：事件驱动频谱缓存（spectrum_events）。

覆盖：
  1. SpectrumEvent schema：as_dict/from_ndjson 往返 + 非法事件类型拒绝
  2. EventRingBuffer：固定预算（最旧淘汰）+ recent(n)
  3. 检测器：能量跳变 → appear 事件
  4. 检测器：能量跌落 → vanish 事件（含存活时长）
  5. 检测器：快速出现+消失+高能量 → burst 事件
  6. 缓存：current_interferers 返回当前活跃源
  7. 缓存：recent_events 返回最近 N 条
  8. NDJSON：单行 JSON 且含事件类型字段

运行：python -m pytest mcpserver/rf_brain/test_spectrum_events.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from . import spectrum_events as se


def _freqs(n: int = 201) -> np.ndarray:
    return np.linspace(-1000.0, 1000.0, n)


def _floor(n: int = 201, db: float = -100.0) -> np.ndarray:
    return np.full(n, db)


def test_event_schema_roundtrip():
    ev = se.SpectrumEvent(1.5, 100.0, "appear", duration_s=0.0,
                          strength_dbm=-20.0, bandwidth_hz=50.0)
    d = ev.as_dict()
    assert d["src"] == "rf_brain"
    assert d["event_type"] == "appear"
    ev2 = se.SpectrumEvent.from_ndjson(ev.to_ndjson())
    assert ev2 == ev
    # 非法事件类型拒绝
    with pytest.raises(ValueError):
        se.SpectrumEvent(0.0, 0.0, "bogus")


def test_ring_buffer_budget():
    buf = se.EventRingBuffer(capacity=3)
    for i in range(5):
        buf.push(se.SpectrumEvent(float(i), float(i), "appear"))
    assert len(buf) == 3
    assert buf.all()[0].timestamp == 2.0        # 最旧两条已淘汰
    assert buf.recent(2)[-1].timestamp == 4.0
    # 非法容量拒绝
    with pytest.raises(ValueError):
        se.EventRingBuffer(capacity=0)


def test_detect_appear():
    det = se.SpectrumEventDetector()
    freqs = _freqs()
    assert det.process_frame(freqs, _floor(), timestamp=0.0) == []  # 纯噪声无事件
    db = _floor()
    db[100] = 0.0
    evs = det.process_frame(freqs, db, timestamp=1.0)
    assert len(evs) == 1
    assert evs[0].event_type == "appear"
    assert evs[0].freq_hz == pytest.approx(freqs[100])
    assert evs[0].strength_dbm == pytest.approx(0.0)


def test_detect_vanish():
    det = se.SpectrumEventDetector()
    freqs = _freqs()
    db = _floor()
    db[100] = 0.0
    det.process_frame(freqs, db, timestamp=1.0)   # appear
    assert det.process_frame(freqs, db, timestamp=2.0) == []  # 持续活跃无新事件
    evs = det.process_frame(freqs, _floor(), timestamp=3.0)
    assert len(evs) == 1
    assert evs[0].event_type == "vanish"
    assert evs[0].duration_s == pytest.approx(2.0)  # 3 - 1


def test_detect_burst():
    det = se.SpectrumEventDetector(burst_max_duration_s=2.0, burst_min_strength_db=-30.0)
    freqs = _freqs()
    db = _floor()
    db[100] = 0.0  # 高能量
    det.process_frame(freqs, db, timestamp=0.0)     # appear
    evs = det.process_frame(freqs, _floor(), timestamp=0.5)  # 极速消失
    assert len(evs) == 1
    assert evs[0].event_type == "burst"
    assert evs[0].duration_s == pytest.approx(0.5)


def test_cache_current_interferers():
    cache = se.SpectrumEventCache()
    freqs = _freqs()
    db = _floor()
    db[100] = 0.0
    cache.ingest_frame(freqs, db, timestamp=0.0)
    inter = cache.current_interferers(now=0.1)
    assert len(inter) == 1
    assert inter[0].event_type == "interferer"
    assert inter[0].freq_hz == pytest.approx(freqs[100])
    assert inter[0].duration_s == pytest.approx(0.1)


def test_cache_recent_events():
    cache = se.SpectrumEventCache()
    freqs = _freqs()
    db = _floor()
    db[100] = 0.0
    cache.ingest_frame(freqs, db, timestamp=0.0)   # appear
    cache.ingest_frame(freqs, _floor(), timestamp=1.0)  # vanish
    evs = cache.recent_events(10)
    types = {e.event_type for e in evs}
    assert "appear" in types and "vanish" in types


def test_ndjson_output_format():
    ev = se.SpectrumEvent(1.0, 250.0, "appear", strength_dbm=-10.0, bandwidth_hz=10.0)
    line = ev.to_ndjson()
    assert line.endswith("\n")
    obj = json.loads(line)
    for key in ("src", "event_type", "timestamp", "freq_hz",
                "duration_s", "strength_dbm", "bandwidth_hz"):
        assert key in obj, f"缺少字段 {key}"
