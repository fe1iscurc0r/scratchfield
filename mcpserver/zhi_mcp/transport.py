"""传输层：抽象 + 内存假设备（工单248）。

## 为什么要"传输抽象 + 假设备"

上游的 MCP 消息跑在 **WebSocket 或 MQTT** 上。若把 websocket 客户端写死在协议层里，
那么协议实现就**只能连真设备才能测** —— 变成没有硬件就无法回归的东西。
（本仓已吃过这个味道：245 的 PCB 夹具因为本机没 KiCAD 只能说"手写样本"。）

⇒ 本模块把传输抽成两方法（``send`` / ``recv``），协议实现只依赖它；
测试用 `InMemoryTransport` + `FakeZhiDevice` **端到端跑完整交互**（含分页与错误路径），
真设备接进来时只需换一个 transport 实现。

## 假设备的忠实度边界

`FakeZhiDevice` 严格按上游 `docs/mcp-protocol_zh.md` 的报文形态应答
（`initialize` / `tools/list` 含 `nextCursor` 分页 / `tools/call` 含 `content+isError` /
未知工具回 `-32601`）。但**它是我们按文档写的，不是上游固件**：
真机上工具清单内容、以及文档与 `main/mcp_server.cc` 的细节出入，需真设备复核。
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Callable, Protocol

from .envelope import (
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    TYPE_HELLO,
    TYPE_MCP,
    Envelope,
    ZhiMcpError,
    make_request,
)


class Transport(Protocol):
    """传输：发一个信封、收一个信封。真实现 = WebSocket / MQTT；测试实现 = 内存。"""

    def send(self, envelope: dict) -> None:  # pragma: no cover - 协议
        ...

    def recv(self, timeout_s: float | None = None) -> dict | None:  # pragma: no cover - 协议
        ...

    def close(self) -> None:  # pragma: no cover - 协议
        ...


class InMemoryTransport:
    """内存传输：两端各一个队列。`recv` 返回 ``None`` 表示无新消息。"""

    def __init__(self) -> None:
        self.sent: deque[dict] = deque()        # 本端发出的
        self.inbox: deque[dict] = deque()       # 本端待收的
        self.closed = False

    def send(self, envelope: dict) -> None:
        if self.closed:
            raise ZhiMcpError(ERR_INVALID_PARAMS, "传输已关闭")
        self.sent.append(envelope)

    def recv(self, timeout_s: float | None = None) -> dict | None:
        return self.inbox.popleft() if self.inbox else None

    def close(self) -> None:
        self.closed = True

    # 测试辅助：把对端发出的消息投递进本端 inbox
    def deliver(self, envelope: dict) -> None:
        self.inbox.append(envelope)


class LoopbackTransport(InMemoryTransport):
    """一对互连端点（测试与离线演示用）—— 语义刻意分开，避免"发给自己还是发给对方"的混乱：

    - ``send(env)`` / ``deliver(env)``：**给对方**（`send` 是协议层发请求，`deliver` 是假设备回包；
      两者同向，保留两个名字只是为了贴合各自调用点的语气）
    - ``inject(env)``：**给自己**（测试构造"本端收到了什么"，如手工塞一条通知）

    未连线时（``peer is None``）``send`` 退化为自环 —— 便于单端自测，但**不是**默认行为。
    """

    def __init__(self) -> None:
        super().__init__()
        self.peer: LoopbackTransport | None = None

    def send(self, envelope: dict) -> None:
        if self.closed:                     # ⚠️ 覆写 send 时必须自己再检一次 —— 基类的检查被绕过了
            raise ZhiMcpError(ERR_INVALID_PARAMS, "传输已关闭")
        self.sent.append(envelope)          # 本端发件账（测试断言"发了几条/发了什么"）
        if self.peer is None:
            self.inbox.append(envelope)
            return
        self.peer.inbox.append(envelope)

    def deliver(self, envelope: dict) -> None:
        self.send(envelope)

    def inject(self, envelope: dict) -> None:
        self.inbox.append(envelope)


def wire_pair() -> tuple[LoopbackTransport, LoopbackTransport]:
    """建一对互连端点 ``(a, b)``：``a.send`` 进 ``b.inbox``，``b.send`` 进 ``a.inbox``。"""
    a, b = LoopbackTransport(), LoopbackTransport()
    a.peer, b.peer = b, a
    return a, b


class FakeZhiDevice:
    """按上游文档形态应答的**内存假设备**（MCP 服务器侧）。

    :param tools: ``{工具名: (描述, inputSchema, handler)}``；handler 收 `arguments` 返回任意值，
        **返回值会被包成 ``[{"type":"text","text": str(值)}]``** —— 与文档示例一致
        （`self.audio_speaker.set_volume` 返回 `"true"` 文本而不是 JSON 布尔）。
    :param page_size: `tools/list` 每页返回多少条（0 = 不分页，一次给全）。
    """

    def __init__(self, transport: InMemoryTransport, *,
                 tools: dict[str, tuple[str, dict, Callable[[dict], Any]]] | None = None,
                 page_size: int = 0, board_name: str = "fake-xiaozhi",
                 firmware_version: str = "0.0.0-fake") -> None:
        self.transport = transport
        self.tools = dict(tools or _DEFAULT_TOOLS)
        self.page_size = int(page_size)
        self.board_name = board_name
        self.firmware_version = firmware_version
        self.calls: list[tuple[str, dict]] = []          # 收到过的 tools/call（供测试断言）
        self.unknown_methods: list[str] = []             # 收到过的未知 method
        self.hello_sent = False

    # ---------------------------------------------------------------- 设备行为
    def send_hello(self, *, session_id: str = "") -> None:
        """设备连上后台后先发 hello（含 `features.mcp=True`）。"""
        self.transport.deliver({
            "type": TYPE_HELLO, "version": 1, "transport": "websocket",
            "features": {"mcp": True, "audio": True},
            "session_id": session_id,
        })
        self.hello_sent = True

    def serve_one(self) -> dict | None:
        """处理一条来自后台的请求，回一条响应。返回处理过的请求（无消息则 None）。"""
        req_env = self.transport.recv()
        if req_env is None:
            return None
        try:
            env = Envelope.from_wire(req_env)
        except ZhiMcpError as exc:
            self._reply(req_env, {"jsonrpc": "2.0", "id": None,
                                  "error": {"code": exc.code, "message": exc.message}})
            return req_env
        payload = env.payload or {}
        if "id" not in payload:                      # 通知：不回
            return req_env
        method = str(payload.get("method") or "")
        params = payload.get("params") or {}
        rid = payload.get("id")
        try:
            if method == "initialize":
                result = self._on_initialize(params)
            elif method == "tools/list":
                result = self._on_tools_list(params)
            elif method == "tools/call":
                result = self._on_tools_call(params)
            else:
                self.unknown_methods.append(method)
                raise ZhiMcpError(ERR_METHOD_NOT_FOUND, f"未知方法 {method}")
        except ZhiMcpError as exc:
            self._reply(env.to_wire(), {"jsonrpc": "2.0", "id": rid,
                                        "error": {"code": exc.code, "message": exc.message}})
            return req_env
        self._reply(env.to_wire(), {"jsonrpc": "2.0", "id": rid, "result": result})
        return req_env

    def serve_all(self, *, max_messages: int = 64) -> int:
        """一直处理到没消息为止（返回处理条数）。"""
        n = 0
        while n < max_messages and self.serve_one() is not None:
            n += 1
        return n

    # ---------------------------------------------------------------- 各方法
    def _on_initialize(self, params: dict) -> dict:
        # 文档：设备回 protocolVersion / capabilities.tools / serverInfo
        _ = params.get("capabilities")           # 后台能力（如 vision）—— 我们只记录不处理
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self.board_name, "version": self.firmware_version},
        }

    def _on_tools_list(self, params: dict) -> dict:
        cursor = str(params.get("cursor") or "")
        names = list(self.tools)
        if self.page_size <= 0:
            page, next_cursor = names, ""
        else:
            start = int(cursor) if cursor.isdigit() else 0
            page = names[start:start + self.page_size]
            nxt = start + self.page_size
            next_cursor = str(nxt) if nxt < len(names) else ""
        return {
            "tools": [{"name": n, "description": self.tools[n][0], "inputSchema": self.tools[n][1]}
                      for n in page],
            "nextCursor": next_cursor,
        }

    def _on_tools_call(self, params: dict) -> dict:
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        self.calls.append((name, args))
        if name not in self.tools:
            # 文档：未知工具回 -32601
            raise ZhiMcpError(ERR_METHOD_NOT_FOUND, f"Unknown tool: {name}")
        handler = self.tools[name][2]
        value = handler(args)
        if isinstance(value, dict) and "content" in value:      # handler 可自行给完整结果体
            return value
        return {"content": [{"type": "text", "text": _as_text(value)}], "isError": False}

    def _reply(self, req_env: dict, payload: dict) -> None:
        env = Envelope.from_wire(req_env)
        self.transport.deliver({**env.extra, "session_id": env.session_id,
                                "type": TYPE_MCP, "payload": payload})


def _as_text(value: Any) -> str:
    """按设备的实际行为把返回值转文本（bool → "true"/"false"，与文档示例一致）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _default_tools() -> dict[str, tuple[str, dict, Callable[[dict], Any]]]:
    """一组最小可用的设备端工具（照上游 `self.*` 命名空间与文档点名的两个工具）。"""
    def _volume(args: dict) -> bool:
        v = int(args.get("volume", 0))
        if not 0 <= v <= 100:
            raise ZhiMcpError(ERR_INVALID_PARAMS, f"volume 越界: {v}（须 0..100）")
        return True

    return {
        "self.get_device_status": (
            "查询设备状态（电量/音量/网络）",
            {"type": "object", "properties": {}, "required": []},
            lambda _a: {"battery": 87, "volume": 50, "network": "wifi"},
        ),
        "self.audio_speaker.set_volume": (
            "设置扬声器音量（0-100）",
            {"type": "object",
             "properties": {"volume": {"type": "integer", "minimum": 0, "maximum": 100}},
             "required": ["volume"]},
            _volume,
        ),
        "self.light.set_rgb": (
            "设置灯色（R/G/B 0-255）",
            {"type": "object",
             "properties": {"r": {"type": "integer"}, "g": {"type": "integer"},
                            "b": {"type": "integer"}},
             "required": ["r", "g", "b"]},
            lambda a: True,
        ),
    }


_DEFAULT_TOOLS = _default_tools()
