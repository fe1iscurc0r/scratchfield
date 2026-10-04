"""APRS iGate 扩展（Y-06 · 解码 → APRS-IS 上报 → GeoJSON 导出 → 去重 → 配置模板化）

数据链：AFSK1200 解码文本 → 解析 source/info（位置包 / Maidenhead 网格）
       → APRS-IS 裸 socket 上报（可 mock）→ 本地 GeoJSON FeatureCollection 导出
       → (callsign, info) 滑动窗口去重 → JSON 配置覆盖默认值。

解码复用 decoders/aprs 的 decode_afsk1200（禁止重写），本模块只消费其返回的
``"{dest} <- {src}: {info}"`` 文本，不触碰 AX.25 帧 / CRC / NRZI 底层。

依赖：仅 numpy + 标准库（socket / json / pathlib / os / re / time）。
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
from pathlib import Path

import numpy as np

from .decoders import aprs as _aprs

# --------------------------------------------------------------------------- #
# 默认配置模板
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG: dict = {
    "igate_callsign": "N0CALL",       # 本 igate 呼号
    "passcode": None,                 # None = 按 igate_callsign 自动计算
    "aprsis_host": "localhost",       # APRS-IS 服务器
    "aprsis_port": 14580,             # APRS-IS 端口
    "mock": False,                    # True 时不联网，仅本地回显
    "geojson_path": "aprs_igate.geojson",   # 本地 GeoJSON 导出路径
    "dedupe_window_seconds": 60,      # 去重滑动窗口（秒）
}

# --------------------------------------------------------------------------- #
# APRS 文本解析（消费 decode_afsk1200 的返回文本）
# --------------------------------------------------------------------------- #

# 未压缩位置包：!DDMM.mmN/DDDMM.mmW 或 =DDMM.mmN/DDDMM.mmW（可带符号/注释）
_POSITION_RE = re.compile(
    r"(?P<lat>\d{2,4}\.\d{2,4}[NS])[/\\](?P<lon>\d{2,5}\.\d{2,4}[EW])"
)
# Maidenhead 网格定位器：2/4/6/8 位，成对出现（字段 AA-XX，方格 00-99）
_GRID_RE = re.compile(r"^([A-Ra-r]{2})([0-9]{2})(?:([A-Xa-x]{2})([0-9]{2})?)?$")


def _dm_to_degrees(value: str, hemisphere: str) -> float | None:
    """DDMM.mm / DDDMM.mm + N/S/E/W → 十进制度；格式非法返回 None。

    入参 value 末尾带半球字母（如 ``4903.50N`` / ``07201.75W``）。
    度数 = 整数部分去掉末两位（分），分 = 末两位整数 + 小数。
    """
    body = value[:-1]                # 去掉末尾 N/S/E/W
    if "." not in body:
        return None
    int_part, frac_part = body.split(".", 1)
    if len(int_part) < 3:
        return None
    try:
        deg = int(int_part[:-2])     # DD（纬度）或 DDD（经度）
        minutes = float(int_part[-2:] + "." + frac_part)
    except ValueError:
        return None
    if not 0.0 <= minutes < 60.0:
        return None
    out = deg + minutes / 60.0
    if hemisphere in "SW":
        out = -out
    return out


def _maidenhead_to_latlon(grid: str) -> tuple[float, float] | None:
    """Maidenhead 网格中心点 → (lat, lon)；非法网格返回 None。

    转换关系：字段对 18 经度格 × 10 纬度格；方格 2° 经 × 1° 纬；
    子字段 5' 经 × 2.5' 纬；子方格 30'' 经 × 15'' 纬（中心取半格）。
    """
    g = grid.upper().strip()
    m = _GRID_RE.match(g)
    if not m or (len(g) % 2) != 0:
        return None
    # 字段
    lon = (ord(g[0]) - ord("A")) * 20 - 180
    lat = (ord(g[1]) - ord("A")) * 10 - 90
    # 方格
    if len(g) >= 4:
        lon += int(g[2]) * 2
        lat += int(g[3])
    # 子字段
    if len(g) >= 6:
        lon += (ord(g[4]) - ord("A")) * (5 / 60)
        lat += (ord(g[5]) - ord("A")) * (2.5 / 60)
    # 子方格
    if len(g) >= 8:
        lon += int(g[6]) * (30 / 3600)
        lat += int(g[7]) * (15 / 3600)
    # 中心点：加上当前精度格的一半
    half = {2: (10.0, 5.0), 4: (1.0, 0.5),
            6: (2.5 / 60, 1.25 / 60), 8: (15 / 3600, 7.5 / 3600)}[len(g)]
    return lat + half[1], lon + half[0]


def parse_aprs_text(text: str) -> dict:
    """解析 decode_afsk1200 返回的 ``"{dest} <- {src}: {info}"`` 文本。

    返回 dict：source（源呼号）、dest（目的地址）、info、format、
    lat / lon（仅当 info 为位置包或 Maidenhead 网格时可解析）。
    format 取值：``"position"`` | ``"grid"`` | ``None``。
    """
    result: dict = {"source": None, "dest": None, "info": None,
                    "lat": None, "lon": None, "format": None}

    m = re.match(r"^\s*(?P<dest>\S+)\s*<-\s*(?P<src>\S+)\s*:\s*(?P<info>.*)$",
                 text, re.DOTALL)
    if not m:
        # 兜底：按最后一次 "<-" 与首个 ":" 手动切分
        if "<-" not in text:
            return result
        dest, rest = text.split("<-", 1)
        dest = dest.strip()
        if ":" in rest:
            src, info = rest.split(":", 1)
        else:
            src, info = rest, ""
        m = re.match(r"^(?P<dest>\S+)\s*<-\s*(?P<src>\S+)\s*:\s*(?P<info>.*)$",
                     f"{dest} <- {src}: {info}", re.DOTALL)
        if not m:
            return result

    result["source"] = m.group("src").strip()
    result["dest"] = m.group("dest").strip()
    info = m.group("info").strip()
    result["info"] = info
    if not info:
        return result

    # 位置包：'!' 或 '=' 开头
    if info[0] in "!=":
        body = info[1:]
        pm = _POSITION_RE.search(body)
        if pm:
            lat = _dm_to_degrees(pm.group("lat"), pm.group("lat")[-1])
            lon = _dm_to_degrees(pm.group("lon"), pm.group("lon")[-1])
            if lat is not None and lon is not None:
                result["lat"], result["lon"] = lat, lon
                result["format"] = "position"
                return result
        # 网格定位器（! 或 = 后紧跟网格）
        grid_candidate = body.split("/")[0]
        ll = _maidenhead_to_latlon(grid_candidate)
        if ll is not None:
            result["lat"], result["lon"] = ll
            result["format"] = "grid"
            return result
        return result

    # 无前缀的纯网格定位器
    ll = _maidenhead_to_latlon(info)
    if ll is not None:
        result["lat"], result["lon"] = ll
        result["format"] = "grid"
    return result


# --------------------------------------------------------------------------- #
# APRS-IS passcode / 登录行
# --------------------------------------------------------------------------- #

def aprs_passcode(callsign: str) -> int:
    """APRS-IS 登录 passcode：种子 0x73e2，逐字符按位哈希，结果 & 0x7fff。

    标准算法（见 APRS-IS 通行实现）：呼号大写后按两字符一组，前一字符
    左移 8 位、后一字符原值，依次异或进种子；末尾单字符左移 8 位异或。
    """
    h = 0x73E2
    call = callsign.upper()
    i = 0
    n = len(call)
    while i < n:
        h ^= ord(call[i]) << 8
        if i + 1 < n:
            h ^= ord(call[i + 1])
        i += 2
    return h & 0x7FFF


def build_aprsis_login(callsign: str, passcode) -> str:
    """生成 APRS-IS 登录行 ``user <call> pass <code> vers rf_brain-igate 1.0``。"""
    return (f"user {callsign} pass {int(passcode)} "
            f"vers rf_brain-igate 1.0\r\n")


# --------------------------------------------------------------------------- #
# APRS-IS 上报（裸 socket）
# --------------------------------------------------------------------------- #

def igate_report(callsign: str, frames, host: str = "localhost",
                 port: int = 14580, timeout: int = 5, **params) -> dict:
    """向 APRS-IS 上报帧；mock 模式或 APRS_IS_MOCK=1 时不联网。

    mock 触发：params["mock"] 为真，或环境变量 APRS_IS_MOCK == "1"。
    返回 ``{"ok": True, "mock": True, "frames": [...]}``（mock）或
    ``{"ok": True, "server": host, "frames": [...]}``（真实）；失败返回
    ``{"ok": False, "error": "..."}``，不抛裸异常。
    """
    frame_list = [str(f) for f in frames]

    if params.get("mock") or os.environ.get("APRS_IS_MOCK") == "1":
        return {"ok": True, "mock": True, "frames": frame_list}

    login = build_aprsis_login(callsign, aprs_passcode(callsign))
    lines = [login] + [f"{f}\r\n" if not f.endswith("\r\n") else f
                       for f in frame_list]
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as s:
            for line in lines:
                s.sendall(line.encode("ascii", "replace"))
    except (OSError, socket.timeout, ValueError) as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "server": host, "port": int(port),
            "frames": frame_list}


# --------------------------------------------------------------------------- #
# 本地 GeoJSON 导出
# --------------------------------------------------------------------------- #

def export_geojson(records, file_path) -> dict:
    """记录 → GeoJSON FeatureCollection（Point）写入 file_path。

    无坐标（lat/lon 缺失）的记录跳过。返回
    ``{"ok": True, "file_path": str, "count": N}``。
    """
    features = []
    for rec in records:
        lat = rec.get("lat")
        lon = rec.get("lon")
        if lat is None or lon is None:
            continue
        properties = {k: v for k, v in rec.items() if k not in ("lat", "lon")}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": properties,
        })
    fc = {"type": "FeatureCollection", "features": features}

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)

    return {"ok": True, "file_path": str(path), "count": len(features)}


# --------------------------------------------------------------------------- #
# 去重过滤（滑动窗口）
# --------------------------------------------------------------------------- #

def _to_timestamp(value) -> float | None:
    """datetime / 数值 / 字符串 → Unix 秒；None → None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dedupe_frames(frames, window_seconds: float = 60.0):
    """按 (callsign, info) 在时间窗内去重，返回带 ``time`` 字段的记录列表。

    - 入参每项为 dict，含 callsign / info / time（缺省 time 用当前时刻）。
    - 先按 time 升序稳定排序，再用「每组最近一次上报时间」做滑动窗口判定。
    """
    normalized = []
    for f in frames:
        rec = dict(f)
        ts = _to_timestamp(rec.get("time"))
        if ts is None:
            ts = time.time()
        rec["time"] = ts
        normalized.append(rec)

    normalized.sort(key=lambda r: r["time"])

    out: list[dict] = []
    last_seen: dict[tuple, float] = {}
    for rec in normalized:
        key = (rec.get("callsign"), rec.get("info"))
        ts = rec["time"]
        prev = last_seen.get(key)
        if prev is not None and (ts - prev) <= window_seconds:
            continue                       # 窗口内重复，丢弃
        last_seen[key] = ts
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# 配置加载
# --------------------------------------------------------------------------- #

