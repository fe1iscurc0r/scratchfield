"""小智（xiaozhi-esp32）MCP 消息信封与 JSON-RPC 2.0 编解码（工单248）。

## 真值源与它的保留意见

上游 `78/xiaozhi-esp32`（MIT，31.2k★）的 `docs/mcp-protocol_zh.md` 定义了协议：
后台 API（**MCP 客户端**）与 ESP32 设备（**MCP 服务器**）之间，MCP 消息**封装在基础通信协议**
（WebSocket 或 MQTT）的消息体里，内层是标准 **JSON-RPC 2.0**：

```json
{"session_id": "...", "type": "mcp", "payload": {"jsonrpc": "2.0", "method": "...", ...}}
```

⚠️ **该文档自己声明**：「NOTICE: AI 辅助生成, 在实现后台服务时, 请参照代码确认细节!!」
⇒ 本模块按**文档描述的形态**实现，并对两处**刻意的宽松**处理：
① 未知字段**原样透传**（不因多一个字段就拒收）；② 缺失可选字段不报错。
这样即使线上固件与文档有出入，也不会因为我们"校验太严"而丢消息。

多设备/多会话共用一条连接时靠 `session_id` 区分；**本模块所有收发都带它**，
不存在"忘了带 session_id"的隐式路径（`Envelope.session_id` 是必填参数）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 信封里 `type` 的固定值（设备控制类消息）
TYPE_MCP = "mcp"
#: 信封里 `type` 的握手消息
TYPE_HELLO = "hello"

#: JSON-RPC 2.0 错误码（上游文档只点名了 -32601，其余按规范补齐）
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

#: 上游文档示例出现的协议版本（设备在 initialize 响应里回它）
PROTOCOL_VERSION = "2024-11-05"

#: 设备端工具名的命名空间前缀 —— `self.*` 表示"设备自身的能力"
DEVICE_TOOL_PREFIX = "self."


class ZhiMcpError(Exception):
    """遵循 JSON-RPC 的错误（`code`/`message` 来自设备响应）。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data

    @classmethod
    def from_error(cls, err: dict | None) -> ZhiMcpError:
        e = err or {}
        return cls(int(e.get("code", ERR_INTERNAL)), str(e.get("message", "unknown error")),
                   e.get("data"))


@dataclass
class Envelope:
    """基础协议信封：``{session_id, type, payload}``。"""

    session_id: str
    payload: dict
    type: str = TYPE_MCP
    #: 信封上可能出现的其它字段（上游文档未穷举）—— 原样保留，不丢不生
    extra: dict = field(default_factory=dict)

    def to_wire(self) -> dict:
        out = dict(self.extra)
        out.update({"session_id": self.session_id, "type": self.type, "payload": self.payload})
        return out

    @classmethod
    def from_wire(cls, raw: dict) -> Envelope:
        if not isinstance(raw, dict):
            raise ZhiMcpError(ERR_INVALID_REQUEST, f"信封必须是对象，实得 {type(raw).__name__}")
        known = {"session_id", "type", "payload"}
        return cls(session_id=str(raw.get("session_id") or ""),
                   payload=raw.get("payload") or {},
                   type=str(raw.get("type") or TYPE_MCP),
                   extra={k: v for k, v in raw.items() if k not in known})


# --------------------------------------------------------------------------- JSON-RPC


def make_request(method: str, params: dict | None, req_id: int) -> dict:
    """构造 JSON-RPC 2.0 请求（`id` 必填 —— 设备要靠它匹配响应）。"""
    msg: dict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    return msg


def make_notification(method: str, params: dict | None = None) -> dict:
    """构造通知（**无 `id`** —— 收到通知不得回包）。"""
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def is_notification(msg: dict) -> bool:
    """无 `id` 且有 `method` ⇒ 通知。"""
    return isinstance(msg, dict) and "id" not in msg and "method" in msg


def unwrap_response(msg: dict, expect_id: int | None = None) -> dict:
    """从响应里取出 `result`；有 `error` 就抛 `ZhiMcpError`。

    :param expect_id: 给定则校验 `id` 是否匹配（防止把别的请求的响应当成自己的）。
    """
    if not isinstance(msg, dict):
        raise ZhiMcpError(ERR_INVALID_REQUEST, "响应必须是对象")
    if expect_id is not None and msg.get("id") != expect_id:
        raise ZhiMcpError(ERR_INVALID_REQUEST,
                          f"响应 id 不匹配：期望 {expect_id}，实得 {msg.get('id')!r}")
    if "error" in msg and msg["error"]:
        raise ZhiMcpError.from_error(msg["error"])
    if "result" not in msg:
        raise ZhiMcpError(ERR_INVALID_REQUEST, "响应既无 result 也无 error")
    return msg["result"] or {}


def parse_tool_result(result: dict) -> tuple[Any, bool]:
    """解析 `tools/call` 的 `result`：``(content, is_error)``。

    按上游文档，成功时 ``result.content`` 是内容块列表（``{"type":"text","text":...}``），
    并带 ``isError`` 标志。这里把 ``text`` 块**原样保留成字符串列表**，
    **不尝试把 "true"/"50" 猜成类型** —— 猜错比不猜更糟（设备返回的是文本，是否解析由调用方决定）。
    """
    blocks = result.get("content") or []
    if isinstance(blocks, dict):                     # 容错：单个块而非列表
        blocks = [blocks]
    texts = [str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in blocks]
    return texts, bool(result.get("isError", False))


def dumps(msg: dict) -> str:
    """序列化（`ensure_ascii=False` —— 中文描述不该变成 \\uXXXX；紧凑分隔符贴近设备实发）。"""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict:
    """反序列化；坏 JSON 抛 ``ZhiMcpError(-32700)``（与 JSON-RPC 的 parse error 一致）。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ZhiMcpError(ERR_PARSE, f"JSON 解析失败：{exc.msg}（pos {exc.pos}）") from exc
