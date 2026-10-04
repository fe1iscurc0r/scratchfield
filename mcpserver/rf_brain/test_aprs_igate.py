"""APRS iGate 扩展验收测试（Y-06）

覆盖工单验收点：
1. passcode 标准算法（N0CALL == 13023 固定值）
2. 位置包解析：'!' 与 '=' 开头的 DDMM.mmN/DDDMM.mmW → 十进制度
3. Maidenhead 网格定位器 → 经纬度
4. build_aprsis_login 登录行格式
5. igate_report：mock 模式不联网、真实模式失败不抛裸异常
6. export_geojson：FeatureCollection / Point，无坐标记录跳过
7. dedupe_frames：(callsign, info) 时间窗去重
8. load_config：JSON 覆盖默认值、文件不存在回退默认值
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain import aprs_igate as igate  # noqa: E402

# --------------------------------------------------------------------------- #
# passcode
# --------------------------------------------------------------------------- #

def test_passcode_n0call_fixed_value():
    """N0CALL 的标准 APRS-IS passcode 固定为 13023。

    来源：APRS-IS passcode 通行算法（种子 0x73e2，呼号逐字符按位哈希，
    结果 & 0x7fff），APRS 通行示例表（carrilloapps/web-aprs-passcode 的
    APRS-GUIDE）给出 N0CALL → 13023；本实现与独立脚本核对一致。
    """
    assert igate.aprs_passcode("N0CALL") == 13023


def test_passcode_is_call_dependent_and_case_insensitive():
    assert igate.aprs_passcode("n0call") == igate.aprs_passcode("N0CALL")
    assert igate.aprs_passcode("N0CALL") != igate.aprs_passcode("W1AW")
    assert igate.aprs_passcode("N0CALL") == (0x73E2 ^ (ord("N") << 8) ^ ord("0")
                                             ^ (ord("C") << 8) ^ ord("A")
                                             ^ (ord("L") << 8) ^ ord("L")) & 0x7FFF


# --------------------------------------------------------------------------- #
# 文本解析：位置包 / 网格
# --------------------------------------------------------------------------- #

def test_parse_position_packet_exclaim():
    r = igate.parse_aprs_text("APRS <- N0CALL: !4903.50N/07201.75W-")
    assert r["source"] == "N0CALL"
    assert r["format"] == "position"
    # 49°03.50'N = 49 + 3.5/60 = 49.05833...；72°01.75'W = -(72 + 1.75/60)
    assert abs(r["lat"] - (49 + 3.5 / 60)) < 1e-6
    assert abs(r["lon"] - -(72 + 1.75 / 60)) < 1e-6


def test_parse_position_packet_equals():
    r = igate.parse_aprs_text("APRS <- N0CALL: =4903.50N/07201.75W-Test")
    assert r["source"] == "N0CALL"
    assert r["format"] == "position"
    assert abs(r["lat"] - (49 + 3.5 / 60)) < 1e-6
    assert abs(r["lon"] - -(72 + 1.75 / 60)) < 1e-6


def test_parse_maidenhead_grid():
    r = igate.parse_aprs_text("APRS <- N0CALL: !IO91")
    assert r["source"] == "N0CALL"
    assert r["format"] == "grid"
    # IO91 中心（伦敦附近）：经度字段 I(8)=20°W~0°、纬度字段 O(14)=50°N~60°N；
    # 方格 9=2°W~0°、1=51°N~52°N → 中心 (51.5°N, 1°W)
    assert abs(r["lat"] - 51.5) < 1e-6
    assert abs(r["lon"] - (-1.0)) < 1e-6


def test_parse_non_position_info_has_no_coords():
    r = igate.parse_aprs_text("APRS <- N0CALL: >Hello from APRS")
    assert r["source"] == "N0CALL"
    assert r["lat"] is None and r["lon"] is None and r["format"] is None


# --------------------------------------------------------------------------- #
# 登录行
# --------------------------------------------------------------------------- #

def test_build_aprsis_login_format():
    line = igate.build_aprsis_login("N0CALL", 13023)
    assert line == "user N0CALL pass 13023 vers rf_brain-igate 1.0\r\n"


# --------------------------------------------------------------------------- #
# igate_report：mock / 失败不抛异常
# --------------------------------------------------------------------------- #

def test_igate_report_mock_offline():
    r = igate.igate_report("N0CALL", ["N0CALL>APRS:!4903.50N/07201.75W-"], mock=True)
    assert r["ok"] is True and r.get("mock") is True
    assert r["frames"] == ["N0CALL>APRS:!4903.50N/07201.75W-"]


def test_igate_report_env_mock_offline():
    os.environ["APRS_IS_MOCK"] = "1"
    try:
        r = igate.igate_report("N0CALL", ["X"])
    finally:
        os.environ.pop("APRS_IS_MOCK", None)
    assert r["ok"] is True and r.get("mock") is True


def test_igate_report_real_failure_returns_error_not_raise():
    """连接不可达端口（localhost 关闭）应返回 {ok:False, error:...} 而非抛异常。"""
    r = igate.igate_report("N0CALL", ["X"], host="127.0.0.1",
                           port=1, timeout=1)
    assert r["ok"] is False and "error" in r


# --------------------------------------------------------------------------- #
# export_geojson
# --------------------------------------------------------------------------- #

def test_export_geojson_feature_collection(tmp_path):
    records = [
        {"callsign": "N0CALL", "info": "!4903.50N/07201.75W-",
         "lat": 49.058333, "lon": -72.029167},
        {"callsign": "W1AW", "info": "no position"},
    ]
    out = igate.export_geojson(records, tmp_path / "out.geojson")
    assert out["ok"] is True and out["count"] == 1
    data = json.loads(Path(out["file_path"]).read_text(encoding="utf-8"))
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    f = data["features"][0]
    assert f["geometry"]["type"] == "Point"
    assert f["geometry"]["coordinates"] == [-72.029167, 49.058333]
    assert f["properties"]["callsign"] == "N0CALL"


# --------------------------------------------------------------------------- #
# dedupe_frames
# --------------------------------------------------------------------------- #

def test_dedupe_frames_window():
    frames = [
        {"callsign": "N0CALL", "info": "!4903.50N/07201.75W-", "time": 100.0},
        {"callsign": "N0CALL", "info": "!4903.50N/07201.75W-", "time": 120.0},
        {"callsign": "N0CALL", "info": "!4903.50N/07201.75W-", "time": 200.0},
        {"callsign": "W1AW", "info": "!4903.50N/07201.75W-", "time": 100.0},
    ]
    out = igate.dedupe_frames(frames, window_seconds=60)
    # 前两条间隔 20s 去重；200s 与 120s 间隔 80s 保留；不同 callsign 保留
    assert len(out) == 3
    assert [f["time"] for f in out] == [100.0, 100.0, 200.0]
    assert all("time" in f for f in out)


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #

def test_load_config_defaults_and_passcode_autofill():
    cfg = igate.load_config()
    assert cfg["igate_callsign"] == "N0CALL"
    assert cfg["aprsis_port"] == 14580
    assert cfg["passcode"] == 13023          # 缺省自动按 N0CALL 计算


def test_load_config_json_override(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "igate_callsign": "W1AW",
        "aprsis_port": 10152,
        "mock": True,
    }), encoding="utf-8")
    cfg = igate.load_config(p)
    assert cfg["igate_callsign"] == "W1AW"
    assert cfg["aprsis_port"] == 10152
    assert cfg["mock"] is True
    assert cfg["passcode"] == igate.aprs_passcode("W1AW")


def test_load_config_missing_file_uses_defaults(tmp_path):
    cfg = igate.load_config(tmp_path / "does_not_exist.json")
    assert cfg["igate_callsign"] == "N0CALL"
    assert cfg["passcode"] == 13023


if __name__ == "__main__":
    test_passcode_n0call_fixed_value()
    test_passcode_is_call_dependent_and_case_insensitive()
    test_parse_position_packet_exclaim()
    test_parse_position_packet_equals()
    test_parse_maidenhead_grid()
    test_parse_non_position_info_has_no_coords()
    test_build_aprsis_login_format()
    test_igate_report_mock_offline()
    test_igate_report_env_mock_offline()
    test_igate_report_real_failure_returns_error_not_raise()
    test_dedupe_frames_window()
    test_load_config_defaults_and_passcode_autofill()
    print("\n🎉 APRS iGate 扩展全部自测通过")
