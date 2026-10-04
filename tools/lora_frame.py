"""LoRaCanary 帧协议 · Python 镜像（纯标准库，与 C++ 侧 loracanary_frame.cpp 逐字节兼容）。

依据 docs/SPEC-20-LoRa环境感知节点-总纲.md 第二节帧格式（本文件是唯一格式契约的
Python 实现，供 pytest 与主机解析；ESP32 侧用 C++ 镜像，二者逐字节一致）。

帧格式：
    magic(2B) + type(1B) + seq(1B) + node_id(1B) + payload(N) + crc16(2B LE)
    总长 = 7 + N，payload ≤ 120B

消息类型 type：
    0x01 = ENV（环境数据）     payload 定长 7B
    0x02 = HEARTBEAT（心跳）   payload 0B
    0x03 = GEO（定位+环境）    payload 定长 18B     ← v1.5 新增（AB-01）
    0xFE = ACK（确认）         payload 0B
    0xFF = ERR（错误）         payload 0B

ENV payload（7B）：
    t: int16 LE  ×100（0.01℃）  —— 26.3℃ → 2630
    h: uint8      原值百分比(0-100)  —— 55% → 55
    p: uint32 LE ×100（0.01hPa） —— 1013.2hPa → 101320

    注：SPEC 原文写「h:uint8(0.1%)」，但 0.1% 分辨率下 0-100% 需 0-1000，溢出 uint8。
    v1 取 1% 分辨率（uint8 原值），如需 0.1% 精度 v2 升级 uint16×10（诚实标注，见 README）。

GEO payload（18B，v1.5——顺序照 SPEC-20 v1.5 第二节，逐字段契约）：
    t:   int16 LE  ×100（0.01℃）
    h:   uint8      湿度 %（1% 分辨率，同 ENV 勘误）
    p:   uint32 LE ×100（0.01hPa）
    lat: int32 LE  ×1e7（度）—— 39.9042 → 399042000，±180° 均在 int32 内
    lng: int32 LE  ×1e7（度）
    alt: int16 LE  海拔 m（有符号，1m 分辨率）
    sat: uint8     卫星数，0 = 无定位

    勘误（诚实标注）：立项工单写「GEO payload 定长 16B / 总帧 23B」，逐字段算术
    合计 2+1+4+4+4+2+1 = 18B（总帧 7+18=25B）。按字段清单实现是唯一自洽读法
    （16B 会丢字段、破坏编解码往返）。仍是定长结构，仍 < 120B 上限。

    降级：sat=0 时 encode 强制 lat/lng/alt=0（无定位不报假坐标）；decode 不崩。

完整性：
  - magic = b"\\xd0\\xcc"（与 mesh_layer 的 b"MR"、dcp 的 0xD0CC 同字，LoRaCanary 独用）
  - CRC-16 MODBUS（poly 0x8005 / init 0xFFFF / refin/refout true），覆盖
    type+seq+node_id+payload（不含 magic）。标准向量 b"123456789" → 0x4B37。
  - decode 校验 magic + crc + type + 定长，任一失败返回 None，不抛异常（坏帧贞洁）。
"""
from __future__ import annotations

MAGIC = b"\xd0\xcc"
MAGIC_LEN = 2
TYPE_LEN = 1
SEQ_LEN = 1
NODE_ID_LEN = 1
HEADER_LEN = MAGIC_LEN + TYPE_LEN + SEQ_LEN + NODE_ID_LEN  # 5
CRC_LEN = 2
OVERHEAD = HEADER_LEN + CRC_LEN                            # 7

MAX_PAYLOAD = 120          # 载荷 ≤120B（SPEC 硬约束）
MAX_FRAME = OVERHEAD + MAX_PAYLOAD

ENV_PAYLOAD_LEN = 7        # t(2) + h(1) + p(4)
GEO_PAYLOAD_LEN = 18       # t(2) + h(1) + p(4) + lat(4) + lng(4) + alt(2) + sat(1)
GEO_FRAME_LEN = OVERHEAD + GEO_PAYLOAD_LEN  # 25B（GEO 总帧定长）

