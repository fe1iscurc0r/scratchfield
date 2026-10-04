# -*- coding: utf-8 -*-
"""卷140 测试：Firecrawl 抓取适配器（全部离线，HTTP 传输注入假函数）。"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcpserver.firecrawl_adapter.adapter import FirecrawlBridge  # noqa: E402
from mcpserver.firecrawl_adapter.client import (  # noqa: E402
    FirecrawlClient,
    FirecrawlError,
)


def ok_body(md="## 标题\n\n正文内容", title="示例页", url="https://example.com"):
    return json.dumps({"success": True, "data": {
        "markdown": md, "metadata": {"title": title, "sourceURL": url, "statusCode": 200}}})


class FakeTransport:
    """可编排的假传输：记录调用，按 URL 前缀给不同应答。"""

    def __init__(self, self_host_status=200, self_host_body=None,
                 cloud_status=200, cloud_body=None, raise_on_self_host=False):
        self.calls = []
        self.self_host_status = self_host_status
        self.self_host_body = self_host_body if self_host_body is not None else ok_body()
        self.cloud_status = cloud_status
        self.cloud_body = cloud_body if cloud_body is not None else ok_body(title="云", url="https://example.com")
        self.raise_on_self_host = raise_on_self_host

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body})
        if "localhost" in url or "127.0.0.1" in url:
            if self.raise_on_self_host:
                raise OSError("connection refused")
            return self.self_host_status, self.self_host_body
        return self.cloud_status, self.cloud_body


class TestScrape(unittest.TestCase):
    def test_self_host_happy_path(self):
        t = FakeTransport()
        c = FirecrawlClient(self_host_url="http://localhost:3002", transport=t)
        r = c.scrape_to_md("https://example.com")
        self.assertTrue(r.ok)
        self.assertEqual(r.route, "self-host")
        self.assertIn("正文内容", r.markdown)
        self.assertEqual(r.title, "示例页")
        # 请求体符合官方文档形状
        body = t.calls[0]["body"]
        self.assertEqual(body["url"], "https://example.com")
        self.assertEqual(body["formats"], ["markdown"])
        self.assertTrue(body["onlyMainContent"])
        # 自托管不带 Authorization
        self.assertNotIn("Authorization", t.calls[0]["headers"])

    def test_empty_markdown_fails_fast(self):
        """正文为空 → 报错，不静默返回空（工单要求）。"""
        t = FakeTransport(self_host_body=json.dumps(
            {"success": True, "data": {"markdown": "   ", "metadata": {}}}))
        c = FirecrawlClient(transport=t, api_key="")
        with self.assertRaises(FirecrawlError) as ctx:
            c.scrape_to_md("https://example.com", allow_cloud_fallback=False)
        self.assertIn("正文为空", str(ctx.exception))

    def test_http_error_raises(self):
        t = FakeTransport(self_host_status=502, self_host_body="bad gateway")
        c = FirecrawlClient(transport=t)
        with self.assertRaises(FirecrawlError) as ctx:
            c.scrape_to_md("https://x.com", allow_cloud_fallback=False)
        self.assertIn("HTTP 502", str(ctx.exception))

    def test_success_false_raises(self):
        t = FakeTransport(self_host_body=json.dumps({"success": False, "error": "blocked"}))
        c = FirecrawlClient(transport=t)
        with self.assertRaises(FirecrawlError):
            c.scrape_to_md("https://x.com", allow_cloud_fallback=False)

    def test_unreachable_no_key_reports_both_paths(self):
        """自托管不可达且无 key → 错误信息必须说清两条路都没通（不静默降级）。"""
        t = FakeTransport(raise_on_self_host=True)
        c = FirecrawlClient(transport=t, api_key="")
        with self.assertRaises(FirecrawlError) as ctx:
            c.scrape_to_md("https://x.com")
        msg = str(ctx.exception)
        self.assertIn("自托管不可达", msg)
        self.assertIn("FIRECRAWL_API_KEY", msg)

    def test_cloud_fallback_marks_route(self):
        t = FakeTransport(raise_on_self_host=True)
        c = FirecrawlClient(transport=t, api_key="fc-test-key")
        r = c.scrape_to_md("https://x.com")
        self.assertEqual(r.route, "cloud")
        self.assertIn("回落到云 API", r.warning)
        # 云路线必须带 Bearer
        cloud_call = [x for x in t.calls if "localhost" not in x["url"]][0]
        self.assertEqual(cloud_call["headers"]["Authorization"], "Bearer fc-test-key")

    def test_empty_url_raises(self):
        c = FirecrawlClient(transport=FakeTransport())
        for bad in ("", "   "):
            with self.assertRaises(FirecrawlError):
                c.scrape_to_md(bad)

    def test_timeout_clamped(self):
        t = FakeTransport()
        c = FirecrawlClient(transport=t)
        c.scrape_to_md("https://x.com", timeout_ms=999999)
        self.assertLessEqual(t.calls[0]["body"]["timeout"], 300000)


class TestBridge(unittest.TestCase):
    def _bridge(self, transport=None):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = FirecrawlClient(transport=transport or FakeTransport(), api_key="")
        return FirecrawlBridge(client=c, inbox=Path(tmp.name) / "inbox")

    def test_scrape_tool(self):
        b = self._bridge()
        r = b.firecrawl_scrape_to_md(url="https://example.com")
        self.assertEqual(r["status"], "ok")
        self.assertGreater(r["chars"], 0)

    def test_scrape_tool_fail_fast(self):
        b = self._bridge(FakeTransport(self_host_status=500, self_host_body="err"))
        r = b.firecrawl_scrape_to_md(url="https://example.com", allow_cloud_fallback=False)
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["error"], "scrape_failed")

    def test_scrape_tool_empty_url(self):
        b = self._bridge()
        r = b.firecrawl_scrape_to_md(url="")
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["error"], "empty_url")

    def test_enrich_rss_writes_file_with_frontmatter(self):
        b = self._bridge()
        r = b.firecrawl_enrich_rss(item_url="https://example.com/post",
                                   title="水凝胶新进展", source="materials-rss")
        self.assertEqual(r["status"], "ok")
        p = Path(r["path"])
        self.assertTrue(p.exists(), "全文应落盘")
        text = p.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"), "应带 YAML front-matter")
        self.assertIn("source: materials-rss", text)
        self.assertIn("水凝胶新进展", text)
        self.assertIn("正文内容", text)
        # 文件名带日期前缀 + 标题 slug
        self.assertRegex(p.name, r"^\d{4}-\d{2}-\d{2}-")

    def test_enrich_rss_fail_fast_on_scrape_error(self):
        b = self._bridge(FakeTransport(raise_on_self_host=True))
        r = b.firecrawl_enrich_rss(item_url="https://example.com/x")
        self.assertEqual(r["status"], "error")

    def test_health_reports_state(self):
        # 明确清空环境变量，避免本机 env 干扰「无 key 应报 False」的断言
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": ""}, clear=False):
            b = self._bridge()
            h = b.firecrawl_health()
        self.assertEqual(h["status"], "ok")
        self.assertIn("reachable", h)
        self.assertFalse(h["cloud_key_present"], "无 key 时应如实报 False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
