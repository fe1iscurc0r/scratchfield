"""Sentinel-Link 协议 + 网关 + 占用检测 单测（卷187 验收项 7，>=12 用例）。

纯 stdlib + pytest，无硬件依赖。覆盖：
- 协议编解码往返 / CRC 正确性 / CRC 篡改检出
- 坏 JSON / 未知帧型 / 缺字段 的降级行为
- 扫描配置参数校验（合法 + 各种非法）
- 网关：去重（同 node+ts+type）/ 重放幂等 / CRC 错帧丢弃计数 / 坏行分类
- 网关：scan/env/hello 落库行数与内容
- 占用检测：达阈值发事件、只报一次、断档重开
- 占用落地：表写入 + 查询
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from mcpserver.rf_brain.sentinel_link.gateway import SentinelGateway, SqliteSink
from mcpserver.rf_brain.sentinel_link.occupation import (
    OccupationConfig,
    OccupationDetector,
    OccupationHandler,
    ensure_occupation_table,
    query_occupations,
)
from mcpserver.rf_brain.sentinel_link.protocol import (
    EnvSample,
    ScanBin,
    SentinelProtocolError,
    compute_crc32,
    decode,
    decode_frame,
    encode_frame,
    make_cmd_frame,
    make_env_frame,
    make_hello_frame,
    make_scan_frame,
    parse_scan_config,
)

# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture()
def sink(tmp_path):
    s = SqliteSink(str(tmp_path / "v187_test.db"))
    yield s
    s.close()


@pytest.fixture()
def gw(sink):
    events: list[tuple[str, dict]] = []
    g = SentinelGateway(sink, emit=lambda t, p: events.append((t, p)))
    g.events = events          # 测试侧观察点
    return g


def _bins():
    return [ScanBin(433.0, -108.2), ScanBin(434.0, -61.5, sf=9)]


# ── 1. 协议：编解码往返 ───────────────────────────────────────────────────

def test_scan_frame_roundtrip():
    line = make_scan_frame("canary-01", 1743561600.123, "1.1.0", _bins(),
                           EnvSample(temp_c=23.4, hum_pct=41, bat_mv=3980),
                           event="cad_busy")
    f = decode_frame(line)
    assert f["t"] == "scan"
    assert f["node_id"] == "canary-01"
    assert f["ts"] == 1743561600.123
    assert f["fw"] == "1.1.0"
    p = f["payload"]
    assert len(p["rssi_scan"]) == 2
    assert p["rssi_scan"][0] == {"freq_mhz": 433.0, "rssi_dbm": -108.2, "sf": 0}
    assert p["rssi_scan"][1]["sf"] == 9
    assert p["env"]["temp_c"] == 23.4
    assert p["event"] == "cad_busy"


def test_env_and_hello_frame_roundtrip():
    e = decode_frame(make_env_frame("n1", 1.0, "1.0", EnvSample(pres_hpa=1008.0)))
    assert e["t"] == "env" and e["payload"]["env"]["pres_hpa"] == 1008.0
    h = decode_frame(make_hello_frame("n1", 1.0, "1.0", {"has_env": True}))
    assert h["t"] == "hello" and h["payload"]["caps"]["has_env"] is True


def test_cmd_frame_roundtrip():
    line = make_cmd_frame("gw", 2.0, "scan_config",
                          {"freq_range": [433.0, 434.7], "dwell_ms": 120},
                          cmd_id="c-1")
    f = decode_frame(line)
    assert f["t"] == "cmd"
    assert f["payload"]["cmd"] == "scan_config"
    assert f["payload"]["dwell_ms"] == 120
    assert f["payload"]["cmd_id"] == "c-1"


# ── 2. 协议：CRC ─────────────────────────────────────────────────────────

def test_crc_deterministic_and_key_order_insensitive():
    a = compute_crc32({"x": 1, "y": [1, 2, 3]})
    b = compute_crc32({"y": [1, 2, 3], "x": 1})      # 键序不同
    assert a == b and len(a) == 8


def test_crc_tamper_detected():
    line = make_scan_frame("n1", 1.0, "1.0", _bins())
    tampered = line.replace("-108.2", "-98.2")       # 改 payload 不改 crc
    frame, err = decode(tampered)
    assert frame is None and "CRC" in err


def test_missing_crc_rejected():
    line = make_scan_frame("n1", 1.0, "1.0", _bins(), with_crc=False)
    frame, err = decode(line)
    assert frame is None and "crc32" in err


# ── 3. 协议：降级与 fail-fast ────────────────────────────────────────────

@pytest.mark.parametrize("bad,keyword", [
    ("", "空帧"),
    ("not json at all", "坏 JSON"),
    ('["a","b"]', "JSON 对象"),
    ('{"t":"nope","node_id":"n","ts":1,"payload":{}}', "未知帧类型"),
    ('{"t":"scan","ts":1,"payload":{}}', "node_id"),
    ('{"t":"scan","node_id":"n","payload":{}}', "ts"),
])
def test_decode_degradation(bad, keyword):
    frame, err = decode(bad)
    assert frame is None
    assert keyword in err


def test_encode_rejects_bad_type_and_empty_node():
    with pytest.raises(SentinelProtocolError):
        encode_frame("bogus", "n", 1.0, "1.0", {})
    with pytest.raises(SentinelProtocolError):
        encode_frame("scan", "  ", 1.0, "1.0", {})


# ── 4. 扫描配置校验 ──────────────────────────────────────────────────────

def test_parse_scan_config_ok_and_defaults():
    cfg = parse_scan_config({})
    assert cfg["freq_range"] == [433.0, 434.7]
    assert cfg["dwell_ms"] == 120
    assert cfg["sf_set"] == [7, 9, 10, 12]
    cfg2 = parse_scan_config({"freq_range": [433.0, 434.0], "dwell_ms": 50,
                              "sf_set": [12, 7, 9], "step_khz": 125})
    assert cfg2["sf_set"] == [7, 9, 12]              # 去重且升序
    assert cfg2["step_khz"] == 125


@pytest.mark.parametrize("payload", [
    {"freq_range": [434.0, 433.0]},                  # 倒置
    {"freq_range": [100.0, 200.0]},                  # 越界
    {"freq_range": [433.0]},                         # 长度错
    {"freq_range": []},                              # 空数组
    {"dwell_ms": 1},                                 # 太小
    {"dwell_ms": 99999},                             # 太大
    {"sf_set": []},                                  # 空
    {"sf_set": [13]},                                # sf 越界
    {"step_khz": 0},                                 # 步进非法
])
def test_parse_scan_config_invalid(payload):
    with pytest.raises(SentinelProtocolError):
        parse_scan_config(payload)


# ── 5. 网关：解析 / 去重 / 落库 ──────────────────────────────────────────

def test_gateway_scan_lands_rows(gw, sink):
    line = make_scan_frame("n1", 100.0, "1.0", _bins(),
                           EnvSample(temp_c=20.0, bat_mv=3900))
    assert gw.consume_line(line, now=100.0) is not None
    s = gw.stats
    assert s.ok == 1 and s.scans_rows == 2 and s.env_rows == 1
    rows = sink.query_spectrum()
    assert len(rows) == 2
    assert {r["freq_mhz"] for r in rows} == {433.0, 434.0}
    env = sink.query_env(hours=1e9)
    assert len(env) == 1 and env[0]["temp_c"] == 20.0


def test_gateway_dedup_same_node_ts_type(gw, sink):
    line = make_scan_frame("n1", 100.0, "1.0", _bins())
    assert gw.consume_line(line, now=100.0) is not None
    assert gw.consume_line(line, now=100.0) is None      # 重复 → 丢弃
    assert gw.stats.duplicate == 1
    assert gw.stats.scans_rows == 2                      # 未重复入库
    assert len(sink.query_spectrum()) == 2


def test_gateway_replay_idempotent(sink):
    line = make_scan_frame("n1", 100.0, "1.0", _bins())
    g1 = SentinelGateway(sink, emit=lambda t, p: None)
    g1.consume_line(line, now=100.0)
    g2 = SentinelGateway(sink, emit=lambda t, p: None)   # 新实例（内存窗口空）
    g2.consume_line(line, now=100.0)                     # 表唯一索引兜底
    assert g2.stats.ok == 0
    assert len(sink.query_spectrum()) == 2


def test_gateway_counts_bad_frames(gw):
    gw.consume_line("{broken json", now=1.0)                       # bad json
    good = make_scan_frame("n1", 2.0, "1.0", _bins())
    gw.consume_line(good.replace("-108.2", "-99.9"), now=2.0)      # crc 错
    gw.consume_line('{"t":"zzz","node_id":"n","ts":3,"payload":{}}', now=3.0)
    s = gw.stats
    assert s.received == 3 and s.ok == 0
    assert s.dropped_bad_json == 1
    assert s.dropped_crc == 1
    assert s.dropped_unknown_type == 1


def test_gateway_env_and_hello(gw, sink):
    gw.consume_line(make_hello_frame("n1", 10.0, "1.1", {"has_env": True}), now=10.0)
    gw.consume_line(make_env_frame("n1", 11.0, "1.1", EnvSample(hum_pct=44.0)), now=11.0)
    assert gw.stats.hello == 1 and gw.stats.env_rows == 1
    assert len(sink.query_env(hours=1e9)) == 1
    assert len(sink.list_nodes(now=11.0)) == 1
    assert sink.list_nodes(now=11.0)[0]["online"] is True
    assert sink.list_nodes(now=1000.0)[0]["online"] is False   # >60s 离线


def test_gateway_emits_events(gw):
    gw.consume_line(make_hello_frame("n1", 1.0, "1.0"), now=1.0)
    gw.consume_line(make_scan_frame("n1", 2.0, "1.0", _bins()), now=2.0)
    topics = [t for t, _ in gw.events]
    assert "lumo.sentinel.node_online" in topics
    assert "lumo.sentinel.scan" in topics
    scan_ev = [p for t, p in gw.events if t == "lumo.sentinel.scan"][0]
    assert scan_ev["node_id"] == "n1" and scan_ev["n_bins"] == 2
    assert scan_ev["peak_dbm"] == -61.5


# ── 6. 占用检测 ──────────────────────────────────────────────────────────

def test_occupation_reports_after_hold():
    det = OccupationDetector(OccupationConfig(hold_s=5.0, high_threshold_dbm=-85.0))
    bins = [ScanBin(434.0, -60.0)]
    assert det.feed("n1", 0.0, bins) == []
    assert det.feed("n1", 3.0, bins) == []
    ev = det.feed("n1", 6.0, bins)                  # 超过 5s → 报
    assert len(ev) == 1
    assert ev[0]["freq_mhz"] == 434.0
    assert ev[0]["duration_s"] == 6.0
    assert ev[0]["n_samples"] == 3
    assert det.feed("n1", 7.0, bins) == []          # 同段只报一次


def test_occupation_below_threshold_ignored():
    det = OccupationDetector(OccupationConfig(hold_s=1.0, high_threshold_dbm=-85.0))
    bins = [ScanBin(434.0, -95.0)]                  # 低于阈值
    for t in range(0, 5):
        assert det.feed("n1", float(t), bins) == []


def test_occupation_gap_resets_track():
    # max_gap_s=2.0 表示"相邻样本间隔 >2s 即视为断档"；采样间隔保持 1s。
    det = OccupationDetector(OccupationConfig(hold_s=5.0, max_gap_s=2.0))
    bins = [ScanBin(434.0, -60.0)]
    det.feed("n1", 0.0, bins)
    det.feed("n1", 1.0, bins)
    # 断档 10s（> max_gap）→ 结算旧轨（仅 1s，未达 5s 不报）、开新轨
    assert det.feed("n1", 11.0, bins) == []
    assert len(det.active()) == 1
    # 新轨按 1s 间隔重新计时；hold_s=5.0 且判定为 >=，故 11→16（5s）即报出
    for t in (12.0, 13.0, 14.0, 15.0):
        assert det.feed("n1", t, bins) == []
    ev = det.feed("n1", 16.0, bins)
    assert len(ev) == 1
    assert ev[0]["start_ts"] == 11.0 and ev[0]["duration_s"] == 5.0


def test_occupation_handler_lands_record(tmp_path):
    db = str(tmp_path / "occ.db")
    h = OccupationHandler(db)
    ev = {"node_id": "n1", "freq_mhz": 434.0, "start_ts": 100.0, "end_ts": 170.0,
          "duration_s": 70.0, "peak_dbm": -61.0, "mean_dbm": -66.0, "n_samples": 70}
    h.handle(ev)
    assert h.stats()["recorded"] == 1
    rows = query_occupations(hours=1e9, db_path=db)
    assert len(rows) == 1
    assert rows[0]["node_id"] == "n1" and rows[0]["duration_s"] == 70.0


def test_occupation_handler_survives_bad_event(tmp_path):
    h = OccupationHandler(str(tmp_path / "occ2.db"))
    h.handle("not-a-dict")          # 字符串（非法 JSON 结构）
    h.handle({"no_node_id": 1})
    assert h.stats()["errors"] == 2
    assert h.recorded == 0


def test_gateway_triggers_occupation_event(tmp_path):
    """端到端：持续高 RSSI → 网关发 occupation 事件 + 落库。"""
    db = str(tmp_path / "occ_e2e.db")
    sink = SqliteSink(db)
    events: list[tuple[str, dict]] = []
    gw = SentinelGateway(sink, emit=lambda t, p: events.append((t, p)))
    # 缩短阈值以适配短测
    from mcpserver.rf_brain.sentinel_link import occupation as occ_mod
    occ_mod.reset_detector(OccupationConfig(hold_s=5.0, high_threshold_dbm=-85.0))
    gw._occupation = None           # 强制重新取单例

    hot = [ScanBin(434.0, -60.0)]
    for t in (100.0, 103.0, 106.0):
        gw.consume_line(make_scan_frame("n1", t, "1.0", hot), now=t)
    occ_events = [p for tp, p in events if tp == "lumo.sentinel.occupation"]
    assert len(occ_events) == 1
    assert gw.stats.occupation_events == 1
    rows = query_occupations(hours=1e9, db_path=db)
    # 网关只发事件，落库由 handler 负责 → 这里表应为空
    assert rows == []
    # 挂 handler 后 replay 一次事件能落库
    h = OccupationHandler(db)
    h.handle(occ_events[0])
    assert len(query_occupations(hours=1e9, db_path=db)) == 1
    sink.close()