def load_config(path=None) -> dict:
    """加载 JSON 配置覆盖默认值；path 缺失或文件不存在时返回默认值。

    ``passcode`` 缺省 / 为 null 时按 ``igate_callsign`` 自动计算。
    """
    config = dict(DEFAULT_CONFIG)
    if path is not None:
        p = Path(path)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            config.update(data)
    if config.get("passcode") is None:
        config["passcode"] = aprs_passcode(config["igate_callsign"])
    return config


# --------------------------------------------------------------------------- #
# 便捷入口：解码 → 解析 → 上报 → 导出
# --------------------------------------------------------------------------- #

def process_iq(iq: np.ndarray, sample_rate: float, config: dict | None = None,
               **params) -> dict:
    """端到端：AFSK1200 解码 → 解析 → mock/真实上报 → 追加导出。"""
    cfg = load_config() if config is None else config
    try:
        text = _aprs.decode_afsk1200(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    parsed = parse_aprs_text(text)
    report = igate_report(
        cfg["igate_callsign"],
        [text],
        host=cfg["aprsis_host"],
        port=cfg["aprsis_port"],
        mock=cfg.get("mock", False),
    )
    return {"ok": True, "text": text, "parsed": parsed, "report": report}


__all__ = [
    "DEFAULT_CONFIG",
    "parse_aprs_text",
    "aprs_passcode",
    "build_aprsis_login",
    "igate_report",
    "export_geojson",
    "dedupe_frames",
    "load_config",
    "process_iq",
]
