"""B-08 · HAM 无线电接入（卷132）。

把业余无线电记录（APRS 报文 / ADIF 日志 / 演示站点）统一成 `Station` 模型，
供 `/api/ham/stations` 返回 GeoJSON，前端 F-01 用它渲染「HAM 无线电站」图层。

> 原工单希望复用 `mcpserver/rf_brain/aprs_igate.py`（Maidenhead 转换 / APRS-IS
> 登录 / GeoJSON 导出 / 去重）。本 checkout 中该模块不存在，这里改为自包含实现：
> Maidenhead 转换直接复用本包 `coords.maidenhead_to_lonlat`；APRS / ADIF 用轻量
> 解析。若日后补回 `aprs_igate.py`，可在 `load_stations()` 里优先调用其
> `to_geojson_features()`。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from .coords import maidenhead_to_lonlat
from .models import Station

logger = logging.getLogger("sitaware.ham")

# 演示用业余无线电台（WGS84）。无真实日志 / 网络时返回，保证图层非空。
_DEMO_STATIONS: list[Station] = [
    Station(call="BG7ZZZ", lng=113.2644, lat=23.1291, freq_mhz=14.070, mode="FT8",
            grid="OL23oc", source="adif", comment="广州主控"),
    Station(call="BH7ABC", lng=113.3612, lat=23.1247, freq_mhz=7.074, mode="FT8",
            grid="OL23od", source="adif", comment="天河中继"),
    Station(call="BI7DEF", lng=113.3768, lat=23.1029, freq_mhz=145.500, mode="FM",
            grid="OL23oc", source="aprs", comment="琶洲 APRS"),
    Station(call="BG7GHI", lng=114.0579, lat=22.5431, freq_mhz=433.000, mode="DMR",
            grid="OL63pl", source="adif", comment="深圳节点"),
    Station(call="BA7JKL", lng=113.2730, lat=23.1573, freq_mhz=21.074, mode="FT8",
            grid="OL23oc", source="adif", comment="白云"),
]


# --------------------------------------------------------------------------- #
# APRS 位置报文（极简解析，覆盖 `CALL>...:!LAT/LON...` 形态）
# --------------------------------------------------------------------------- #

_APRS_POS = re.compile(
    r"^(?P<call>[A-Z0-9]{4,})\b.*?[:!](?P<lat>\d{4}\.\d{2}[NS])"
    r"[/\\](?P<lon>\d{5}\.\d{2}[EW])"
)


def _aprs_coord(lat_s: str, lon_s: str) -> tuple[float, float]:
    """APRS 度分格式 → 十进制度（WGS84）。"""
    lat = int(lat_s[:2]) + float(lat_s[2:4] + "." + lat_s[5:7]) / 60.0
    if lat_s.endswith("S"):
        lat = -lat
    lon = int(lon_s[:3]) + float(lon_s[3:5] + "." + lon_s[6:8]) / 60.0
    if lon_s.endswith("W"):
        lon = -lon
    return round(lon, 6), round(lat, 6)


def aprs_to_station(packet: str) -> Station | None:
    """APRS 位置报文 → Station；无法解析返回 None。"""
    m = _APRS_POS.search(packet or "")
    if not m:
        return None
    try:
        lng, lat = _aprs_coord(m.group("lat"), m.group("lon"))
    except (ValueError, IndexError):
        return None
    return Station(call=m.group("call"), lng=lng, lat=lat,
                   source="aprs", comment=packet.strip()[:60])


# --------------------------------------------------------------------------- #
# ADIF 日志（极简：按 <FIELD:len>value; 提取 CALL/LAT/LON/GRID/MODE/FREQ/BAND）
# --------------------------------------------------------------------------- #

_ADIF_FIELD = re.compile(r"<(?P<name>[A-Z_]+):(?P<len>\d+)>(?P<val>[^<]*)")


def _parse_adif_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ADIF_FIELD.finditer(text or ""):
        out[m.group("name")] = m.group("val")[: int(m.group("len"))]
    return out


def adif_to_station(record: str) -> Station | None:
    """单条 ADIF 记录 → Station；缺坐标且缺网格则 None。"""
    f = _parse_adif_fields(record)
    call = f.get("CALL")
    if not call:
        return None
    lng = lat = None
    if f.get("LAT") and f.get("LON"):
        try:
            lat = float(f["LAT"]); lng = float(f["LON"])
        except ValueError:
            lng = lat = None
    if lng is None and f.get("GRID"):
        try:
            lng, lat = maidenhead_to_lonlat(f["GRID"])
        except ValueError:
            return None
    if lng is None or lat is None:
        return None
    freq = None
    if f.get("FREQ"):
        try:
            freq = float(f["FREQ"])
        except ValueError:
            freq = None
    return Station(call=call, lng=round(lng, 6), lat=round(lat, 6),
                   freq_mhz=freq, mode=f.get("MODE"),
                   grid=f.get("GRID"), source="adif", comment=f.get("COMMENT"))


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #

def load_stations(adif_path: str | None = None,
                  aprs_packets: Iterable[str] | None = None) -> list[Station]:
    """聚合 HAM 站点：ADIF 文件 → APRS 报文 → 演示兜底。

    任一输入源都能独立工作；都没有时返回演示站点，保证 /api/ham/stations 不空。
    """
    stations: list[Station] = []

    if adif_path and Path(adif_path).exists():
        try:
            text = Path(adif_path).read_text(encoding="utf-8", errors="ignore")
            for rec in text.split("<EOR>"):
                s = adif_to_station(rec)
                if s:
                    stations.append(s)
        except OSError as exc:
            logger.warning("读取 ADIF 失败：%s", exc)

    if aprs_packets:
        for pkt in aprs_packets:
            s = aprs_to_station(pkt)
            if s:
                stations.append(s)

    if not stations:
        stations = list(_DEMO_STATIONS)
    return stations


__all__ = ["load_stations", "aprs_to_station", "adif_to_station"]
