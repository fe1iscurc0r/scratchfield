"""zotpilot 文献管理 MCP 桥 —— ZotPilotBridge（agent-manifest.json entryPoint）。

封装 ZotPilot（xunhe730/ZotPilot，MIT）的文献管理能力面：
- zotpilot_search    文献搜索
- zotpilot_import    批量导入
- zotpilot_annotate  方向标注（笔记 + 标签）
- zotpilot_status    状态 / 凭证检查

凭证缺失时返回 auth_required 标准错误（不 crash）；上游许可 MIT，
已在 agent-manifest.json 的 license 字段标注。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcpserver.zotpilot.zotero_client import ZoteroAuthError, ZoteroClient

logger = logging.getLogger(__name__)


class ZotPilotBridge:
    """zotpilot 文献管理 MCP 服务实例。"""

    def __init__(self, client: ZoteroClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> ZoteroClient:
        if self._client is None:
            self._client = ZoteroClient()
        return self._client

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {
            k: v
            for k, v in tool_call.items()
            if k not in ("service_name", "tool_name", "message", "session_id", "callback_url")
        }
        try:
            result = self._dispatch(tool_name, params)
        except ZoteroAuthError as e:
            return json.dumps(
                {"status": "error", "error_type": "auth_required",
                 "service": "zotpilot", "tool": tool_name, "error": str(e)},
                ensure_ascii=False,
            )
        except Exception as e:  # noqa: BLE001 - 统一兜底，不让桥崩溃
            logger.warning("[zotpilot] %s 失败: %s", tool_name, e)
            return json.dumps(
                {"status": "error", "service": "zotpilot", "tool": tool_name, "error": str(e)},
                ensure_ascii=False,
            )
        return json.dumps(
            {"status": "ok", "service": "zotpilot", "tool": tool_name, "result": result},
            ensure_ascii=False,
        )

    def _dispatch(self, tool_name: str, p: dict[str, Any]) -> dict[str, Any]:
        client = self.client

        if tool_name == "zotpilot_search":
            return client.search(
                str(p.get("q", "")),
                item_type=p.get("item_type"),
                limit=int(p.get("limit", 25) or 25),
            )

        if tool_name == "zotpilot_import":
            items = p.get("items")
            if not isinstance(items, list):
                return {"ok": False, "error": "items 必须是 JSON 数组"}
            return client.create_items(items)

        if tool_name == "zotpilot_annotate":
            tags = p.get("tags")
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            return client.annotate(
                str(p.get("item_key", "")), str(p.get("note", "")), tags
            )

        if tool_name == "zotpilot_status":
            try:
                return client.library_status()
            except ZoteroAuthError as e:
                return {"ok": True, "configured": False, "reason": str(e)}

        return {"ok": False, "error": f"未知工具: {tool_name}"}
