"""`mcpserver.zhi_mcp` 的 MCP 入口（工单248）。

对外两面：
- **离线可跑的一面** —— `demo_*` 用内存假设备跑完整协议流程（握手/翻页/调用/错误路径），
  不需要真硬件也不需要 websocket 库；
- **真实对接的一面** —— `build_envelope` / `parse_message` 给出**可复用的报文构造与判定**，
  把这两个接到任意 websocket/MQTT 收发上即可与真设备通信（传输由调用方提供）。

契约形态与 `mcpserver/rf_workflow`、`mcpserver/kicad_mcp`、`mcpserver/rf_evolve` 一致：
``handle_handoff(task) -> JSON 字符串``。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

from . import envelope as env
from .client import ZhiMcpClient
from .transport import FakeZhiDevice, wire_pair

logger = logging.getLogger(__name__)


def _wire_pair(page_size: int, tools: dict | None = None) -> tuple[ZhiMcpClient, FakeZhiDevice]:
    """建一对「客户端 ↔ 假设备」的内存连线（两个互连端点，语义见 `LoopbackTransport`）。"""
    client_tp, device_tp = wire_pair()
    device = FakeZhiDevice(device_tp, tools=tools, page_size=page_size)
    # 离线同线程 ⇒ 客户端等待响应时用 pump 驱动假设备（真实部署不需要，设备是独立对端）
    client = ZhiMcpClient(client_tp, session_id="sess-demo-0001", pump=device.serve_all)
    return client, device


class ZhiMcpBridge:
    """小智 MCP 协议的 MCP 入口。"""

    # ---- 工具一：协议自述 ----
    def protocol_spec(self) -> dict[str, Any]:
        """协议自述：信封形态 / 三个方法 / 角色分工 / 真值源与它的保留意见。"""
        return {"ok": True, "tool": "protocol_spec", "data": {
            "source": {
                "repo": "78/xiaozhi-esp32", "license": "MIT", "stars": 31197,
                "doc": "docs/mcp-protocol_zh.md",
                "doc_caveat": "该文档自述『AI 辅助生成, 在实现后台服务时, 请参照代码确认细节!!』"
                              "⇒ 本模块按文档形态实现，并对未知字段原样透传（不因多字段拒收）",
            },
            "role": {"device": "MCP 服务器（提供工具）", "backend_api": "MCP 客户端（调用工具）"},
            "envelope": {"session_id": "会话 ID（多设备共用连接时区分）",
                         "type": "固定 \"mcp\"",
                         "payload": "JSON-RPC 2.0 消息"},
            "methods": [
                {"name": "initialize", "direction": "后台→设备",
                 "params": "capabilities（可选，如 vision.url/token）",
                 "result": "protocolVersion / capabilities.tools / serverInfo"},
                {"name": "tools/list", "direction": "后台→设备",
                 "params": "cursor（首次空串）",
                 "result": "tools[] / nextCursor（非空则继续翻页）"},
                {"name": "tools/call", "direction": "后台→设备",
                 "params": "name / arguments",
                 "result": "content[{type:'text',text}] / isError；未知工具回 -32601"},
            ],
            "notifications": "设备可主动发 notifications/*（无 id，**不得回包**）",
            "tool_namespace": {"prefix": env.DEVICE_TOOL_PREFIX,
                               "meaning": "self.* = 设备自身能力（音量/灯/GPIO…）",
                               "observed": ["self.get_device_status", "self.audio_speaker.set_volume"]},
            "protocol_version_seen": env.PROTOCOL_VERSION,
            "transport": "WebSocket 或 MQTT（本模块抽象成 send/recv，由调用方注入）",
        }}

    # ---- 工具二：离线握手演示 ----
    def demo_handshake(self, page_size: int = 2) -> dict[str, Any]:
        """用内存假设备跑完整握手：hello → initialize → tools/list（**自动翻页**）。

        `page_size` 控制假设备每页返回几条（>0 时强制多页，用来验翻页逻辑）。
        """
        client, device = _wire_pair(page_size)
        device.send_hello()
        summary = client.handshake({"vision": {"url": "http://example.invalid/vision", "token": "x"}})
        return {"ok": True, "tool": "demo_handshake", "data": {
            "page_size": page_size,
            "client": client.describe(),
            "device_tools_called": device.calls,
            "requests_seen": len(client.transport.sent),
        } | summary}

    # ---- 工具三：离线工具调用演示 ----
    def demo_call_tool(self, tool_name: str = "self.audio_speaker.set_volume",
                       arguments: str = '{"volume": 42}', page_size: int = 0) -> dict[str, Any]:
        """用内存假设备跑一次 `tools/call`（含未知工具的错误路径）。"""
        client, device = _wire_pair(page_size)
        client.handshake({})
        args = json.loads(arguments) if arguments else {}
        try:
            res = client.call_tool(tool_name, args)
            return {"ok": True, "tool": "demo_call_tool", "data": {
                "call": res, "device_calls": device.calls}}
        except env.ZhiMcpError as exc:
            return {"ok": True, "tool": "demo_call_tool", "data": {
                "error": {"code": exc.code, "message": exc.message},
                "device_calls": device.calls,
                "note": "设备报错被如实抛出（未吞成 ok=false）"}}

    # ---- 工具四：构造报文 ----
    def build_envelope(self, session_id: str, method: str, params: str = "",
                       req_id: int = 1) -> dict[str, Any]:
        """构造一条**真实可用**的信封（给对接真设备用）。`params` 传 JSON 字符串。"""
        p = json.loads(params) if params else None
        payload = env.make_request(method, p, req_id)
        wire = env.Envelope(session_id, payload).to_wire()
        return {"ok": True, "tool": "build_envelope",
                "data": {"wire": wire, "json": env.dumps(wire)}}

    # ---- 工具五：解析/判定报文 ----
    def parse_message(self, raw_json: str) -> dict[str, Any]:
        """解析一条收到的信封：判定类型 / 是否通知 / 是否响应，并给出可读摘要。"""
        raw = env.loads(raw_json)
        e = env.Envelope.from_wire(raw)
        payload = e.payload or {}
        # ⚠️ 判定顺序：通知（无 id）→ **请求（有 method）** → 响应（有 id、无 method）。
        #    JSON-RPC 的**请求同时有 id 与 method**，若先判 id 会把请求误判成响应（实测踩过）。
        kind = ("notification" if env.is_notification(payload)
                else "request" if "method" in payload
                else "response" if "id" in payload else "unknown")
        out = {"session_id": e.session_id, "type": e.type, "kind": kind,
               "extra_fields": sorted(e.extra), "payload_keys": sorted(payload)}
        if kind == "request":
            out["method"] = payload.get("method")
        elif kind == "response":
            out["id"] = payload.get("id")
            out["has_error"] = bool(payload.get("error"))
            if payload.get("error"):
                out["error"] = payload["error"]
        else:
            out["method"] = payload.get("method")
        return {"ok": True, "tool": "parse_message", "data": out}

    # ---- 工具六：自述 ----
    def doctor(self) -> dict[str, Any]:
        """能力与**边界**自述。"""
        return {"ok": True, "tool": "doctor", "module": "mcpserver.zhi_mcp",
                "can": [
                    "实现小智 MCP 的**后台侧**完整交互（initialize / tools/list 翻页 / tools/call）",
                    "信封与 JSON-RPC 2.0 编解码（未知字段原样透传）",
                    "用内存假设备**离线**跑通全链路（含分页与 -32601 错误路径）",
                    "给真实对接提供 build_envelope / parse_message 两个可复用入口",
                ],
                "cannot": [
                    "**不实现 WebSocket/MQTT 传输** —— 传输抽象成 send/recv，由调用方注入（避免把协议层绑死到某个 ws 库）",
                    "**不驱动真设备**（本机无 ESP32；假设备是按上游文档写的，不是固件）",
                    "不把设备返回的文本猜成类型（`\"true\"` 就是字符串，是否解析由调用方决定）",
                    "不做云端 MCP 那一路（上游文档只写了**设备端** MCP；云端方向另属 `mcp-usage` 文档范围）",
                ],
                "notes": [
                    "与 243（mcpserver/esp32）的边界：243 是**集群/编码仿真**，本模块是**设备控制协议**，两者不共用代码。",
                    "上游文档自述由 AI 辅助生成、要求以代码为准 ⇒ 真机联调时若报文有出入，以设备实发为准。",
                ]}

    # ---- 白名单 ----
    _TOOLS: dict[str, str] = {
        "protocol_spec": "protocol_spec",
        "demo_handshake": "demo_handshake",
        "demo_call_tool": "demo_call_tool",
        "build_envelope": "build_envelope",
        "parse_message": "parse_message",
        "doctor": "doctor",
        # ⚠️ list_tools 必须在此表内（由 test_manifest_commands_match_dispatch_table 盯着）
        "list_tools": "list_tools",
    }

    def list_tools(self) -> dict[str, Any]:
        """自述白名单。"""
        return {"ok": True, "tool": "list_tools", "count": len(self._TOOLS),
                "tools": sorted(self._TOOLS),
                "note": "本模块是**协议层**：离线演示 + 报文构造/解析；传输由调用方注入。"}

    # ---- handoff ----
    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 契约入口：``task -> JSON 字符串``。"""
        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps({"status": "error",
                               "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                               "data": {}}, ensure_ascii=False)
        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_") and k not in ("tool_name", "agentType", "service_name")}
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[zhi_mcp] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """命令行入口。"""
    ap = argparse.ArgumentParser(prog="zhi_mcp", description="小智 MCP 协议层（工单248）")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("spec", help="协议自述")
    p = sub.add_parser("handshake", help="离线握手演示")
    p.add_argument("--page-size", type=int, default=2)
    p = sub.add_parser("call", help="离线工具调用演示")
    p.add_argument("--tool", default="self.audio_speaker.set_volume")
    p.add_argument("--args", default='{"volume": 42}')
    p = sub.add_parser("parse", help="解析一条信封 JSON")
    p.add_argument("raw", help="信封 JSON 字符串")
    sub.add_parser("doctor", help="能力/边界自述")
    return ap


def main(argv: list[str] | None = None) -> int:
    """跑一个 CLI 子命令并打印 JSON。"""
    args = build_parser().parse_args(argv)
    br = ZhiMcpBridge()
    c = args.command
    if c == "spec":
        out = br.protocol_spec()
    elif c == "handshake":
        out = br.demo_handshake(args.page_size)
    elif c == "call":
        out = br.demo_call_tool(args.tool, args.args)
    elif c == "parse":
        out = br.parse_message(args.raw)
    elif c == "doctor":
        out = br.doctor()
    else:
        out = br.list_tools()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["FakeZhiDevice", "ZhiMcpBridge", "ZhiMcpClient",
           "build_parser", "main"]
