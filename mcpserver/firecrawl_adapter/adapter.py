"""firecrawl MCP 桥 — FirecrawlBridge（agent-manifest.json entryPoint）。

工具（3 个）：
- firecrawl_scrape_to_md(url)：单页 → markdown 正文（自托管优先，云 API fallback）
- firecrawl_enrich_rss(item_url, title, source)：RSS 摘要条目 → 全文落盘并返回路径
- firecrawl_health()：自托管可达性 + 云 key 是否存在

fail-fast：url 空 / 抓取失败 / 正文为空 一律返回 {"status":"error", ...}，
绝不静默返回空正文（空正文对下游知识库无意义）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from mcpserver.firecrawl_adapter.client import FirecrawlClient, FirecrawlError

logger = logging.getLogger(__name__)


def default_inbox() -> Path:
    """全文落地目录：<repo>/knowledge-base/inbox（与既有知识库目录同策略）。"""
    repo = Path(__file__).resolve().parents[2]
    return repo / "knowledge-base" / "inbox"


def _slug(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(text or "")).strip("-")
    return (s[:limit] or "untitled")


class FirecrawlBridge:
    """MCP 桥：把 Firecrawl 抓取包成可调用工具面。"""

    def __init__(self, client: FirecrawlClient | None = None,
                 inbox: str | Path | None = None):
        self._client = client
        self._inbox = Path(inbox) if inbox else None

    @property
    def client(self) -> FirecrawlClient:
        if self._client is None:
            self._client = FirecrawlClient()
        return self._client

    @property
    def inbox(self) -> Path:
        if self._inbox is None:
            self._inbox = default_inbox()
        self._inbox.mkdir(parents=True, exist_ok=True)
        return self._inbox

    # -------------------------------------------------- 工具

    def firecrawl_scrape_to_md(self, url: str = "", only_main_content: bool = True,
                               allow_cloud_fallback: bool = True, **_: Any) -> dict:
        """单页 → markdown 正文。"""
        if not str(url or "").strip():
            return {"status": "error", "error": "empty_url", "detail": "url 必填"}
        try:
            r = self.client.scrape_to_md(
                str(url).strip(), only_main_content=bool(only_main_content),
                allow_cloud_fallback=bool(allow_cloud_fallback))
            return {"status": "ok", **r.to_dict()}
        except FirecrawlError as e:
            return {"status": "error", "error": "scrape_failed", "detail": str(e)[:300]}
        except Exception as e:  # 兜底：任何异常都不静默
            return {"status": "error", "error": "unexpected", "detail": str(e)[:300]}

    def firecrawl_enrich_rss(self, item_url: str = "", title: str = "",
                             source: str = "", **_: Any) -> dict:
        """RSS 摘要条目 → 抓全文 → 落盘 knowledge-base/inbox/<slug>.md。

        落盘内容带 YAML front-matter（source/title/url/fetched_at），
        供后续实体抽取（卷142）与知识库检索消费。
        """
        if not str(item_url or "").strip():
            return {"status": "error", "error": "empty_url",
                    "detail": "item_url 必填"}
        try:
            r = self.client.scrape_to_md(str(item_url).strip())
        except FirecrawlError as e:
            return {"status": "error", "error": "scrape_failed", "detail": str(e)[:300]}
        except Exception as e:
            return {"status": "error", "error": "unexpected", "detail": str(e)[:300]}

        stamp = time.strftime("%Y-%m-%d")
        name = f"{stamp}-{_slug(title or r.title or item_url)}.md"
        path = self.inbox / name
        fm = [
            "---",
            f"source: {source or 'rss'}",
            f"title: {title or r.title}",
            f"url: {r.url or item_url}",
            f"fetched_at: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
            f"route: {r.route}",
            "---",
            "",
        ]
        path.write_text("\n".join(fm) + r.markdown, encoding="utf-8")
        return {"status": "ok", "path": str(path), "chars": len(r.markdown),
                "route": r.route, "title": title or r.title}

    def firecrawl_health(self, **_: Any) -> dict:
        """自托管可达性 + 云 key 状态（不发抓取请求）。"""
        return {"status": "ok", **self.client.health()}

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """类方法入口（总线契约）：按 tool 名分发到本类工具方法。

        注册表运行时按 instance.handle_handoff 调用（Format A: {module, class}），
        task 格式 {"tool": ..., "params": {...}}；工具方法均带 **_ 兜底，
        未知参数键不崩。返回 JSON 字符串。
        """
        tool = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
        params = tool_call.get("params")
        if not isinstance(params, dict):
            params = {}
        dispatcher: dict[str, Any] = {
            "firecrawl_scrape_to_md": self.firecrawl_scrape_to_md,
            "firecrawl_enrich_rss": self.firecrawl_enrich_rss,
            "firecrawl_health": self.firecrawl_health,
        }
        handler = dispatcher.get(tool)
        if handler is None:
            result: dict[str, Any] = {
                "status": "error",
                "error": f"unknown_tool: {tool}",
                "available": sorted(dispatcher),
            }
        else:
            result = handler(**params)
        return json.dumps(result, ensure_ascii=False, default=str)
