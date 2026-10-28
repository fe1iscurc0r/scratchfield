"""小智 MCP 客户端（工单248 · 后台 API 侧）。

上游把角色分得很清：**后台 API 是 MCP 客户端，ESP32 设备是 MCP 服务器**。
本模块实现客户端侧的完整交互：

```
设备 ──hello(features.mcp=true)──► 后台
后台 ──initialize(capabilities)──► 设备 ──► {protocolVersion, serverInfo}
后台 ──tools/list(cursor="")─────► 设备 ──► {tools:[...], nextCursor}
        （nextCursor 非空则继续翻页，直到为空）
后台 ──tools/call(name,args)─────► 设备 ──► {content:[{type:"text",text}], isError}
后台 ◄──notifications/*（设备主动，无 id，不回包）
```

设计取舍
--------
- **同步**：`recv` 拿到就用，不做事件循环。设备消息是请求-响应节奏；通知在 `drain_notifications` 里
  顺手收（真要长连接常驻，应由调用方在自己的 pump 里驱动 `serve`）。
- **不猜类型**：`tools/call` 的返回是**文本块**（文档示例 `set_volume` 回 `"true"`）。
  是否把 `"true"` 解析成布尔**由调用方决定** —— 我们只给文本，避免猜错。
- **不吞通知**：`drain_notifications` 会把非响应消息收起来而不是丢掉，
  否则设备主动报的状态变化会静默消失。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .envelope import (
    DEVICE_TOOL_PREFIX,
    TYPE_MCP,
    Envelope,
    ZhiMcpError,
    is_notification,
    make_request,
    parse_tool_result,
    unwrap_response,
)
from .transport import Transport


@dataclass
class ToolSpec:
    """一条设备工具声明。"""

    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)

    @property
    def is_device_namespace(self) -> bool:
        """是否属 `self.*`（设备自身能力）命名空间。"""
        return self.name.startswith(DEVICE_TOOL_PREFIX)

    @classmethod
    def from_wire(cls, raw: dict) -> ToolSpec:
        return cls(name=str(raw.get("name") or ""),
                   description=str(raw.get("description") or ""),
                   input_schema=raw.get("inputSchema") or raw.get("input_schema") or {})

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.input_schema}


class ToolCatalog:
    """设备工具目录：按名索引 + 命名空间切分 + **重名检测**。

    重名检测是刻意的：设备若在两页里报了同名工具，静默后者覆盖前者会让调用打到非预期的实现上。
    """

    def __init__(self, tools: list[ToolSpec] | None = None) -> None:
        self._by_name: dict[str, ToolSpec] = {}
        self.duplicates: list[str] = []
        self.order: list[str] = []
        for t in tools or []:
            self.add(t)

    def add(self, tool: ToolSpec) -> None:
        if not tool.name:
            return
        if tool.name in self._by_name:
            if tool.name not in self.duplicates:
                self.duplicates.append(tool.name)
        else:
            self.order.append(tool.name)
        self._by_name[tool.name] = tool          # 后者生效，但已记进 duplicates 供审计

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def names(self) -> list[str]:
        return list(self.order)

    def get(self, name: str) -> ToolSpec | None:
        return self._by_name.get(name)

    def device_tools(self) -> list[ToolSpec]:
        return [self._by_name[n] for n in self.order if n.startswith(DEVICE_TOOL_PREFIX)]

    def other_tools(self) -> list[ToolSpec]:
        return [self._by_name[n] for n in self.order if not n.startswith(DEVICE_TOOL_PREFIX)]

    def search(self, keyword: str) -> list[ToolSpec]:
        """子串检索（名字或描述，大小写不敏感）。空关键词返回空 —— 不做"返回全部"的隐式语义。"""
        kw = (keyword or "").strip().lower()
        if not kw:
            return []
        return [self._by_name[n] for n in self.order
                if kw in n.lower() or kw in self._by_name[n].description.lower()]

    def as_dict(self) -> dict:
        return {
            "count": len(self),
            "device_namespace_count": len(self.device_tools()),
            "other_namespace_count": len(self.other_tools()),
            "duplicates": list(self.duplicates),
            "tools": [self._by_name[n].as_dict() for n in self.order],
        }


class ZhiMcpClient:
    """后台 API 侧的小智 MCP 客户端。"""

    def __init__(self, transport: Transport, session_id: str, *,
                 timeout_s: float = 10.0, max_pages: int = 8,
                 pump: "Callable[[], object] | None" = None) -> None:
        """:param pump: **离线同线程场景**下的"跑一下对端"钩子。

        真实部署里设备是独立进程/设备，响应会自己到达，**不需要** pump；
        但在离线演示与单测里客户端与假设备跑在同一线程，客户端等待响应时没人驱动设备
        ⇒ 会一直等到超时。传 ``pump=device.serve_all`` 即可（实测踩过这个超时）。
        """
        if not session_id:
            raise ZhiMcpError(-32600, "session_id 必填（多设备共用连接时靠它区分）")
        self.transport = transport
        self.session_id = session_id
        self.timeout_s = float(timeout_s)
        self.max_pages = int(max_pages)
        self._pump = pump
        self._next_id = 1
        self.catalog = ToolCatalog()
        self.server_info: dict = {}
        self.negotiated_version: str = ""
        self.notifications: list[dict] = []
        self.handshake_done = False

    # ---------------------------------------------------------------- 底层收发
    def _send_request(self, method: str, params: dict | None) -> dict:
        rid = self._next_id
        self._next_id += 1
        self.transport.send(Envelope(self.session_id, make_request(method, params, rid)).to_wire())
        return self._await_result(rid)

    def _await_result(self, rid: int) -> dict:
        """等 `id == rid` 的响应；途中的通知收进 `self.notifications`（不丢）。"""
        budget = self.max_pages * 4 + 8            # 兜底：不无限等
        for _ in range(budget):
            raw = self.transport.recv(timeout_s=self.timeout_s)
            if raw is None:
                if self._pump is None:
                    raise ZhiMcpError(-32603, f"等待 id={rid} 的响应超时（{self.timeout_s}s）")
                self._pump()                       # 离线同线程：先让"设备"处理积压请求
                raw = self.transport.recv(timeout_s=0.0)
                if raw is None:
                    raise ZhiMcpError(-32603, f"等待 id={rid} 的响应超时（pump 后仍无消息）")
            env = Envelope.from_wire(raw)
            if env.type != TYPE_MCP:
                continue                            # 非 MCP 信封（如 hello）跳过
            payload = env.payload or {}
            if is_notification(payload):
                self.notifications.append({"session_id": env.session_id, **payload})
                continue
            if payload.get("id") != rid:
                # 不是我们要的响应 —— 可能是别的请求的（多路复用时正常）⇒ 收着别丢
                self.notifications.append({"session_id": env.session_id, **payload})
                continue
            return unwrap_response(payload, expect_id=rid)
        raise ZhiMcpError(-32603, f"等待 id={rid} 的响应时超出消息预算")

    # ---------------------------------------------------------------- 协议流程
    def initialize(self, capabilities: dict | None = None) -> dict:
        """① `initialize`：协商协议版本与拿到设备自述（serverInfo）。"""
        result = self._send_request("initialize", {"capabilities": capabilities or {}})
        self.server_info = result.get("serverInfo") or {}
        self.negotiated_version = str(result.get("protocolVersion") or "")
        return result

    def list_tools(self, *, max_pages: int | None = None) -> ToolCatalog:
        """② `tools/list`：**按 `nextCursor` 自动翻页**直到为空，结果落进 `catalog`。"""
        cap = self.max_pages if max_pages is None else int(max_pages)
        cursor = ""
        catalog = ToolCatalog()
        for page in range(cap):
            result = self._send_request("tools/list", {"cursor": cursor})
            for raw in result.get("tools") or []:
                catalog.add(ToolSpec.from_wire(raw))
            cursor = str(result.get("nextCursor") or "")
            if not cursor:
                self.catalog = catalog
                return catalog
        raise ZhiMcpError(-32603,
                          f"tools/list 翻页超过 {cap} 页仍未结束（cursor={cursor!r}）—— 疑似设备不回空 cursor")

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """③ `tools/call`：调用设备工具。设备报错 ⇒ 抛 `ZhiMcpError`（不吞成 ok=False）。"""
        result = self._send_request("tools/call",
                                    {"name": name, "arguments": arguments or {}})
        texts, is_error = parse_tool_result(result)
        return {"tool": name, "arguments": arguments or {}, "texts": texts,
                "is_error": is_error, "content": result.get("content") or []}

    # ---------------------------------------------------------------- 便捷
    def handshake(self, capabilities: dict | None = None) -> dict:
        """一步到位：`initialize` + `tools/list`。返回自述与目录摘要。"""
        info = self.initialize(capabilities)
        cat = self.list_tools()
        self.handshake_done = True
        return {"protocol_version": self.negotiated_version,
                "server_info": dict(self.server_info),
                "catalog": cat.as_dict(),
                "initialize_result_keys": sorted(info)}

    def drain_notifications(self) -> list[dict]:
        """回收已到达的设备通知（不去阻塞等）。"""
        while True:
            raw = self.transport.recv(timeout_s=0.0)
            if raw is None:
                break
            env = Envelope.from_wire(raw)
            self.notifications.append({"session_id": env.session_id, **(env.payload or {})})
        out, self.notifications = self.notifications, []
        return out

    def describe(self) -> dict:
        """客户端现状自述（会话/版本/目录规模/重名/收到的通知数）。"""
        return {
            "session_id": self.session_id,
            "protocol_version": self.negotiated_version,
            "server_info": dict(self.server_info),
            "handshake_done": self.handshake_done,
            "tool_count": len(self.catalog),
            "catalog": self.catalog.as_dict(),
            "pending_messages": len(self.notifications),
            "timeout_s": self.timeout_s,
        }
