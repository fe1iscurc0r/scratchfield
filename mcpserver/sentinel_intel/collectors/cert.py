"""collectors/cert.py — 证书透明度采集器（crt.sh JSON API，纯 stdlib）。

cert_lookup(domain)：urllib 查 crt.sh 证书透明度日志，返回该域签发的证书
列表（CN/issuer/有效期/序列号），去重保序。
降级纪律照 context7.py：网络失败/超时/JSON 异常/无记录 → {"ok": False}
永不抛错。成功载荷带 ingest（etype=infra，可直接喂 intel_ingest）。
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from . import _net

logger = logging.getLogger(__name__)

CRTSH_URL = "https://crt.sh/?q={query}&output=json"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_certs(text: str) -> list[dict[str, Any]]:
    """crt.sh JSON → 去重证书列表（CN|serial 去重，保序）。"""
    try:
        rows = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    seen: set[str] = set()
    certs: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cn = str(row.get("common_name") or row.get("name_value") or "").strip()
        if not cn:
            continue
        key = f"{cn}|{row.get('serial_number')}"
        if key in seen:
            continue
        seen.add(key)
        certs.append({
            "common_name": cn,
            "issuer": str(row.get("issuer_name") or "").strip(),
            "not_before": str(row.get("not_before") or "").strip(),
            "not_after": str(row.get("not_after") or "").strip(),
            "serial_number": str(row.get("serial_number") or "").strip(),
        })
    return certs


def cert_lookup(domain: str, timeout: float = 8.0) -> dict[str, Any]:
    """证书透明度查询：查 crt.sh 公开日志，返回该域证书列表。

    Args:
        domain: 待查域名（如 "example.com"）
        timeout: 网络超时秒数

    Returns:
        {"ok": True, "source": "cert", "domain": ..., "ts": ...,
         "data": {"certs": [...], "cert_count": N}, "ingest": {entities/edges}}
        网络失败/超时/JSON 异常/无记录 → {"ok": False, "error": ...}（永不抛错）
    """
    def fail(err: str) -> dict[str, Any]:
        return {"ok": False, "source": "cert", "domain": domain, "data": {},
                "ingest": {"entities": [], "edges": []}, "error": err}

    if not str(domain or "").strip():
        return fail("domain 不能为空")
    url = CRTSH_URL.format(query=urllib.parse.quote(domain, safe=""))
    try:
        text = _net.http_get(url, timeout)
    except Exception as e:  # 无网络/超时/HTTP 错误 → 降级，绝不抛错
        logger.info("[collector:cert] %s 降级: %s", domain, e)
        return fail(str(e) or type(e).__name__)

    certs = _parse_certs(text)
    if not certs:
        return fail("crt.sh 无响应或该域无证书透明度记录")
    issuers = sorted({c["issuer"] for c in certs if c["issuer"]})
    props = {
        "source": "cert", "cert_count": len(certs),
        "issuers": issuers,
        "earliest_not_before": min(
            (c["not_before"] for c in certs if c["not_before"]), default=""),
        "latest_not_after": max(
            (c["not_after"] for c in certs if c["not_after"]), default=""),
    }
    return {"ok": True, "source": "cert", "domain": domain,
            "ts": _now_iso(),
            "data": {"certs": certs[:50], "cert_count": len(certs)},
            "ingest": {"entities": [{"etype": "infra", "value": domain,
                                     "props": props}], "edges": []}}
