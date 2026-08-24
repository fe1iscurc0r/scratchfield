"""哨兵网格 · 串口桥 + 记忆入库测试（N-04 验收）

mock 串口数据过桥 → 入库 → 查询；坏 JSON / 未知协议降级不崩。
"""
from __future__ import annotations

import json

from mcpserver.rf_brain.sentinel_bridge import feed_line, query, status


def _mk_line(**kw) -> str:
    obj = {"src": "sentinel", "protocol": "acurite-tower", "id": 4660,
           "channel": "C", "temperature_c": 25.0, "humidity_pct": 50,
           "battery": "OK", "rssi_dbm": -85.0}
    obj.update(kw)
    return json.dumps(obj)


def test_ingest_and_query(tmp_path):
    db = tmp_path / "sentinel.db"
    # 3 条合法
    assert feed_line(_mk_line(id=1), db).status == "ok"
    assert feed_line(_mk_line(id=2, temperature_c=20.0), db).status == "ok"
    assert feed_line(_mk_line(id=3, humidity_pct=60), db).status == "ok"
    rows = query(db_path=db)
    assert len(rows) == 3
    # 最近一条在上（id=3）
    assert rows[0]["device_id"] == 3


def test_query_by_protocol_and_id(tmp_path):
    db = tmp_path / "sentinel.db"
    feed_line(_mk_line(id=10), db)
    feed_line(_mk_line(id=11, protocol="acurite-515"), db)
    r = query(protocol="acurite-tower", db_path=db)
    assert len(r) == 1
    assert r[0]["device_id"] == 10
    r2 = query(device_id=11, db_path=db)
    assert len(r2) == 1
    assert r2[0]["protocol"] == "acurite-515"


def test_bad_json_degrades(tmp_path):
    db = tmp_path / "sentinel.db"
    r = feed_line("not a json{{{", db)
    assert r.status == "failed"
    # failed 记录也落库（status 字段区分）
    rows = status(5, db)
    assert len(rows) == 1
    assert rows[0]["status"].startswith("failed")


def test_unknown_protocol_degrades(tmp_path):
    db = tmp_path / "sentinel.db"
    r = feed_line(_mk_line(protocol="not-a-real-protocol"), db)
    assert r.status == "failed"
    assert "unknown protocol" in r.reason


def test_missing_src_degrades(tmp_path):
    db = tmp_path / "sentinel.db"
    r = feed_line(json.dumps({"protocol": "acurite-tower"}), db)
    assert r.status == "failed"
    assert "missing src" in r.reason


def test_status_returns_recent(tmp_path):
    db = tmp_path / "sentinel.db"
    for i in range(5):
        feed_line(_mk_line(id=i), db)
    rows = status(3, db)
    assert len(rows) == 3
    assert rows[0]["device_id"] == 4  # 最近的是 id=4
