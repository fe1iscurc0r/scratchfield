"""本地网页搜索回退（卷112 W112-02）。

Naga 登录态与 Brave key 都缺失时，/tools/search 原先直接 401「未登录且
未配置搜索服务」——本地实测确认这是 Lumo web_search「没用」的根因（请求
在入口即被拦死，三级回退链从未生效）。本模块提供纯本地回退：直接请求
Bing 网页搜索端点并解析结果，零 key、零登录、零外部服务。

境内网络实测：html.duckduckgo.com 连接超时（不可达），www.bing.com 可
正常返回（302→cn.bing.com，10 个结果块），故回退源选 Bing。

SSRF 防护：请求目标为固定 https 域名字面量；用户查询词仅作为 query
参数传入（httpx params 编码），不进 URL 路径、不参与域名解析决策。
"""
from __future__ import annotations

import html
import re
from typing import Any

import httpx

# 固定端点（字面量域名，不随输入变化；Bing 会 302 到 cn.bing.com，需跟随）
_SEARCH_URL = "https://www.bing.com/search"

# 与 Lumo 各下游（travel_service 等）一致的浏览器 UA
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Bing 结果块：<li class="b_algo"> ... <h2><a href="...">标题</a></h2> <p>摘要</p> ... </li>
_ALGO_BLOCK_RE = re.compile(r'<li class="b_algo".*?</li>', re.DOTALL)
_LINK_RE = re.compile(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_SNIPPET_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_bing_html(page_html: str, count: int = 8) -> list[dict[str, str]]:
    """从 Bing 搜索结果页解析结果（纯函数，可离线测试）。"""
    results: list[dict[str, str]] = []
    for block in _ALGO_BLOCK_RE.findall(page_html):
        m = _LINK_RE.search(block)
        if not m:
            continue
        url = html.unescape(m.group(1)).strip()
        title = _strip_tags(m.group(2))
        if not url or not title:
            continue
        description = ""
        s = _SNIPPET_RE.search(block)
        if s:
            description = _strip_tags(s.group(1))
        results.append({"title": title, "url": url, "description": description})
        if len(results) >= count:
            break
    return results


async def search_local(query: str, count: int = 8, timeout: float = 15.0) -> dict[str, Any]:
    """本地搜索回退入口。返回与下游一致的 details 形状。

    失败（网络/解析）抛异常，由调用方决定回退策略；本函数不吞错。
    """
    headers = {"User-Agent": BROWSER_UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    async with httpx.AsyncClient(
        timeout=timeout,
        proxy=None,
        trust_env=False,
        follow_redirects=True,
    ) as client:
        resp = await client.get(_SEARCH_URL, params={"q": query}, headers=headers)
        resp.raise_for_status()
    results = parse_bing_html(resp.text, count=count)
    if not results:
        raise RuntimeError("本地搜索未解析到任何结果")
    return {
        "query": query,
        "results": results,
    }
