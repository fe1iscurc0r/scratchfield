"""collectors/dns.py — DNS 采集器（最小 DNS 客户端，纯 stdlib）。

dns_lookup(domain)：UDP:53 直查指定 resolver（默认 8.8.8.8），自构造查询
包/自解析响应（A/AAAA/NS/MX/TXT，名字支持压缩指针），不依赖系统解析器
（可 mock，离线可测）。
降级纪律照 context7.py：网络失败/超时 → {"ok": False} 永不抛错；
NXDOMAIN/无记录算正常结果（ok=True, records 空）。
成功载荷带 ingest：domain(infra) --observed_at--> 解析资源(indicator)。
"""
from __future__ import annotations

import ipaddress
import logging
import random
import struct
from datetime import UTC, datetime
from typing import Any

from . import _net

logger = logging.getLogger(__name__)

DEFAULT_RESOLVER = "8.8.8.8"
DEFAULT_PORT = 53

# 支持的记录类型（够 OSINT 勘察用，不引 dnspython）
QTYPE = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28}
_QTYPE_NAME = {v: k for k, v in QTYPE.items()}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _encode_name(name: str) -> bytes:
    """域名 → DNS wire 格式（每段 len 前缀 + 末尾 0）。"""
    out = bytearray()
    for label in str(name).rstrip(".").split("."):
        if not label:
            continue
        out.append(len(label))
        out.extend(label.encode("ascii", errors="ignore"))
    out.append(0)
    return bytes(out)


def _build_query(name: str, qtype: int) -> bytes:
    """构造 DNS 查询包（随机 id、RD=1、单 question）。"""
    header = struct.pack(">HHHHHH", random.randint(0, 0xFFFF), 0x0100,
                         1, 0, 0, 0)
    question = _encode_name(name) + struct.pack(">HH", qtype, 1)
    return header + question


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    """读 DNS 名字（支持压缩指针），返回 (域名, 跳过后的偏移)。

    offset 指向名字起点；返回偏移指向上层解包的下一位。若中途遇压缩
    指针，则指向指针字段之后（即上层无需再解包后续名字字节）。
    """
    labels: list[str] = []
    pos = offset
    end = offset
    jumped = False
    while pos < len(data):
        length = data[pos]
        if length == 0:  # 名字终止
            if not jumped:
                end = pos + 1
            break
        if length & 0xC0 == 0xC0:  # 压缩指针（0xC0 XX → 偏移）
            if pos + 1 >= len(data):
                break
            if not jumped:
                end = pos + 2
                jumped = True
            pos = ((length & 0x3F) << 8) | data[pos + 1]
            continue
        pos += 1
        if pos + length > len(data):
            break
        labels.append(data[pos:pos + length].decode("ascii", errors="ignore"))
        pos += length
    return ".".join(labels), end


def _format_rdata(rtype: int, rdata: bytes) -> str:
    """rdata → 可读字符串（A/AAAA/NS/CNAME/MX/TXT，其余 hex 兜底）。"""
    if rtype == 1 and len(rdata) == 4:  # A
        return ".".join(str(b) for b in rdata)
    if rtype == 28 and len(rdata) == 16:  # AAAA
        return str(ipaddress.IPv6Address(rdata))
    if rtype in (2, 5):  # NS / CNAME（rdata 内嵌名字）
        name, _ = _read_name(rdata, 0)
        return name
    if rtype == 15 and len(rdata) >= 3:  # MX（偏好 + 名字）
        pref = int.from_bytes(rdata[:2], "big")
        name, _ = _read_name(rdata, 2)
        return f"{pref} {name}"
    if rtype == 16:  # TXT（多段字符串拼接）
        parts: list[str] = []
        pos = 0
        while pos < len(rdata):
            n = rdata[pos]
            if pos + 1 + n > len(rdata):
                break
            parts.append(
                rdata[pos + 1:pos + 1 + n].decode("utf-8", errors="replace"))
            pos += 1 + n
        return " ".join(parts)
    return rdata.hex()