# ---- 消息类型 ----
TYPE_ENV = 0x01
TYPE_HEARTBEAT = 0x02
TYPE_GEO = 0x03
TYPE_ACK = 0xFE
TYPE_ERR = 0xFF

# 已知类型的 payload 长度（None = 变长，不额外校验）
_PAYLOAD_LEN = {
    TYPE_ENV: ENV_PAYLOAD_LEN,
    TYPE_HEARTBEAT: 0,
    TYPE_GEO: GEO_PAYLOAD_LEN,
    TYPE_ACK: 0,
    TYPE_ERR: 0,
}

# 可读类型名（decode 结果里附带）
_TYPE_NAMES = {
    TYPE_ENV: "env",
    TYPE_HEARTBEAT: "heartbeat",
    TYPE_GEO: "geo",
    TYPE_ACK: "ack",
    TYPE_ERR: "err",
}


# ---- CRC-16 MODBUS（查表法，纯标准库）----
_CRC16_TABLE: list[int] = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xA001 if _c & 1 else _c >> 1
    _CRC16_TABLE.append(_c)


def crc16_modbus(data: bytes) -> int:
    """CRC-16 MODBUS，标准向量 crc16_modbus(b"123456789") == 0x4B37。"""
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ b) & 0xFF]
    return crc


def _u8(v: int, name: str) -> int:
    if not (0 <= int(v) <= 255):
        raise ValueError(f"{name} 超出 uint8 范围: {v}")
    return int(v) & 0xFF


# ---- 编解码 ----
def encode(
    msg_type: int = TYPE_ENV,
    seq: int = 0,
    node_id: int = 1,
    payload: bytes = b"",
    *,
    env: int | None = None,
    t: float | None = None,
    h: float | None = None,
    p: float | None = None,
    geo: bool = False,
    lat: float | None = None,
    lng: float | None = None,
    alt: float | None = None,
    sat: int | None = None,
) -> bytes:
    """编码一帧：magic + type + seq + node_id + payload + crc16(LE)。

    三种调用：
      encode(TYPE_HEARTBEAT, seq, node_id)                     # 通用
      encode(env=node_id, seq=seq, t=26.3, h=55.0, p=1013.2)  # 便捷 env 帧（SPEC 验收写法）
      encode(geo=True, seq=seq, t=26.3, h=55, p=1013.2,
             lat=39.9042, lng=116.4074, alt=52, sat=8)        # 便捷 geo 帧（v1.5）

    geo=True 或给出 lat/lng/sat 之一时走 GEO 分支（geo 显式优先）。
    """
    if geo or lat is not None or lng is not None or sat is not None:
        return encode_geo(
            node_id, seq,
            0.0 if t is None else t,
            0.0 if h is None else h,
            0.0 if p is None else p,
            0.0 if lat is None else lat,
            0.0 if lng is None else lng,
            0.0 if alt is None else alt,
            0 if sat is None else sat,
        )
    if env is not None or t is not None or h is not None or p is not None:
        nid = node_id if env is None else env
        return encode_env(
            nid, seq,
            0.0 if t is None else t,
            0.0 if h is None else h,
            0.0 if p is None else p,
        )
    mt = _u8(msg_type, "msg_type")
    sq = _u8(seq, "seq")
    nid = _u8(node_id, "node_id")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload 超长: {len(payload)} > {MAX_PAYLOAD}")
    body = bytes([mt, sq, nid]) + bytes(payload)
    crc = crc16_modbus(body)
    return MAGIC + body + crc.to_bytes(2, "little")


def encode_env(node_id: int, seq: int, t: float, h: float, p: float) -> bytes:
    """编码一帧 env 数据（node_id + 温湿压）。"""
    return encode(TYPE_ENV, seq, node_id, build_env_payload(t, h, p))


