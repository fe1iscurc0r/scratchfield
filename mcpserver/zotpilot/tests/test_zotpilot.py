"""zotpilot 封装单测（无网络，FakeClient 注入）。"""
from __future__ import annotations

import json
from pathlib import Path

from mcpserver.zotpilot.bridge import ZotPilotBridge
from mcpserver.zotpilot.zotero_client import ZoteroAuthError, ZoteroClient


class FakeClient(ZoteroClient):
    """注入假响应的 Zotero 客户端，不发真实 HTTP。"""

    def __init__(self, responses: list | None = None, raise_auth: bool = False):
        super().__init__(base_url="https://test.invalid")
        self.responses = responses or []
        self.raise_auth = raise_auth
        self.calls: list[tuple[str, str, object]] = []

    def _credentials(self):
        if self.raise_auth:
            raise ZoteroAuthError("缺少凭证")
        return ("test-key", "user", "12345")

    def _request(self, method, path, *, data=None):
        self.calls.append((method, path, data))
        if self.raise_auth:
            raise ZoteroAuthError("401 unauthorized")
        return self.responses.pop(0) if self.responses else []


def _run(bridge, tool_name, **params):
    import asyncio

    return asyncio.run(bridge.handle_handoff({**{"tool_name": tool_name}, **params}))


def test_manifest_license_and_entrypoint():
    manifest_path = Path(__file__).resolve().parents[1] / "agent-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "MIT" in manifest["license"]
    assert "ZotPilot" in manifest["license"]  # 许可标注
    assert manifest["entryPoint"]["module"] == "mcpserver.zotpilot.bridge"
    assert manifest["entryPoint"]["class"] == "ZotPilotBridge"
    commands = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert {"zotpilot_search", "zotpilot_import", "zotpilot_annotate", "zotpilot_status"} <= commands


def test_search_ok():
    bridge = ZotPilotBridge(client=FakeClient(responses=[[{"key": "A1", "data": {}}]]))
    out = json.loads(_run(bridge, "zotpilot_search", q="lignin", limit=10))
    assert out["status"] == "ok"
    assert out["result"]["count"] == 1
    method, path, _ = bridge.client.calls[-1]
    assert method == "GET"
    assert "/users/12345/items" in path
    assert "q=lignin" in path


def test_import_posts_items():
    client = FakeClient(responses=[[{"key": "B1"}]])
    bridge = ZotPilotBridge(client=client)
    items = [{"itemType": "journalArticle", "title": "t"}]
    out = json.loads(_run(bridge, "zotpilot_import", items=items))
    assert out["status"] == "ok"
    method, path, data = client.calls[-1]
    assert method == "POST"
    assert data == items


def test_annotate_parses_tags():
    client = FakeClient(responses=[[{"key": "N1"}]])
    bridge = ZotPilotBridge(client=client)
    out = json.loads(_run(bridge, "zotpilot_annotate", item_key="ABCD1234", note="生物质", tags="陆墨,P0"))
    assert out["status"] == "ok"
    _, path, data = client.calls[-1]
    assert "ABCD1234/children" in path
    assert data == [{"itemType": "note", "parentItem": "ABCD1234", "note": "生物质",
                     "tags": [{"tag": "陆墨"}, {"tag": "P0"}]}]


def test_status_unconfigured_no_crash():
    bridge = ZotPilotBridge(client=FakeClient(raise_auth=True))
    out = json.loads(_run(bridge, "zotpilot_status"))
    assert out["status"] == "ok"
    assert out["result"]["configured"] is False


def test_search_auth_required():
    bridge = ZotPilotBridge(client=FakeClient(raise_auth=True))
    out = json.loads(_run(bridge, "zotpilot_search", q="x"))
    assert out["status"] == "error"
    assert out["error_type"] == "auth_required"


def test_unknown_tool():
    bridge = ZotPilotBridge(client=FakeClient())
    out = json.loads(_run(bridge, "zotpilot_nope"))
    assert out["status"] == "ok"
    assert out["result"]["ok"] is False
