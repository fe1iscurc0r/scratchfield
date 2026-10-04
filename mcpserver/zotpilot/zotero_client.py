"""Zotero Web API v3 客户端（薄封装，供 zotpilot 桥调用）。

仅用标准库 urllib，避免额外依赖。凭证一律走环境变量，便于测试注入：

- ZOTERO_API_KEY        Zotero API key（必填）
- ZOTERO_USER_ID        用户库 ID（与 ZOTERO_GROUP_ID 二选一）
- ZOTERO_GROUP_ID       群组库 ID（可选）
- ZOTERO_LIBRARY_TYPE   user | group（默认 user）
- ZOTERO_BASE_URL       API 根地址（默认 https://api.zotero.org）
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.zotero.org"


class ZoteroAuthError(RuntimeError):
    """凭证缺失或 Zotero API 拒绝请求。"""


class ZoteroClient:
    """Zotero Web API v3 同步客户端。"""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url or os.environ.get("ZOTERO_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

    @staticmethod
    def _credentials() -> tuple[str, str, str]:
        api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
        library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user").strip()
        library_id = os.environ.get(
            "ZOTERO_USER_ID", os.environ.get("ZOTERO_GROUP_ID", "")
        ).strip()
        if not api_key or not library_id:
            raise ZoteroAuthError(
                "缺少凭证：请配置 ZOTERO_API_KEY 与 ZOTERO_USER_ID（或 ZOTERO_GROUP_ID）"
            )
        return api_key, library_type, library_id

    def _library_prefix(self) -> str:
        _, library_type, library_id = self._credentials()
        return f"/{library_type}s/{library_id}"

    def _request(self, method: str, path: str, *, data: Any = None) -> Any:
        api_key, _, _ = self._credentials()
        url = f"{self.base_url}{path}"
        headers = {"Zotero-API-Key": api_key, "Content-Type": "application/json"}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise ZoteroAuthError(
                f"Zotero API {method} {path} -> {e.code}: {detail}"
            ) from e

    def search(self, q: str, item_type: str | None = None, limit: int = 25) -> dict[str, Any]:
        """在文献库中检索条目。"""
        prefix = self._library_prefix()
        params: dict[str, Any] = {"q": q, "limit": limit, "itemType": "-attachment"}
        if item_type:
            params["itemType"] = item_type
        qs = urllib.parse.urlencode(params)
        data = self._request("GET", f"{prefix}/items?{qs}")
        return {"ok": True, "count": len(data), "items": data}

    def create_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """批量创建条目（导入）。"""
        prefix = self._library_prefix()
        data = self._request("POST", f"{prefix}/items", data=items)
        return {"ok": True, "created": data}

    def annotate(self, item_key: str, note: str, tags: list[str] | None = None) -> dict[str, Any]:
        """为条目追加方向标注（子笔记 + 可选标签）。"""
        prefix = self._library_prefix()
        child: dict[str, Any] = {"itemType": "note", "parentItem": item_key, "note": note}
        if tags:
            child["tags"] = [{"tag": t} for t in tags]
        data = self._request("POST", f"{prefix}/items/{item_key}/children", data=[child])
        return {"ok": True, "annotation": data}

    def library_status(self) -> dict[str, Any]:
        """库可达性探测。"""
        prefix = self._library_prefix()
        data = self._request("GET", f"{prefix}/items?limit=1")
        return {"ok": True, "reachable": True, "probe_items": data}
