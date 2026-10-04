"""Firecrawl 网页抓取 MCP 适配器（卷140）。

补 RSS 采集的"只有摘要、没有全文"缺口：单页 → 结构化 markdown，
落 knowledge-base/inbox/ 供知识库与实体抽取（卷142）消费。

许可：Firecrawl 本体 MIT（firecrawl/firecrawl-mcp-server 7491★）。
部署：优先自托管（Docker）；本机无 Docker（2026-09-20 实测），
故自托管部署层在本机不可执行，适配器侧以可配置 base_url + 云 fallback 兜住。
"""
from mcpserver.firecrawl_adapter.adapter import FirecrawlBridge, default_inbox
from mcpserver.firecrawl_adapter.client import (
    DEFAULT_CLOUD,
    DEFAULT_SELF_HOST,
    FirecrawlClient,
    FirecrawlError,
    ScrapeResult,
)

__all__ = [
    "DEFAULT_CLOUD",
    "DEFAULT_SELF_HOST",
    "FirecrawlBridge",
    "FirecrawlClient",
    "FirecrawlError",
    "ScrapeResult",
    "default_inbox",
]
