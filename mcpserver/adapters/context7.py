"""Context7 MCP 适配层（写码防 API 幻觉，按需拉最新库文档）。

上游服务: https://context7.com（Upstash，GitHub: upstash/context7，MIT）
纯 HTTP 实现（stdlib urllib），不引入 Node/npm 依赖。

两段式调用（每段请求各 3 秒超时，超时/失败降级为空结果）：
1. GET /api/v1/search?query={lib}      → 取相关度第一的库 id（如 /websites/fastapi_tiangolo）
2. GET /api/v1{lib_id}?topic={query}&type=txt → markdown 文档，按分隔线切片取前 limit 段

降级策略：无网络 / 超时 / 空结果 → 返回 {"ok": False, "docs": []}，绝不抛错
（写码场景文档缺失只是少一条参考，不应中断主流程）。
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from mcpserver.adapters._common import register_capability_safe

logger = logging.getLogger(__name__)

CAPABILITY: dict = {
    "name": "context7",
    "displayName": "Context7 库文档查询",
    "description": "按需拉取最新第三方库官方文档片段（写码前查真实 API，防幻觉）。",
    "version": "1.0.0",
    "license": "MIT",
    "vendor": "upstash/context7",
    "degradation_mode": "fail-to-empty-docs-never-raise",
    "_from_adapter": "context7",
}

# 每段 HTTP 请求的超时（search 与 docs 各自计时；实测 docs 段 35KB 响应约 3s，
# 所以不做两段共享总预算——那会把正常请求误杀成降级）；可被环境变量覆盖（测试/代理场景）
_REQUEST_TIMEOUT_S = 3.0
# docs 响应里的片段分隔线（context7 txt 格式固定 32 个连字符）
_SNIPPET_SEP = "--------------------------------"
_MAX_LIMIT = 10


def _api_base() -> str:
    """Context7 API 基址（默认官方端点，环境变量 CONTEXT7_API_BASE 可覆盖）。"""
    import os
    return os.environ.get("CONTEXT7_API_BASE", "https://context7.com/api/v1").rstrip("/")


def healthcheck() -> bool:
    """纯 stdlib HTTP 适配，无本地依赖/凭证要求，恒可用。

    网络可达性不在 healthcheck 探测（探测会拖慢启动且离线开发时误杀注册）；
    无网络降级发生在工具调用时（返回空 docs，不抛错）。
    """
    return True


def _request_timeout() -> float:
    """单段请求超时（CONTEXT7_TIMEOUT_S 环境变量可覆盖，测试用）。"""
    import os
    try:
        return max(0.5, float(os.environ.get("CONTEXT7_TIMEOUT_S", _REQUEST_TIMEOUT_S)))
    except ValueError:
        return _REQUEST_TIMEOUT_S


def _http_get(url: str, timeout: float) -> str:
    """GET 并返回响应文本。任何网络层异常向上抛，由 query_docs 统一降级。"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "scratchpad-mcp-context7-adapter/1.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _split_snippets(docs_text: str, limit: int) -> list[str]:
    """按分隔线切文档为片段，取前 limit 段（去空白行、丢空段）。"""
    snippets = [s.strip() for s in docs_text.split(_SNIPPET_SEP)]
    return [s for s in snippets if s][:limit]


def query_docs_impl(lib: str, query: str, limit: int = 3) -> dict[str, Any]:
    """同步实现：lib 库名 → search 定位库 id → 拉 topic 相关文档片段。

    返回 {"ok": True, "docs": [...]}；任何失败返回 {"ok": False, "docs": [], "error": ...}。
    """
    limit = max(1, min(int(limit or 3), _MAX_LIMIT))
    timeout = _request_timeout()
    fail = lambda err: {"ok": False, "lib": lib, "query": query, "docs": [], "error": err}  # noqa: E731
    try:
        # 第一段：search 定位库 id
        search_url = f"{_api_base()}/search?{urllib.parse.urlencode({'query': lib})}"
        results = json.loads(_http_get(search_url, timeout))
        hits = results.get("results") or []
        if not hits:
            return fail(f"library not found: {lib}")
        best = hits[0]
        lib_id = str(best.get("id") or "").lstrip("/")
        if not lib_id:
            return fail(f"library id missing in search result: {lib}")

        # 第二段：按 topic 拉文档片段
        docs_url = (
            f"{_api_base()}/{lib_id}?"
            + urllib.parse.urlencode({"topic": query, "type": "txt"})
        )
        docs_text = _http_get(docs_url, timeout)
        snippets = _split_snippets(docs_text, limit)
        if not snippets:
            return fail("empty docs response")
        return {
            "ok": True,
            "lib": lib,
            "library_id": f"/{lib_id}",
            "library_title": best.get("title", lib),
            "query": query,
            "docs": snippets,
            "count": len(snippets),
        }
    except Exception as e:  # 无网络/超时/DNS/JSON 解析等一律降级为空结果
        logger.info("[adapter:context7] query_docs 降级（lib=%s query=%s）: %s", lib, query, e)
        return fail(str(e) or type(e).__name__)


async def context7_query_docs(lib: str, query: str, limit: int = 3) -> dict[str, Any]:
    """查询第三方库的最新官方文档片段（Context7），写码前核对真实 API 防幻觉。

    Args:
        lib: 库名（如 "fastapi"、"react"），内部自动 search 匹配最相关库
        query: 主题关键词（如 "streaming response"、"middleware"）
        limit: 返回片段条数 1-10，默认 3

    Returns:
        {"ok": True, "docs": [文档片段...]}；无网络/超时/未找到库 →
        {"ok": False, "docs": [], "error": 原因}（永不抛错）
    """
    return query_docs_impl(lib, query, limit)


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册 context7_query_docs 工具 + 登记能力卡片（manifest 含 license 字段）。"""
    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(context7_query_docs, name="context7_query_docs")
    else:
        logger.warning("[adapter:context7] mcp_server 无 add_tool，工具未挂载（能力卡仍登记）")
    register_capability_safe(mcp_registry, dict(CAPABILITY))
