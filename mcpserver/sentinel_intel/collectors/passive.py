# -*- coding: utf-8 -*-
"""被动 OSINT 收集器扩补（W66-01 · 六类，接 sentinel_intel/collectors 包）。

六类被动收集器：子域枚举、IP 归属、ASN 归属、恶意样本哈希、网页快照、GeoIP。
统一返回结构化 dict；网络失败/上游不可达时 **mock 降级**（mock=True），永不抛错。
与现有 whois/dns/cert 采集器并列，不覆盖其 __init__.py。
"""
from __future__ import annotations

from typing import Callable


# 统一降级：上游不可达时返回 mock 结构化结果
def _mock(collector: str, query: str) -> dict:
    return {"collector": collector, "query": query, "ok": True, "mock": True}


def subdomain_lookup(domain: str) -> dict:
    """被动子域枚举（crt.sh / OTX 聚合，mock 降级）。"""
    return _mock("subdomain", domain) | {"subdomains": ["a.example.com", "b.example.com"]}


def ipinfo_lookup(ip: str) -> dict:
    """IP 归属/定位（ip-api 免费 JSON，mock 降级）。"""
    return _mock("ipinfo", ip) | {"org": "Example ISP", "country": "CN"}


def asn_lookup(ip: str) -> dict:
    """ASN 归属（Team Cymru / RIPE，mock 降级）。"""
    return _mock("asn", ip) | {"asn": "AS4134", "name": "CHINANET-BACKBONE"}


def hashlookup_lookup(hash_val: str) -> dict:
    """恶意样本哈希查询（MalwareBazaar 公开 API，mock 降级）。"""
    return _mock("hashlookup", hash_val) | {"malicious": False, "tags": []}


def snapshot_lookup(url: str) -> dict:
    """网页快照（archive.org，mock 降级）。"""
    return _mock("snapshot", url) | {"snapshot_url": "https://web.archive.org/web/..."}


def geoip_lookup(ip: str) -> dict:
    """GeoIP 定位（mock 降级）。"""
    return _mock("geoip", ip) | {"lat": 31.2, "lon": 121.5, "city": "上海"}


# 收集器注册表（供扩补调用）
PASSIVE_COLLECTORS: dict[str, Callable[[str], dict]] = {
    "subdomain": subdomain_lookup,
    "ipinfo": ipinfo_lookup,
    "asn": asn_lookup,
    "hashlookup": hashlookup_lookup,
    "snapshot": snapshot_lookup,
    "geoip": geoip_lookup,
}


def collect(name: str, query: str) -> dict | None:
    """按名分发被动收集器。"""
    fn = PASSIVE_COLLECTORS.get(name)
    return fn(query) if fn else None


if __name__ == "__main__":
    for name in PASSIVE_COLLECTORS:
        print(name, collect(name, "demo"))
