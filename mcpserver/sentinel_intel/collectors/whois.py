"""collectors/whois.py — WHOIS 采集器（RFC 3912，纯 stdlib）。

whois_lookup(domain)：socket TCP:43 直连默认 whois.iana.org，发 "domain\r\n"
读回文本，解析常见字段（registrar/creation_date/name_server/status 等）。
降级纪律照 context7.py：网络失败/超时/响应为空 → {"ok": False} 永不抛错。
成功载荷带 ingest（etype=infra，可直接喂 IntelBridge.intel_ingest）。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from . import _net

logger = logging.getLogger(__name__)

DEFAULT_SERVER = "whois.iana.org"
DEFAULT_PORT = 43

# 只挑入库有情报价值的常见字段（值保原样，仅大小写归一判重）
_KEYS = (
    "registrar", "registrar_iana_id", "creation_date", "registry_expiry_date",
    "updated_date", "name_server", "registrant_organization",
    "registrant_country", "status", "refer",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_whois(text: str) -> dict[str, Any]:
    """WHOIS 文本 → 常见字段 dict（键 lower 下划线化，值去重保序）。"""
    fields: dict[str, list[str]] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()
        if not key or not value or key not in _KEYS:
            continue
        seen = {v.lower() for v in fields.get(key, [])}
        if value.lower() not in seen:
            fields.setdefault(key, []).append(value)
    return {k: (v[0] if len(v) == 1 else v) for k, v in fields.items()}


def whois_lookup(domain: str, server: str = DEFAULT_SERVER,
                 timeout: float = 8.0) -> dict[str, Any]:
    """WHOIS 查询：TCP:43 发 "domain\\r\\n"，解析常见字段。

    Args:
        domain: 待查域名（如 "example.com"）
        server: whois 服务器（默认 whois.iana.org，可换注册局服务器）
        timeout: 网络超时秒数

    Returns:
        {"ok": True, "source": "whois", "domain": ..., "server": ...,
         "ts": ..., "data": {字段}, "ingest": {entities/edges}}
        网络失败/超时/响应无可解析字段 → {"ok": False, "error": ...}（永不抛错）
    """
    def fail(err: str) -> dict[str, Any]:
        return {"ok": False, "source": "whois", "domain": domain,
                "server": server, "data": {},
                "ingest": {"entities": [], "edges": []}, "error": err}

    if not str(domain or "").strip():
        return fail("domain 不能为空")
    try:
        text = _net.tcp_query(server, DEFAULT_PORT, f"{domain}\r\n", timeout)
    except Exception as e:  # 无网络/超时/对端拒绝 → 降级，绝不抛错
        logger.info("[collector:whois] %s 降级（server=%s）: %s",
                    domain, server, e)
        return fail(str(e) or type(e).__name__)

    data = _parse_whois(text)
    if not data:
        return fail("whois 响应为空或无可解析字段")
    ingest = {
        "entities": [{
            "etype": "infra", "value": domain,
            "props": {"source": "whois", "server": server,
                      "registrar": data.get("registrar"),
                      "creation_date": data.get("creation_date"),
                      "expiry_date": data.get("registry_expiry_date"),
                      "name_servers": data.get("name_server"),
                      "status": data.get("status"),
                      "registrant_org": data.get("registrant_organization")},
        }],
        "edges": [],
    }
    return {"ok": True, "source": "whois", "domain": domain, "server": server,
            "ts": _now_iso(), "data": data, "ingest": ingest}
