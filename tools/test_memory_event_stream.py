"""memory_event_stream 测试（P2-1 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from memory_event_stream import EventMemory


def test_ingest_builds_index():
    m = EventMemory()
    m.ingest("e1", "Alice configured the ESP32 radio at 433MHz.")
    assert len(m.events) == 1
    assert len(m.entity_index) > 0


def test_recall_returns_related():
    m = EventMemory()
    m.ingest("e1", "Alice configured the ESP32 radio.")
    m.ingest("e2", "Bob measured the SDR noise floor.")
    results = m.recall("ESP32")
    assert results and results[0]["id"] == "e1"


def test_recall_empty_for_unknown():
    m = EventMemory()
    m.ingest("e1", "Alice configured the ESP32.")
    assert m.recall("QuantumEntanglement") == []
