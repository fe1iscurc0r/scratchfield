"""B2 Context7 适配层离线单元测试（不依赖实网，urlopen 全 mock）。

验收对应：
- register() 挂载 context7_query_docs + 能力卡（含 license 字段）
- 成功路径：search → docs → limit 切片
- 降级路径：URLError / socket.timeout / 库未找到 / 空 docs → ok=False + docs=[] 不抛错
- validate_adapter 契约 + _ADAPTERS 注册表纳入
"""
from __future__ import annotations

import json
import logging
import socket
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scratchpad/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.ERROR)

from mcpserver import mcp_registry  # noqa: E402
from mcpserver.adapters import context7  # noqa: E402
from mcpserver.adapters._common import validate_adapter  # noqa: E402

_SEARCH_JSON = json.dumps({
    "results": [{"id": "/websites/fastapi_tiangolo", "title": "FastAPI", "score": 414.0}]
}).encode("utf-8")

_DOCS_TEXT = (
    "### StreamingResponse basics\nSource: https://fastapi.tiangolo.com/advanced/stream-data\n\n"
    "Use `fastapi.responses.StreamingResponse` for streaming.\n\n"
    + context7._SNIPPET_SEP + "\n\n"
    + "### AsyncIterable example\nasync def gen():\n    yield b'chunk'\n\n"
    + context7._SNIPPET_SEP + "\n\n"
    + "### Third snippet\nmore text\n\n"
    + context7._SNIPPET_SEP + "\n\n"
    + "### Fourth snippet\nshould be cut by limit\n"
).encode("utf-8")


class _FakeResp:
    """urlopen 返回的上下文管理器假响应。"""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeServer:
    def __init__(self):
        self.captured = {}

    def add_tool(self, fn, name=None):
        self.captured[name or getattr(fn, "__name__", "?")] = fn


class Context7AdapterTest(unittest.TestCase):
    def setUp(self):
        mcp_registry.clear_registry()
        self.env_patcher = mock.patch.dict(
            "os.environ", {}, clear=False)  # 占位；各用例自行设 CONTEXT7_API_BASE
        self.env_patcher.start()
        os_environ = __import__("os").environ
        os_environ.pop("CONTEXT7_API_BASE", None)
        self.addCleanup(self.env_patcher.stop)
        self.addCleanup(mcp_registry.clear_registry)

    # ---------- 契约与注册 ----------
    def test_validate_adapter_contract(self):
        """纳入门禁：三要素 + CAPABILITY 六必需字段（含 license）+ name 对齐。"""
        issues = validate_adapter(context7, "context7")
        self.assertEqual(issues, [], f"context7 应通过契约校验，问题: {issues}")

    def test_capability_contains_license(self):
        """硬约束：manifest/CAPABILITY 必须含 license 字段。"""
        self.assertEqual(context7.CAPABILITY["license"], "MIT")
        self.assertEqual(context7.CAPABILITY["name"], "context7")

    def test_healthcheck_always_true(self):
        """纯 stdlib HTTP 无本地依赖，healthcheck 恒 True 且不做网络探测。"""
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("healthcheck 不得发网络请求")):
            self.assertTrue(context7.healthcheck())

    def test_register_adds_tool_and_capability_card(self):
        """register()：工具挂载 + 能力卡登记（license 字段进入 registry）。"""
        server = _FakeServer()
        context7.register(server, mcp_registry=mcp_registry)
        self.assertIn("context7_query_docs", server.captured)
        caps = [c for c in mcp_registry.list_registered_capabilities() if c["name"] == "context7"]
        self.assertEqual(len(caps), 1)
        self.assertEqual(caps[0]["license"], "MIT")
        self.assertEqual(caps[0]["source"], "adapter")

    def test_registered_in_adapters_table(self):
        """context7 已纳入 adapters/__init__.py 的 _ADAPTERS 注册表（带独立开关）。"""
        from mcpserver.adapters import _ADAPTERS
        self.assertIn("context7", _ADAPTERS)
        module_path, env_key = _ADAPTERS["context7"]
        self.assertEqual(module_path, "mcpserver.adapters.context7")
        self.assertEqual(env_key, "ENABLE_ADAPTER_CONTEXT7")

    # ---------- 成功路径 ----------
    def test_query_docs_success_slices_to_limit(self):
        """search → docs 两段请求，片段按分隔线切片取 limit 条。"""
        responses = [_FakeResp(_SEARCH_JSON), _FakeResp(_DOCS_TEXT)]
        with mock.patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: responses.pop(0)):
            result = context7.query_docs_impl("fastapi", "streaming response", 3)
        self.assertTrue(result["ok"], f"应成功: {result}")
        self.assertEqual(result["library_id"], "/websites/fastapi_tiangolo")
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["docs"]), 3)
        self.assertIn("StreamingResponse", result["docs"][0])

    def test_query_docs_limit_clamped(self):
        """limit=99 钳到上限 10 以内（本地切片，无需更多响应数据）。"""
        responses = [_FakeResp(_SEARCH_JSON), _FakeResp(_DOCS_TEXT)]
        with mock.patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: responses.pop(0)):
            result = context7.query_docs_impl("fastapi", "anything", 99)
        self.assertTrue(result["ok"])
        self.assertLessEqual(result["count"], context7._MAX_LIMIT)
        self.assertEqual(result["count"], 4)  # 测试数据共 4 段

    # ---------- 降级路径（不抛错） ----------
    def test_query_docs_network_error_returns_empty(self):
        """URLError（无网络/DNS 失败）→ ok=False + docs=[] 不抛错。"""
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("name resolution failed")):
            result = context7.query_docs_impl("fastapi", "streaming", 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["docs"], [])
        self.assertIn("error", result)

    def test_query_docs_timeout_returns_empty(self):
        """socket.timeout（超时）→ ok=False + docs=[] 不抛错。"""
        with mock.patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            result = context7.query_docs_impl("fastapi", "streaming", 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["docs"], [])

    def test_query_docs_library_not_found(self):
        """search 空结果 → ok=False + 明确 error 信息。"""
        with mock.patch("urllib.request.urlopen",
                        return_value=_FakeResp(json.dumps({"results": []}).encode())):
            result = context7.query_docs_impl("no-such-lib-xyz", "q", 3)
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_query_docs_empty_docs_response(self):
        """docs 响应为空文本 → ok=False（空结果降级）。"""
        responses = [_FakeResp(_SEARCH_JSON), _FakeResp(b"")]
        with mock.patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: responses.pop(0)):
            result = context7.query_docs_impl("fastapi", "q", 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["docs"], [])

    def test_query_docs_docs_stage_failure_after_search_ok(self):
        """search 成功但 docs 段网络失败 → 整体降级 ok=False（不抛错）。"""
        responses = [_FakeResp(_SEARCH_JSON), urllib.error.URLError("connection reset")]
        def _side(req, timeout=None):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with mock.patch("urllib.request.urlopen", side_effect=_side):
            result = context7.query_docs_impl("fastapi", "q", 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["docs"], [])

    def test_api_base_env_override(self):
        """CONTEXT7_API_BASE 覆盖生效（测试/代理场景）。"""
        import os
        with mock.patch.dict(os.environ, {"CONTEXT7_API_BASE": "http://localhost:9999/api/v1"}):
            base = context7._api_base()
        self.assertEqual(base, "http://localhost:9999/api/v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