def encode_geo(node_id: int, seq: int, t: float, h: float, p: float,
               lat: float, lng: float, alt: float, sat: int) -> bytes:
    """编码一帧 geo 数据（node_id + 温湿压 + 定位，v1.5）。"""
    return encode(TYPE_GEO, seq, node_id,
                  build_geo_payload(t, h, p, lat, lng, alt, sat))


def build_env_payload(t: float, h: float, p: float) -> bytes:
    """构造 7B env payload：t(int16 LE ×100) + h(uint8) + p(uint32 LE ×100)。"""
    t_raw = round(t * 100)
    if not (-32768 <= t_raw <= 32767):
        raise ValueError(f"t 超出 int16 范围(×100): {t}")
    h_raw = round(h)
    if not (0 <= h_raw <= 255):
        raise ValueError(f"h 超出 uint8 范围: {h}")
    p_raw = round(p * 100)
    if not (0 <= p_raw <= 0xFFFFFFFF):
        raise ValueError(f"p 超出 uint32 范围(×100): {p}")
    return (
        t_raw.to_bytes(2, "little", signed=True)
        + bytes([h_raw])
        + p_raw.to_bytes(4, "little")
    )


def parse_env_payload(payload: bytes) -> dict:
    """解析 7B env payload → {"t":float,"h":int,"p":float}；长度不足返回空 dict。"""
    if len(payload) != ENV_PAYLOAD_LEN:
        return {}
    t = int.from_bytes(payload[0:2], "little", signed=True) / 100.0
    h = payload[2]
    p = int.from_bytes(payload[3:7], "little") / 100.0
    return {"t": round(t, 2), "h": h, "p": round(p, 2)}


def build_geo_payload(t: float, h: float, p: float,
                      lat: float, lng: float, alt: float, sat: int) -> bytes:
    """构造 18B geo payload（SPEC-20 v1.5 第二节，逐字段定长）。

    字节序（offset）：
      0-1  t   int16 LE ×100
      2    h   uint8
      3-6  p   uint32 LE ×100
      7-10 lat int32 LE ×1e7
      11-14    lng int32 LE ×1e7
      15-16    alt int16 LE（米）
      17   sat uint8

    降级：sat=0 时强制 lat/lng/alt=0（无定位不报假坐标，工单 AB-01 第 4 条）。
    """
    sat_raw = _u8(sat, "sat")
    t_raw = round(t * 100)
    if not (-32768 <= t_raw <= 32767):
        raise ValueError(f"t 超出 int16 范围(×100): {t}")
    h_raw = round(h)
    if not (0 <= h_raw <= 255):
        raise ValueError(f"h 超出 uint8 范围: {h}")
    p_raw = round(p * 100)
    if not (0 <= p_raw <= 0xFFFFFFFF):
        raise ValueError(f"p 超出 uint32 范围(×100): {p}")
    if sat_raw == 0:
        lat = lng = 0.0
        alt = 0
    lat_raw = round(lat * 10_000_000)
    if not (-2147483648 <= lat_raw <= 2147483647):
        raise ValueError(f"lat 超出 int32 范围(×1e7): {lat}")
    lng_raw = round(lng * 10_000_000)
    if not (-2147483648 <= lng_raw <= 2147483647):
        raise ValueError(f"lng 超出 int32 范围(×1e7): {lng}")
    alt_raw = round(alt)
    if not (-32768 <= alt_raw <= 32767):
        raise ValueError(f"alt 超出 int16 范围(米): {alt}")
    return (
        t_raw.to_bytes(2, "little", signed=True)
        + bytes([h_raw])
        + p_raw.to_bytes(4, "little")
        + lat_raw.to_bytes(4, "little", signed=True)
        + lng_raw.to_bytes(4, "little", signed=True)
        + alt_raw.to_bytes(2, "little", signed=True)
        + bytes([sat_raw])
    )


