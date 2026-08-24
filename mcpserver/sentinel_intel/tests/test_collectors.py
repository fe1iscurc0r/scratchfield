# tests/test_collectors.py — M-01 OSINT 采集器 MCP 封装 单元测试
#
# 6 用例（工单点名，全部 mock 网络层 _net，离线可测）：
#   1. whois_lookup 成功（mock tcp_query → WHOIS 文本，解析字段 + ingest）
#   2. whois_lookup 网络失败（mock 抛 socket.timeout → ok=False 不抛错）
#   3. dns_lookup 成功（mock udp_query → 构造 DNS A 响应，records + ingest 边）
#   4. dns_lookup NXDOMAIN（mock → rcode=3 响应，ok=True 空记录）
#   5. cert_lookup 成功（mock http_get → crt.sh JSON，certs 解析 + ingest）
#   6. cert_lookup 网络失败（mock 抛 URLError → ok=False 不抛错）
#
# 运行：python -m pytest mcpserver/sentinel_intel/tests/test_collectors.py -q
"""Tests for sentinel_intel.collectors (mock 网络层，离线可测)."""

from __future__ import annotations

import json
import socket
import struct
import sys
import urllib.error
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # worktree 根（含 mcpserver/）
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.sentinel_intel.collectors import cert as cert_mod  # noqa: E402
from mcpserver.sentinel_intel.collectors import dns as dns_mod  # noqa: E402
from mcpserver.sentinel_intel.collectors import whois as whois_mod  # noqa: E402

WHOIS_TEXT = (
    "Domain Name: EXAMPLE.COM\n"
    "Registrar: RESERVED-Internet Assigned Numbers Authority\n"
    "Creation Date: 1995-08-14T04:00:00Z\n"
    "Registry Expiry Date: 2027-08-13T04:00:00Z\n"
    "Name Server: A.IANA-SERVERS.NET\n"
    "Name Server: B.IANA-SERVERS.NET\n"
    "Status: clientDeleteProhibited\n"
)


def _dns_response(answers: list[tuple[str, int, int, bytes]], rcode: int = 0) -> bytes:
    """构造最小 DNS 响应：1 question（example.com/A）+ N answer（名字压缩指针）。"""
    flags = 0x8080 | rcode  # QR=1, RD=1, rcode
    header = struct.pack(">HHHHHH", 0x1234, flags, 1, len(answers), 0, 0)
    question = dns_mod._encode_name("example.com") + struct.pack(">HH", 1, 1)
    body = b"".join(
        b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 60, len(rdata)) + rdata
        for _, qtype, _, rdata in answers)
    return header + question + body


def test_whois_lookup_success():
    with mock.patch.object(whois_mod._net, "tcp_query", return_value=WHOIS_TEXT):
        result = whois_mod.whois_lookup("example.com")
    assert result["ok"] is True
    assert result["source"] == "whois"
    assert result["domain"] == "example.com"
    assert result["data"]["registrar"] == "RESERVED-Internet Assigned Numbers Authority"
    assert result["data"]["name_server"] == ["A.IANA-SERVERS.NET", "B.IANA-SERVERS.NET"]
    # 降级纪律附带：成功载荷可直接喂 intel_ingest（etype=infra）
    assert result["ingest"]["entities"][0] == {
        "etype": "infra", "value": "example.com",
        "props": {"source": "whois", "server": "whois.iana.org",
                  "registrar": "RESERVED-Internet Assigned Numbers Authority",
                  "creation_date": "1995-08-14T04:00:00Z",
                  "expiry_date": "2027-08-13T04:00:00Z",
                  "name_servers": ["A.IANA-SERVERS.NET", "B.IANA-SERVERS.NET"],
                  "status": "clientDeleteProhibited", "registrant_org": None}}


def test_whois_lookup_network_failure_degrades():
    with mock.patch.object(whois_mod._net, "tcp_query",
                           side_effect=TimeoutError("timed out")):
        result = whois_mod.whois_lookup("example.com")
    assert result["ok"] is False
    assert "error" in result
    assert result["ingest"] == {"entities": [], "edges": []}


def test_dns_lookup_success():
    resp = _dns_response([("example.com", 1, 60, socket.inet_aton("93.184.216.34"))])
    with mock.patch.object(dns_mod._net, "udp_query", return_value=resp):
        result = dns_mod.dns_lookup("example.com")
    assert result["ok"] is True
    a_records = [r for r in result["data"]["records"] if r["type"] == "A"]
    assert a_records == [{"type": "A", "name": "example.com", "ttl": 60,
                          "value": "93.184.216.34"}]
    # ingest：domain(infra) --observed_at--> ip(indicator)
    assert result["ingest"]["entities"][0]["etype"] == "infra"
    ip_entities = [e for e in result["ingest"]["entities"]
                   if e.get("etype") == "indicator"]
    assert ip_entities == [{"etype": "indicator", "value": "93.184.216.34",
                            "props": {"kind": "ip", "record_type": "A"}}]
    assert result["ingest"]["edges"][0]["rel"] == "observed_at"


def test_dns_lookup_nxdomain_is_ok_empty():
    resp = _dns_response([], rcode=3)  # NXDOMAIN
    with mock.patch.object(dns_mod._net, "udp_query", return_value=resp):
        result = dns_mod.dns_lookup("example.com")
    assert result["ok"] is True  # NXDOMAIN 非网络故障，不算降级
    assert result["data"]["records"] == []
    assert result["data"]["record_count"] == 0


def test_cert_lookup_success():
    crtsh_json = json.dumps([
        {"common_name": "example.com",
         "issuer_name": "C=US, O=Let's Encrypt",
         "not_before": "2026-01-01T00:00:00", "not_after": "2026-04-01T00:00:00",
         "serial_number": "01"},
        {"common_name": "www.example.com",
         "issuer_name": "C=US, O=Let's Encrypt",
         "not_before": "2026-02-01T00:00:00", "not_after": "2026-05-01T00:00:00",
         "serial_number": "02"},
    ])
    with mock.patch.object(cert_mod._net, "http_get", return_value=crtsh_json):
        result = cert_mod.cert_lookup("example.com")
    assert result["ok"] is True
    assert result["data"]["cert_count"] == 2
    assert result["data"]["certs"][0]["common_name"] == "example.com"
    assert result["ingest"]["entities"][0]["etype"] == "infra"
    assert result["ingest"]["entities"][0]["props"]["cert_count"] == 2
    assert result["ingest"]["entities"][0]["props"]["issuers"] == [
        "C=US, O=Let's Encrypt"]


def test_cert_lookup_network_failure_degrades():
    with mock.patch.object(cert_mod._net, "http_get",
                           side_effect=urllib.error.URLError("network unreachable")):
        result = cert_mod.cert_lookup("example.com")
    assert result["ok"] is False
    assert "error" in result
    assert result["ingest"] == {"entities": [], "edges": []}
