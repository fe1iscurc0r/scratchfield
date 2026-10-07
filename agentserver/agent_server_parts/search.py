"""agent_server_parts.search —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import logger  # noqa: F401

_search_http_client: httpx.AsyncClient | None = None


def _get_search_client() -> httpx.AsyncClient:
    """搜索代理共享 httpx 客户端"""

    global _search_http_client
    if _search_http_client is None or _search_http_client.is_closed:
        _search_http_client = httpx.AsyncClient(timeout=30.0, proxy=None)
    return _search_http_client


async def _local_search_proxy(args: dict[str, Any]) -> dict[str, Any]:
    """
    本地搜索代理：拦截 web_search 请求，走 Naga 或 Brave，不转发给 OpenClaw。
    返回 MCP 工具结果格式 { success, result: { content: [...] } }
    """
    query = args.get("query", "") or args.get("q", "")
    count = args.get("count", 10) or args.get("limit", 10)
    freshness = args.get("freshness")

    if not query:
        return {"success": False, "error": "缺少搜索关键词 (query)"}

    try:
        # 陆墨定制：统一使用 Brave Search API（本地模式，无Naga依赖）
        api_key = config.online_search.search_api_key
        if not api_key:
            return {"success": False, "error": "未配置 search_api_key，无法搜索"}
        api_base = config.online_search.search_api_base
        params = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness
        client = _get_search_client()
        resp = await client.get(
            api_base,
            params=params,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        source = "brave"

        if resp.status_code != 200:
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message", "") if isinstance(err.get("error"), dict) else str(err)
            except Exception:
                msg = f"HTTP {resp.status_code}"
            logger.warning(f"[搜索代理] {source} 搜索失败: {msg}")
            return {"success": False, "error": f"搜索失败: {msg}"}

        data = resp.json()
        results = data.get("web", {}).get("results", [])

        # 格式化为可读文本
        if not results:
            text = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', '')}")
                lines.append(f"   URL: {r.get('url', '')}")
                if r.get("description"):
                    lines.append(f"   摘要: {r['description']}")
                if r.get("age"):
                    lines.append(f"   时间: {r['age']}")
                lines.append("")
            text = "\n".join(lines)

        logger.info(f"[搜索代理] {source} 搜索完成: query=\"{query}\", 结果数={len(results)}")

        # 返回 MCP 工具结果格式
        return {
            "success": True,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    except Exception as e:
        logger.error(f"[搜索代理] 搜索异常: {e}")
        return {"success": False, "error": f"搜索异常: {e}"}
