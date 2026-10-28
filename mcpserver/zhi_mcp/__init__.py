"""mcpserver.zhi_mcp —— 小智（xiaozhi-esp32）MCP 协议的**后台侧**实现（工单248）。

上游 `78/xiaozhi-esp32`（MIT，31.2k★）是一个「基于 MCP 的聊天机器人」固件：
**设备是 MCP 服务器**（提供 `self.*` 设备能力），**后台 API 是 MCP 客户端**（发现并调用它们）。
本模块把客户端侧那半边做成**离线可跑、无硬件依赖**的实现：

| 文件 | 作用 |
|---|---|
| `envelope.py` | 信封 `{session_id,type,payload}` + JSON-RPC 2.0 编解码（未知字段原样透传） |
| `transport.py` | 传输抽象（`send`/`recv`）+ 内存假设备 `FakeZhiDevice` + 互连端点 |
| `client.py` | `ZhiMcpClient`：`initialize` → `tools/list`（**自动翻页**）→ `tools/call` + 工具目录 |
| `server.py` | `ZhiMcpBridge`（7 工具）+ CLI：协议自述 / 离线演示 / 报文构造与解析 |

**边界**：不实现 WebSocket/MQTT（传输由调用方注入）；不驱动真设备（假设备按上游文档写，
不是固件）；不把设备返回的文本猜成类型；不做云端 MCP 那一路（上游文档只写了设备端）。

**与 243 的划界**：`mcpserver/esp32` 是集群/编码仿真，本模块是**设备控制协议**，不共用代码。
"""

from __future__ import annotations

from .client import ToolCatalog, ToolSpec, ZhiMcpClient
from .envelope import Envelope, ZhiMcpError, dumps, loads
from .transport import FakeZhiDevice, InMemoryTransport, LoopbackTransport, wire_pair

__all__ = [
    "Envelope",
    "FakeZhiDevice",
    "InMemoryTransport",
    "LoopbackTransport",
    "ToolCatalog",
    "ToolSpec",
    "ZhiMcpBridge",
    "ZhiMcpClient",
    "ZhiMcpError",
    "dumps",
    "loads",
    "wire_pair",
]


def __getattr__(name: str):
    """`ZhiMcpBridge` 惰性暴露（`server` 只在真取用时导入）。"""
    if name == "ZhiMcpBridge":
        from .server import ZhiMcpBridge

        return ZhiMcpBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