def _parse_response(data: bytes) -> list[dict[str, Any]]:
    """DNS 响应 → 记录列表（[{"type": "A", "name": ..., "ttl": ..., "value": ...}]）。

    rcode 非 0（NXDOMAIN/SERVFAIL 等）或无 answer → 空列表。
    """
    records: list[dict[str, Any]] = []
    if len(data) < 12:
        return records
    _, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
    if (flags & 0x0F) != 0:  # rcode != NOERROR：无有效答案
        return records
    offset = 12
    for _ in range(qdcount):
        _, offset = _read_name(data, offset)
        offset += 4  # qtype + qclass
    for _ in range(ancount):
        name, offset = _read_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _, ttl, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlength]
        offset += rdlength
        records.append({"type": _QTYPE_NAME.get(rtype, f"TYPE{rtype}"),
                        "name": name, "ttl": ttl,
                        "value": _format_rdata(rtype, rdata)})
    return records


def dns_lookup(domain: str,
               rtypes: tuple[str, ...] = ("A", "AAAA", "NS", "MX", "TXT"),
               resolver: str = DEFAULT_RESOLVER,
               timeout: float = 8.0) -> dict[str, Any]:
    """DNS 查询：逐记录类型发 UDP 查询，自解析响应。

    Args:
        domain: 待查域名（如 "example.com"）
        rtypes: 要查的记录类型（默认 A/AAAA/NS/MX/TXT 五类）
        resolver: DNS 服务器 IP（默认 8.8.8.8）
        timeout: 网络超时秒数

    Returns:
        {"ok": True, "source": "dns", "domain": ..., "resolver": ...,
         "ts": ..., "data": {"records": [...], "record_count": N},
         "ingest": {entities/edges}}
        网络失败/超时 → {"ok": False, "error": ...}（永不抛错）；
        NXDOMAIN/无记录 → ok=True 且 records 为空（非网络故障）。
    """
    def fail(err: str) -> dict[str, Any]:
        return {"ok": False, "source": "dns", "domain": domain,
                "resolver": resolver, "data": {},
                "ingest": {"entities": [], "edges": []}, "error": err}

    if not str(domain or "").strip():
        return fail("domain 不能为空")
    invalid = [t for t in rtypes if t not in QTYPE]
    if invalid:
        return fail(f"不支持的记录类型: {invalid}（可用 {list(QTYPE)}）")

    records: list[dict[str, Any]] = []
    try:
        for rtype in rtypes:
            resp = _net.udp_query(resolver, DEFAULT_PORT,
                                  _build_query(domain, QTYPE[rtype]), timeout)
            for rec in _parse_response(resp):
                if rec["type"] == rtype:  # 只收本查询类型的 answer
                    records.append(rec)
    except Exception as e:  # 无网络/超时/resolver 无响应 → 降级，绝不抛错
        logger.info("[collector:dns] %s 降级（resolver=%s）: %s",
                    domain, resolver, e)
        return fail(str(e) or type(e).__name__)

    # ingest：domain(infra) + A/AAAA 解析到的 IP(indicator)，observed_at 边
    entities: list[dict[str, Any]] = [{
        "etype": "infra", "value": domain,
        "props": {"source": "dns", "resolver": resolver,
                  "record_count": len(records)}}]
    edges: list[dict[str, Any]] = []
    for rec in records:
        if rec["type"] in ("A", "AAAA"):
            entities.append({"etype": "indicator", "value": rec["value"],
                             "props": {"kind": "ip", "record_type": rec["type"]}})
            edges.append({
                "src": {"etype": "infra", "value": domain},
                "dst": {"etype": "indicator", "value": rec["value"]},
                "rel": "observed_at",
                "props": {"record_type": rec["type"]}})
    return {"ok": True, "source": "dns", "domain": domain,
            "resolver": resolver, "ts": _now_iso(),
            "data": {"records": records, "record_count": len(records)},
            "ingest": {"entities": entities, "edges": edges}}
