# mcpserver/zhi_mcp —— 小智 MCP 协议的**后台侧**实现（工单248）

> 上游：**[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)**（MIT，**31,197★ / 7,294 fork**，pushed 2026-10-15）
> 「An MCP-based chatbot ｜ 一个基于 MCP 的聊天机器人」
> 真值源：上游 `docs/mcp-protocol_zh.md` ｜ 本模块：**零第三方依赖、不需要硬件、离线可跑**

---

## 1 · 一句话

上游把角色分得很清：**ESP32 设备是 MCP 服务器**（提供 `self.*` 设备能力：音量/灯/GPIO…），
**后台 API 是 MCP 客户端**（发现并调用这些工具）。本模块实现**客户端那半边**，
并且把它做成**离线可回归**的形态 —— 因为它不依赖真硬件、也不绑定任何 websocket 库。

---

## 2 · 协议（按上游文档实现）

**信封**（跑在 WebSocket/MQTT 的消息体里）：

```json
{"session_id": "...", "type": "mcp", "payload": { /* JSON-RPC 2.0 */ }}
```

**三个方法**：

| 方法 | 方向 | 入参 | 返回 |
|---|---|---|---|
| `initialize` | 后台→设备 | `capabilities`（可选，如 `vision.url/token`） | `protocolVersion` / `capabilities.tools` / `serverInfo` |
| `tools/list` | 后台→设备 | `cursor`（首次空串） | `tools[]` / `nextCursor`（非空则**继续翻页**） |
| `tools/call` | 后台→设备 | `name` / `arguments` | `content[{type:"text",text}]` / `isError`；未知工具回 **-32601** |

**设备通知**：`notifications/*`，**无 `id`** ⇒ 收到不得回包（本模块收进 `notifications` 而不丢）。

⚠️ **上游文档自己声明**：「NOTICE: **AI 辅助生成**, 在实现后台服务时, 请参照代码确认细节!!」
⇒ 本实现对**未知字段原样透传**（不因多一个字段就拒收），缺失可选字段不报错 ——
**宁可宽松也不要因为"校验太严"而丢消息**。

---

## 3 · 为什么"离线可跑"是本模块的关键设计

若把某个 websocket 库写死进协议层，这个模块就**只能连真设备才能测** ⇒ 变成没有 ESP32 就无法回归的东西。
（本仓已吃过同款味道：245 的 PCB 夹具因为本机没 KiCAD，只能说"手写样本"。）

⇒ 传输被抽成**两个方法**（`send` / `recv`），协议层只依赖它：

| 实现 | 用途 |
|---|---|
| `LoopbackTransport` + `FakeZhiDevice` | **测试与离线演示**：同进程跑通全链路（含翻页与错误路径） |
| 调用方自己的 WebSocket/MQTT 实现 | 真机联调（本模块**不替调用方选型**，也不把它的依赖带进仓） |

`FakeZhiDevice` 严格按上游文档形态应答，但它**是按文档写的、不是固件** ⇒ 真机联调时以设备实发为准。

---

## 4 · 能力面（7 个工具）

| 工具 | 给什么 |
|---|---|
| `protocol_spec` | 协议自述（形态/方法/命名空间/真值源与它的保留意见） |
| `demo_handshake` | 离线握手演示：`initialize` + `tools/list`（**自动翻页**） |
| `demo_call_tool` | 离线工具调用：成功给文本块；失败**如实抛错**（不吞成 `ok=false`） |
| `build_envelope` | 构造真实可用的信封（对接真设备用） |
| `parse_message` | 解析来报：判定 request/response/notification/unknown |
| `doctor` / `list_tools` | 能力与**边界**自述 |

**实测（离线）**：

```jsonc
// demo_handshake(page_size=2)：3 个工具分 2 页 ⇒ 3 条请求（1 initialize + 2 tools/list）
{"protocol_version": "2024-11-05",
 "server_info": {"name": "fake-xiaozhi", "version": "0.0.0-fake"},
 "catalog": {"count": 3, "device_namespace_count": 3, "duplicates": []},
 "requests_seen": 3}
// demo_call_tool("self.audio_speaker.set_volume", {"volume": 42})
{"call": {"texts": ["true"], "is_error": false}}
// 越界 ⇒ -32602；未知工具 ⇒ -32601（两种都如实抛出）
```

---

## 5 · 边界（刻意不做）

1. **不实现 WebSocket/MQTT** —— 传输由调用方注入（见 §3）。真机联调需要一个 ws/mqtt 客户端，选型归调用方。
2. **不驱动真设备** —— 本机无 ESP32；`FakeZhiDevice` 是按上游文档写的测试替身。真机报文细节需真设备复核。
3. **不把设备返回的文本猜成类型** —— 文档示例里 `set_volume` 返回的是文本 `"true"` 而非 JSON 布尔；
   是否把 `"true"` 解析成 `True` **由调用方决定**（猜错比不猜更糟）。
4. **不做云端 MCP 那一路** —— 上游文档只描述了**设备端** MCP；「云端 MCP 扩展大模型能力」属 `mcp-usage` 文档范围。

---

## 6 · 与相邻模块的划界

| 模块 | 关系 |
|---|---|
| `mcpserver/esp32`（243） | 243 是**集群/编码仿真**（分簇 + RLNC），本模块是**设备控制协议** —— 不共用代码 |
| `mcpserver/mcp_registry` / `mcp_manager` | 那是本仓**内部**的 MCP 工具总线；本模块是**对外**接小智设备的协议层 |
| `voice_mcp_*` | 语音类 MCP agent；本模块不涉及音频编解码（上游的 `audio_params` 只在 hello 里透传） |

---

## 7 · 复现

```bash
PY=.venv/Scripts/python.exe        # 任意 Python 3.11+，零依赖
$PY -m mcpserver.zhi_mcp.server spec
$PY -m mcpserver.zhi_mcp.server handshake --page-size 2
$PY -m mcpserver.zhi_mcp.server call --tool self.audio_speaker.set_volume --args '{"volume": 42}'
$PY -m mcpserver.zhi_mcp.server parse '{"session_id":"s","type":"mcp","payload":{"jsonrpc":"2.0","method":"tools/list","id":1}}'
$PY -m mcpserver.zhi_mcp.server doctor
$PY -m pytest tests/test_zhi_mcp.py -q     # 35 passed
```