def parse_geo_payload(payload: bytes) -> dict:
    """解析 18B geo payload → 各字段 + gps_fix；长度不符返回空 dict（不崩）。"""
    if len(payload) != GEO_PAYLOAD_LEN:
        return {}
    t = int.from_bytes(payload[0:2], "little", signed=True) / 100.0
    h = payload[2]
    p = int.from_bytes(payload[3:7], "little") / 100.0
    lat = int.from_bytes(payload[7:11], "little", signed=True) / 10_000_000
    lng = int.from_bytes(payload[11:15], "little", signed=True) / 10_000_000
    alt = int.from_bytes(payload[15:17], "little", signed=True)
    sat = payload[17]
    return {
        "t": round(t, 2), "h": h, "p": round(p, 2),
        "lat": round(lat, 7), "lng": round(lng, 7),
        "alt": alt, "sat": sat,
        "gps_fix": sat > 0,
    }


def decode(frame: bytes | bytearray) -> dict | None:
    """解码一帧 → dict；坏帧返回 None（不抛异常）。

    成功返回：
      {"type":int, "type_name":str, "seq":int, "node_id":int, "payload":bytes}
    ENV 帧额外含 t/h/p；GEO 帧额外含 t/h/p/lat/lng/alt/sat/gps_fix。
    """
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < OVERHEAD:
        return None
    if bytes(frame[:MAGIC_LEN]) != MAGIC:
        return None
    mt = frame[MAGIC_LEN]
    seq = frame[MAGIC_LEN + TYPE_LEN]
    node_id = frame[MAGIC_LEN + TYPE_LEN + SEQ_LEN]
    payload = bytes(frame[HEADER_LEN:-CRC_LEN])
    crc = int.from_bytes(frame[-CRC_LEN:], "little")

    # CRC 覆盖 type+seq+node_id+payload（frame[2:-2]）
    if crc16_modbus(bytes(frame[MAGIC_LEN:-CRC_LEN])) != crc:
        return None
    if mt not in _PAYLOAD_LEN:
        return None
    expected = _PAYLOAD_LEN[mt]
    if expected is not None and len(payload) != expected:
        return None

    out = {
        "type": mt,
        "type_name": _TYPE_NAMES[mt],
        "seq": seq,
        "node_id": node_id,
        "payload": payload,
    }
    if mt == TYPE_ENV:
        out.update(parse_env_payload(payload))
    if mt == TYPE_GEO:
        out.update(parse_geo_payload(payload))
    return out


def decode_env(frame: bytes | bytearray) -> dict | None:
    """解码 env 帧 → {"node_id","seq","t","h","p"}；非 env 或坏帧返回 None。"""
    d = decode(frame)
    if d is None or d["type"] != TYPE_ENV:
        return None
    return {
        "node_id": d["node_id"],
        "seq": d["seq"],
        "t": d["t"],
        "h": d["h"],
        "p": d["p"],
    }


def decode_geo(frame: bytes | bytearray) -> dict | None:
    """解码 geo 帧 → {"node_id","seq","t","h","p","lat","lng","alt","sat","gps_fix"}；非 geo 或坏帧返回 None。"""
    d = decode(frame)
    if d is None or d["type"] != TYPE_GEO:
        return None
    return {
        "node_id": d["node_id"],
        "seq": d["seq"],
        "t": d["t"], "h": d["h"], "p": d["p"],
        "lat": d["lat"], "lng": d["lng"], "alt": d["alt"],
        "sat": d["sat"], "gps_fix": d["gps_fix"],
    }


__all__ = [
    "MAGIC", "HEADER_LEN", "OVERHEAD", "MAX_PAYLOAD", "ENV_PAYLOAD_LEN",
    "GEO_PAYLOAD_LEN", "GEO_FRAME_LEN",
    "TYPE_ENV", "TYPE_HEARTBEAT", "TYPE_GEO", "TYPE_ACK", "TYPE_ERR",
    "crc16_modbus", "encode", "encode_env", "encode_geo",
    "build_env_payload", "parse_env_payload",
    "build_geo_payload", "parse_geo_payload",
    "decode", "decode_env", "decode_geo",
]
