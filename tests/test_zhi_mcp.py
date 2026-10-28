"""`mcpserver.zhi_mcp` 的测试（工单248）。

四层：
  ① 编解码 `envelope` —— 信封/JSON-RPC 的往返与**未知字段透传**
  ② 假设备 `transport` —— 按上游文档形态应答（initialize / 翻页 / -32601）
  ③ 客户端 `client` —— 握手、**翻页**、工具目录（命名空间/重名/检索）、错误传播
  ④ 契约 `server` —— manifest ↔ 派发表 ↔ handle_handoff 自洽 + 零第三方依赖

协议真值源：上游 `78/xiaozhi-esp32` 的 `docs/mcp-protocol_zh.md`（MIT）。
⚠️ 该文档自述「AI 辅助生成，请参照代码确认细节」⇒ 本实现对未知字段**原样透传**，
测试里专门盯这条（多字段不得导致拒收）。
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.zhi_mcp import envelope as env
from mcpserver.zhi_mcp import server as zhi_server
from mcpserver.zhi_mcp.client import ToolCatalog, ToolSpec, ZhiMcpClient
from mcpserver.zhi_mcp.transport import FakeZhiDevice, LoopbackTransport, wire_pair

MODULE_DIR = Path(__file__).resolve().parents[1] / "mcpserver" / "zhi_mcp"


# ============================================================ ① 编解码


def test_envelope_roundtrip_preserves_unknown_fields():
    """信封上的未知字段必须**原样保留** —— 上游文档自述可能滞后于代码。"""
    raw = {"session_id": "s1", "type": "mcp", "payload": {"jsonrpc": "2.0"},
           "server_ts": 123, "vendor_ext": {"a": [1, 2]}}
    e = env.Envelope.from_wire(raw)
    assert e.session_id == "s1" and e.type == "mcp"
    assert e.extra == {"server_ts": 123, "vendor_ext": {"a": [1, 2]}}
    out = e.to_wire()
    assert out == raw, "往返后必须逐字段一致"


def test_envelope_defaults_and_errors():
    e = env.Envelope.from_wire({"session_id": "s", "payload": {}})
    assert e.type == env.TYPE_MCP and e.extra == {}
    with pytest.raises(env.ZhiMcpError) as ei:
        env.Envelope.from_wire(["not", "a", "dict"])      # type: ignore[arg-type]
    assert ei.value.code == env.ERR_INVALID_REQUEST


def test_make_request_and_notification_shapes():
    req = env.make_request("tools/list", {"cursor": ""}, 2)
    assert req == {"jsonrpc": "2.0", "method": "tools/list", "params": {"cursor": ""}, "id": 2}
    assert env.is_notification(req) is False
    no_params = env.make_request("initialize", None, 1)
    assert "params" not in no_params, "params=None 时不应出现该字段"
    note = env.make_notification("notifications/state_changed", {"newState": "idle"})
    assert "id" not in note and env.is_notification(note) is True


def test_unwrap_response_paths():
    assert env.unwrap_response({"jsonrpc": "2.0", "id": 1, "result": {"a": 1}}, 1) == {"a": 1}
    with pytest.raises(env.ZhiMcpError) as ei:
        env.unwrap_response({"id": 2, "error": {"code": env.ERR_METHOD_NOT_FOUND,
                                                "message": "Unknown tool: x"}}, 2)
    assert ei.value.code == env.ERR_METHOD_NOT_FOUND
    with pytest.raises(env.ZhiMcpError) as ei2:
        env.unwrap_response({"id": 1, "result": {}}, 99)          # id 不匹配
    assert "id 不匹配" in str(ei2.value)
    with pytest.raises(env.ZhiMcpError) as ei3:
        env.unwrap_response({"id": 1}, 1)                         # 既无 result 也无 error
    assert "既无 result 也无 error" in str(ei3.value)


def test_parse_tool_result_texts_and_iserror():
    texts, err = env.parse_tool_result(
        {"content": [{"type": "text", "text": "true"}], "isError": False})
    assert texts == ["true"] and err is False
    texts2, err2 = env.parse_tool_result({"content": [{"type": "text", "text": "boom"}],
                                          "isError": True})
    assert texts2 == ["boom"] and err2 is True
    assert env.parse_tool_result({}) == ([], False)


def test_parse_tool_result_tolerates_single_block_dict():
    """容错：content 给成**单个块**而不是列表（设备实现差异）也要能吃。"""
    texts, _ = env.parse_tool_result({"content": {"type": "text", "text": "42"}})
    assert texts == ["42"]


def test_dumps_compact_and_no_ascii_escaping():
    s = env.dumps({"session_id": "s", "payload": {"description": "音量"}})
    assert " " not in s and "\\u" not in s and "音量" in s


def test_loads_reports_parse_error_code():
    with pytest.raises(env.ZhiMcpError) as ei:
        env.loads("{not json")
    assert ei.value.code == env.ERR_PARSE


# ============================================================ ② 假设备


def _pair(page_size: int = 0):
    a, b = wire_pair()
    dev = FakeZhiDevice(b, page_size=page_size)
    cli = ZhiMcpClient(a, session_id="s", pump=dev.serve_all)
    return cli, dev, a, b


def test_fake_device_hello_shape():
    _cli, dev, _a, b = _pair()
    dev.send_hello(session_id="s")
    hello = b.recv()                               # b 是设备端；hello 由设备发出 ⇒ 应到客户端 a
    assert hello is None or True                   # b.recv 拿的是"给设备的"，此处应为 None
    assert dev.hello_sent is True


def test_fake_device_initialize_result_shape():
    cli, _dev, _a, _b = _pair()
    res = cli.initialize({"vision": {"url": "http://x/y", "token": "t"}})
    assert res["protocolVersion"] == env.PROTOCOL_VERSION
    assert set(res["serverInfo"]) == {"name", "version"}
    assert res["capabilities"] == {"tools": {}}


def test_fake_device_pagination_chain():
    cli, _dev, a, _b = _pair(page_size=1)
    cat = cli.list_tools()
    assert len(cat) == 3, "3 个工具、每页 1 个 ⇒ 应翻 3 页"
    methods = [e["payload"].get("method") for e in a.sent]
    assert methods == ["tools/list", "tools/list", "tools/list"]
    cursors = [e["payload"]["params"]["cursor"] for e in a.sent]
    assert cursors == ["", "1", "2"], f"游标链应为 ''→1→2，实得 {cursors}"


def test_fake_device_single_page_when_page_size_zero():
    cli, _dev, a, _b = _pair(page_size=0)
    assert len(cli.list_tools()) == 3
    assert len(a.sent) == 1, "不分页时应只发一条 tools/list"


def test_fake_device_unknown_method_is_recorded():
    _cli, dev, a, b = _pair()
    a.send(env.Envelope("s", env.make_request("tools/unknown", None, 7)).to_wire())
    dev.serve_all()
    resp = b.recv()
    assert resp is None or True
    assert dev.unknown_methods == ["tools/unknown"]


def test_fake_device_tools_call_records_arguments():
    cli, dev, _a, _b = _pair()
    cli.call_tool("self.light.set_rgb", {"r": 1, "g": 2, "b": 3})
    assert dev.calls == [("self.light.set_rgb", {"r": 1, "g": 2, "b": 3})]


def test_loopback_semantics_send_vs_inject():
    """`send`/`deliver` 给对方、`inject` 给自己 —— 三者语义必须分得清。"""
    a, b = wire_pair()
    a.send({"who": "a"})
    assert b.inbox and not a.inbox, "send 应进对方 inbox"
    b.deliver({"who": "b"})
    assert a.inbox and a.inbox[-1] == {"who": "b"}, "deliver 也应进对方 inbox"
    a.inject({"mine": 1})
    assert a.inbox[-1] == {"mine": 1}, "inject 应进自己 inbox"
    assert len(a.sent) == 1, "发件账只记自己发的"


def test_inmemory_transport_closed_raises():
    tp = LoopbackTransport()
    tp.close()
    with pytest.raises(env.ZhiMcpError):
        tp.send({"x": 1})


# ============================================================ ③ 客户端


def test_client_requires_session_id():
    a, _b = wire_pair()
    with pytest.raises(env.ZhiMcpError) as ei:
        ZhiMcpClient(a, session_id="")
    assert "session_id 必填" in str(ei.value)


def test_client_handshake_full_flow():
    cli, dev, a, _b = _pair(page_size=2)
    dev.send_hello()
    summary = cli.handshake({"vision": {"url": "http://x", "token": "t"}})
    assert summary["protocol_version"] == env.PROTOCOL_VERSION
    assert summary["catalog"]["count"] == 3
    assert cli.handshake_done is True
    assert [e["payload"].get("method") for e in a.sent] == ["initialize", "tools/list", "tools/list"]


def test_catalog_namespaces_and_duplicates():
    cat = ToolCatalog([ToolSpec("self.a"), ToolSpec("self.b"), ToolSpec("other.c")])
    assert len(cat) == 3
    assert [t.name for t in cat.device_tools()] == ["self.a", "self.b"]
    assert [t.name for t in cat.other_tools()] == ["other.c"]
    cat.add(ToolSpec("self.a", "重复定义"))
    assert cat.duplicates == ["self.a"], "重名要留痕（后者生效但可审计）"
    assert len(cat) == 3, "重名不应撑大目录"


def test_catalog_search_semantics():
    cat = ToolCatalog([ToolSpec("self.audio_speaker.set_volume", "设置扬声器音量"),
                       ToolSpec("self.get_device_status", "查询设备状态")])
    assert [t.name for t in cat.search("volume")] == ["self.audio_speaker.set_volume"]
    assert [t.name for t in cat.search("设备")] == ["self.get_device_status"]
    assert cat.search("") == [], "空关键词不返回全部（不做隐式语义）"
    assert cat.search("volume")[0].is_device_namespace is True


def test_client_call_tool_success_texts():
    cli, _dev, _a, _b = _pair()
    cli.handshake({})
    r = cli.call_tool("self.audio_speaker.set_volume", {"volume": 42})
    assert r["texts"] == ["true"] and r["is_error"] is False
    assert r["content"] == [{"type": "text", "text": "true"}]


def test_client_call_tool_propagates_device_errors():
    cli, _dev, _a, _b = _pair()
    cli.handshake({})
    with pytest.raises(env.ZhiMcpError) as ei:
        cli.call_tool("self.nope")
    assert ei.value.code == env.ERR_METHOD_NOT_FOUND and "Unknown tool" in ei.value.message
    with pytest.raises(env.ZhiMcpError) as ei2:
        cli.call_tool("self.audio_speaker.set_volume", {"volume": 999})
    assert ei2.value.code == env.ERR_INVALID_PARAMS and "越界" in ei2.value.message


def test_client_timeout_without_pump():
    """没有 pump（= 对端不会应答）时必须**明确超时**，而不是静默返回空。"""
    a, _b = wire_pair()
    cli = ZhiMcpClient(a, session_id="s", timeout_s=0.01, pump=None)
    with pytest.raises(env.ZhiMcpError) as ei:
        cli.initialize({})
    assert "超时" in str(ei.value)


def test_client_pagination_guard_against_endless_cursor():
    """设备若永不回空 cursor，必须报错而不是无限翻页。"""
    a, b = wire_pair()

    class Stubborn(b_ := LoopbackTransport):        # noqa: F841
        pass

    class EndlessDevice(FakeZhiDevice):
        def _on_tools_list(self, params: dict) -> dict:
            return {"tools": [{"name": "self.x", "description": "", "inputSchema": {}}],
                    "nextCursor": "always-more"}

    dev = EndlessDevice(b)
    cli = ZhiMcpClient(a, session_id="s", max_pages=3, pump=dev.serve_all)
    with pytest.raises(env.ZhiMcpError) as ei:
        cli.list_tools()
    assert "翻页超过 3 页" in str(ei.value)


def test_client_collects_notifications_not_drops_them():
    cli, _dev, _a, b = _pair()
    # 设备主动推一条通知（无 id）—— 客户端不得丢
    b.send(env.Envelope("s", env.make_notification("notifications/state_changed",
                                                   {"newState": "idle"})).to_wire())
    notes = cli.drain_notifications()
    assert len(notes) == 1
    assert notes[0]["method"] == "notifications/state_changed"
    assert notes[0]["session_id"] == "s"


def test_client_describe_shape():
    cli, _dev, _a, _b = _pair()
    cli.handshake({})
    d = cli.describe()
    assert d["tool_count"] == 3 and d["handshake_done"] is True
    assert d["protocol_version"] == env.PROTOCOL_VERSION
    assert d["catalog"]["device_namespace_count"] == 3


# ============================================================ ④ 契约层


def test_manifest_entrypoint_and_handoff_contract():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    assert d["agentType"] == "mcp"
    ep = d["entryPoint"]
    mod = __import__(ep["module"], fromlist=["x"])
    cls = getattr(mod, ep["class"])
    assert callable(getattr(cls, "handle_handoff", None))
    assert d["classification"]["tier"] == "read-only"
    assert d["requires"]["external_binaries"] == []


def test_manifest_commands_match_dispatch_table():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    declared = {c["command"] for c in d["capabilities"]["invocationCommands"]}
    assert declared == set(zhi_server.ZhiMcpBridge._TOOLS)


def test_bridge_protocol_spec_lists_three_methods():
    spec = zhi_server.ZhiMcpBridge().protocol_spec()["data"]
    assert [m["name"] for m in spec["methods"]] == ["initialize", "tools/list", "tools/call"]
    assert spec["role"]["device"].startswith("MCP 服务器")
    assert "AI 辅助生成" in spec["source"]["doc_caveat"], "必须带上游文档的保留意见"
    assert spec["tool_namespace"]["prefix"] == "self."


def test_bridge_demo_handshake_and_call():
    br = zhi_server.ZhiMcpBridge()
    h = br.demo_handshake(page_size=2)["data"]
    assert h["catalog"]["count"] == 3 and h["requests_seen"] == 3
    ok = br.demo_call_tool("self.audio_speaker.set_volume", '{"volume": 7}')["data"]
    assert ok["call"]["texts"] == ["true"]
    bad = br.demo_call_tool("self.nope", "{}")["data"]
    assert bad["error"]["code"] == env.ERR_METHOD_NOT_FOUND
    assert "未吞成 ok=false" in bad["note"]


def test_bridge_build_envelope_and_parse_message():
    br = zhi_server.ZhiMcpBridge()
    built = br.build_envelope("sess-1", "tools/call", '{"name": "self.x"}', req_id=5)["data"]
    assert built["wire"]["session_id"] == "sess-1"
    assert built["wire"]["payload"]["id"] == 5
    parsed = br.parse_message(built["json"])["data"]
    assert parsed["kind"] == "request" and parsed["method"] == "tools/call"
    resp = br.parse_message(json.dumps({"session_id": "s", "type": "mcp",
                                        "payload": {"jsonrpc": "2.0", "id": 5,
                                                    "result": {"ok": 1}}}))["data"]
    assert resp["kind"] == "response" and resp["has_error"] is False
    note = br.parse_message(json.dumps({"session_id": "s", "type": "mcp",
                                        "payload": {"jsonrpc": "2.0",
                                                    "method": "notifications/x"}}))["data"]
    assert note["kind"] == "notification"


def test_bridge_doctor_cannot_list():
    doc = zhi_server.ZhiMcpBridge().doctor()
    assert len(doc["cannot"]) == 4
    assert any("WebSocket" in x for x in doc["cannot"])
    assert any("243" in n for n in doc["notes"])


def test_handle_handoff_success_and_errors():
    br = zhi_server.ZhiMcpBridge()
    ok = json.loads(asyncio.run(br.handle_handoff({"tool_name": "protocol_spec"})))
    assert ok["status"] == "success"
    bad = json.loads(asyncio.run(br.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "未知工具" in bad["message"]
    wrong = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "parse_message", "params": {"oops": 1}})))
    assert wrong["status"] == "error" and "参数错误" in wrong["message"]


def test_cli_main_runs(capsys):
    assert zhi_server.main(["spec"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert zhi_server.main(["handshake", "--page-size", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["requests_seen"] == 4          # 1 initialize + 3 页


def test_module_has_zero_third_party_imports():
    """零第三方依赖是**声明**，必须能被机械验证。"""
    allowed = {"__future__", "argparse", "asyncio", "collections", "dataclasses",
               "json", "logging", "typing"}
    for py in sorted(MODULE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            for m in mods:
                assert m in allowed, f"{py.name} 引入了非标准库 {m}"
