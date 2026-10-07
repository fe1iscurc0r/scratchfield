"""M4 桥接：陆墨 agent 决策 → NEKO CUA/浏览器执行。

只做 HTTP 客户端 + 鉴权 + 结果回传。NEKO 侧沙箱/端点已就位（蓝图 M4 前置已满足）。
鉴权：NEKO_EXEC_TOKEN 环境变量，Bearer header，fail-safe（未配置返 error 不调用）。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from apiserver.config import settings

NEKO_AGENT_BASE = settings.neko_agent_base()
NEKO_EXEC_TOKEN = settings.neko_exec_token()

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=NEKO_AGENT_BASE.rstrip("/"), timeout=60.0)
    return _client


async def run_neko_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """调用 NEKO 执行端点。action ∈ {"computer_use", "browser_use"}。"""
    if action not in ("computer_use", "browser_use"):
        return {"success": False, "error": f"未知 action: {action}"}
    if not NEKO_EXEC_TOKEN:
        return {"success": False, "error": "NEKO_EXEC_TOKEN 未配置，拒绝调用（fail-safe）"}

    headers = {"Authorization": f"Bearer {NEKO_EXEC_TOKEN}"}
    path = f"/{action}/run"
    try:
        resp = await _get_client().post(path, json=payload, headers=headers)
        resp.raise_for_status()
        return {"success": True, "status": resp.status_code, **resp.json()}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"NEKO {action} HTTP {e.response.status_code}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"NEKO {action} 网络错误: {e}"}
