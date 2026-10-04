"""Firecrawl 客户端（卷140）——单页结构化抓取，自托管优先。

API 依据官方文档（2026-09-20 核实）：
  POST {base_url}/v2/scrape
  headers: Authorization: Bearer <token>（自托管可不校验）、Content-Type: application/json
  body:    {"url": ..., "formats": ["markdown"], "onlyMainContent": true, ...}
  响应:    {"success": bool, "data": {"markdown": str, "metadata": {...}}}

部署策略（工单要求「优先自托管」）：
  * 自托管：`FIRECRAWL_BASE_URL`（默认 http://localhost:3002 —— 自托管 Compose 常用端口，
    以你的 compose 配置为准）；自托管默认不校验 key。
  * 云 API：`FIRECRAWL_API_URL`（默认 https://api.firecrawl.dev）+ `FIRECRAWL_API_KEY`。
    仅在自托管不可达时作为 fallback，且会在返回里标注用了哪条路。

HTTP 传输可注入（`transport`），因此单元测试完全离线。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_SELF_HOST = "http://localhost:3002"
DEFAULT_CLOUD = "https://api.firecrawl.dev"

# 传输层签名：(url, headers, body_dict, timeout) -> (status_code, text)
Transport = Callable[[str, dict, dict, float], tuple[int, str]]


class FirecrawlError(Exception):
    """抓取链路的显式失败（fail-fast，绝不静默返回空正文）。"""


@dataclass
class ScrapeResult:
    ok: bool
    markdown: str = ""
    title: str = ""
    url: str = ""
    status_code: int = 0
    route: str = ""          # "self-host" | "cloud"
    elapsed_ms: float = 0.0
    warning: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "markdown": self.markdown, "title": self.title,
            "url": self.url, "status_code": self.status_code, "route": self.route,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "warning": self.warning, "chars": len(self.markdown),
        }


def _urllib_transport(url: str, headers: dict, body: dict, timeout: float) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class FirecrawlClient:
    """Firecrawl 抓取客户端（自托管优先，云 API fallback）。"""

    def __init__(self, self_host_url: str | None = None,
                 cloud_url: str | None = None, api_key: str | None = None,
                 timeout: float = 60.0, transport: Transport | None = None):
        self.self_host_url = (self_host_url
                              or os.environ.get("FIRECRAWL_BASE_URL")
                              or DEFAULT_SELF_HOST).rstrip("/")
        self.cloud_url = (cloud_url
                          or os.environ.get("FIRECRAWL_API_URL")
                          or DEFAULT_CLOUD).rstrip("/")
        # key 只在内存中用；不落任何文件
        self.api_key = api_key or os.environ.get("FIRECRAWL_API_KEY") or ""
        self.timeout = timeout
        self._transport = transport or _urllib_transport

    # ------------------------------------------------ 内部

    def _post(self, route: str, payload: dict) -> ScrapeResult:
        base = self.self_host_url if route == "self-host" else self.cloud_url
        headers = {"User-Agent": "lumo-firecrawl-adapter/0.1"}
        if route == "cloud":
            if not self.api_key:
                raise FirecrawlError("云 API 路线需要 FIRECRAWL_API_KEY（自托管则不需要）")
            headers["Authorization"] = f"Bearer {self.api_key}"
        t0 = time.perf_counter()
        try:
            status, text = self._transport(
                f"{base}/v2/scrape", headers, payload, self.timeout)
        except Exception as e:
            # 传输层异常（连接被拒/DNS/超时）必须转成显式链路错误，
            # 否则调用方会收到未处理的 OSError——不符合 fail-fast 契约。
            raise FirecrawlError(f"{route} 不可达（{base}）: {type(e).__name__}: {e}") from e
        ms = (time.perf_counter() - t0) * 1000

        if status >= 400:
            raise FirecrawlError(f"{route} 抓取失败 HTTP {status}: {text[:200]}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise FirecrawlError(f"{route} 返回非 JSON: {text[:160]}") from e
        if not data.get("success"):
            raise FirecrawlError(f"{route} 返回 success=false: {str(data)[:200]}")
        d = data.get("data") or {}
        md = d.get("markdown") or ""
        if not md.strip():
            # 明确失败，不静默返回空（正文为空的抓取对下游无意义）
            raise FirecrawlError(f"{route} 抓取成功但正文为空（可能被反爬或页面为纯 JS）")
        meta = d.get("metadata") or {}
        return ScrapeResult(
            ok=True, markdown=md, title=str(meta.get("title", "")),
            url=str(meta.get("sourceURL") or meta.get("url") or payload.get("url", "")),
            status_code=int(meta.get("statusCode") or status), route=route,
            elapsed_ms=ms, warning=str(d.get("warning", "")), meta=meta)

    # ------------------------------------------------ 公开接口

    def scrape_to_md(self, url: str, only_main_content: bool = True,
                     formats: list[str] | None = None,
                     timeout_ms: int | None = None,
                     allow_cloud_fallback: bool = True) -> ScrapeResult:
        """单页 → markdown。自托管优先；不可达且允许时回落云 API。"""
        if not str(url or "").strip():
            raise FirecrawlError("url 必填")
        payload: dict[str, Any] = {
            "url": str(url).strip(),
            "formats": formats or ["markdown"],
            "onlyMainContent": bool(only_main_content),
        }
        if timeout_ms:
            payload["timeout"] = max(1000, min(int(timeout_ms), 300000))

        try:
            return self._post("self-host", payload)
        except FirecrawlError as e:
            if not allow_cloud_fallback:
                raise
            if not self.api_key:
                # 如实报错并指出两条路都没通（不静默降级）
                raise FirecrawlError(
                    f"自托管不可达（{e}）；云 API fallback 未启用（无 FIRECRAWL_API_KEY）。"
                    f"请先起自托管 Firecrawl 或配置 key。") from e
            try:
                result = self._post("cloud", payload)
            except FirecrawlError as e2:
                raise FirecrawlError(f"自托管与云 API 均失败：{e} / {e2}") from e2
            result.warning = (result.warning + " [回落到云 API]").strip()
            return result

    def health(self) -> dict:
        """自托管可达性（不发抓取请求，探根路径）。

        注意：HTTP 状态放在 `http_status`，不要用 `status` ——
        桥接层用 `status` 表示调用结果（ok/error），字段名撞车会互相覆盖。
        """
        try:
            code, _ = self._transport(f"{self.self_host_url}/v2/scrape",
                                      {"User-Agent": "lumo-firecrawl-adapter/0.1"},
                                      {"url": ""}, min(self.timeout, 5.0))
            # 4xx 也说明服务在（只是我们故意发了空 url）
            return {"self_host": self.self_host_url,
                    "reachable": code < 500, "http_status": code,
                    "cloud_key_present": bool(self.api_key)}
        except Exception as e:
            return {"self_host": self.self_host_url, "reachable": False,
                    "error": str(e)[:120], "cloud_key_present": bool(self.api_key)}
