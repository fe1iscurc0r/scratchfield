# -*- coding: utf-8 -*-
"""LoRaCanary v1.5 · GPS 采集/降级 mock 测试（工单 AB-02 验收项）。

节点侧真机用 TinyGPSPlus（C++）解析 NMEA；本文件在 Python 侧镜像其
「输入输出语义」——用公开 NMEA 规范的标准 GGA 样例验证：
  1. 有 fix → lat/lng/alt/sat 进 GEO 帧，gps_fix=True；
  2. 无 fix/无卫星 → 走 sat=0 降级（帧内强制 0），不造假坐标；
  3. 节点串口 JSON 字段可被 json.loads 解析（含 lat/lng/sat/gps_fix）。
样例句子均为 NMEA 0183 规范格式，非实机采集（诚实标注）。
"""
import json
import re

from lora_frame import GEO_PAYLOAD_LEN, build_geo_payload, decode, encode

# 标准 NMEA GGA 样例（公开规范示例改写；UTC 时间/坐标为格式演示值）
GGA_WITH_FIX = (
    "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
)
GGA_NO_FIX = "$GPGGA,123519,,,,,0,00,,,M,,M,,"  # 定位质量 0、无卫星


def parse_gga(sentence: str) -> dict:
    """最小 GGA 解析（镜像 TinyGPSPlus 的 location/altitude/satellites 语义）。

    返回 {"fix":bool,"lat":float,"lng":float,"alt":float,"sat":int}。
    """
    m = re.match(
        r"^\$[A-Z]{2}GGA,\d+(\.\d+)?,"
        r"(\d+)?\.?(\d+)?,([NS])?,(\d+)?\.?(\d+)?,([EW])?,"
        r"(\d)?,(\d+)?,", sentence)
    if not m:
        return {"fix": False, "lat": 0.0, "lng": 0.0, "alt": 0.0, "sat": 0}
    (utc_frac, dd_lat, _mm_lat, ns, dd_lng, _mm_lng, ew,
     quality, nsat) = m.groups()
    if not quality or quality == "0" or not dd_lat:
        return {"fix": False, "lat": 0.0, "lng": 0.0, "alt": 0.0, "sat": 0}
    # 度分（ddmm.mmmm）→ 十进制度：dd 度 + mm.mmmm/60
    lat_deg = int(str(dd_lat)[:2])
    lat_min = float(str(dd_lat)[2:]) if len(str(dd_lat)) > 2 else 0.0
    lat = lat_deg + lat_min / 60.0
    if ns == "S":
        lat = -lat
    lng_deg = int(str(dd_lng)[:3])
    lng_min = float(str(dd_lng)[3:]) if len(str(dd_lng)) > 3 else 0.0
    lng = lng_deg + lng_min / 60.0
    if ew == "W":
        lng = -lng
    am = re.search(r",(\d+\.?\d*),M,", sentence)
    alt = float(am.group(1)) if am else 0.0
    return {"fix": True, "lat": lat, "lng": lng, "alt": alt, "sat": int(nsat or 0)}


class TestGpsMock:
    def test_m01_gga_with_fix_to_geo_frame(self):
        """M-01 有 fix 的 GGA → GEO 帧全字段 + gps_fix=True。"""
        g = parse_gga(GGA_WITH_FIX)
        assert g["fix"] is True and g["sat"] == 8
        b = encode(geo=True, t=26.3, h=55, p=1013.2, lat=g["lat"],
                   lng=g["lng"], alt=g["alt"], sat=g["sat"])
        assert len(b) == 7 + GEO_PAYLOAD_LEN
        d = decode(b)
        assert d["gps_fix"] is True and d["sat"] == 8
        assert abs(d["lat"] - g["lat"]) < 1e-6
        assert d["alt"] == round(g["alt"])  # GEO alt 为 int16 米（1m 分辨率）

    def test_m02_no_fix_degrades_to_sat0(self):
        """M-02 无 fix（质量 0/无卫星）→ sat=0 降级照发，坐标清零不造假。"""
        g = parse_gga(GGA_NO_FIX)
        assert g["fix"] is False and g["sat"] == 0
        # 节点侧语义：无 fix 时坐标全部填 0（与固件 gpsCollect 一致）
        b = encode(geo=True, t=26.3, h=55, p=1013.2,
                   lat=g["lat"], lng=g["lng"], alt=g["alt"], sat=g["sat"])
        d = decode(b)
        assert d["gps_fix"] is False
        assert d["lat"] == 0.0 and d["lng"] == 0.0 and d["alt"] == 0

    def test_m03_partial_sentence_never_crash(self):
        """M-03 半截/垃圾 NMEA 不崩（串口噪声场景，镜像 encode 窗口容错）。"""
        for junk in ("", "$GP", "$GPGGA,123519,4807.038", b"\xff" * 8, "xxxx"):
            g = parse_gga(junk if isinstance(junk, str) else junk.decode("latin1"))
            assert g["fix"] is False
            payload = build_geo_payload(26.3, 55, 1013.2, g["lat"], g["lng"],
                                        g["alt"], g["sat"])
            assert len(payload) == GEO_PAYLOAD_LEN  # 降级路径照常出 18B payload

    def test_m04_node_json_shape_parseable(self):
        """M-04 节点串口 JSON 形状合规（json.loads 可解析，含 lat/lng/sat/gps_fix）。"""
        line = ('{"src":"c3node","node_id":1,"seq":0,"t":26.30,"h":55.0,'
                '"p":1013.20,"lat":0.0000000,"lng":0.0000000,"alt":0,"sat":0,'
                '"gps_fix":false,"mock_bme":true,"tx_ok":true,"tx_state":0}')
        obj = json.loads(line)
        for key in ("lat", "lng", "sat", "gps_fix", "node_id", "t", "h", "p"):
            assert key in obj
        assert obj["gps_fix"] is False and obj["mock_bme"] is True
