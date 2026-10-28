# 工单 248 完工报告 · 小智 MCP 协议层（`mcpserver/zhi_mcp/`）

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `9f55ca65a2`（工单246 合并点）
> 工单来源：`TRAE_WORKORDER_PROMPT_AGENT_248.md`（cron 自动草稿 → 师傅签字晋升）
> 上游：**[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)**（MIT，**31,197★ / 7,294 fork**，"An MCP-based chatbot"）
> 交付：**15 个新文件、0 个既有文件改动**

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增文件 | **15**（模块 5 + manifest/README/requirements + sandbox 9 + 测试 1 + 集成图 1 + 本报告 —— 明细见 §3） |
| 既有文件改动 | **0** |
| 第三方依赖 | **0**（含"刻意不引 websocket 库"的理由，见 §2.2） |
| 需要硬件 | **不需要**（离线假设备跑通全链路） |
| 测试 | **35 用例全绿** |
| `ruff` | **All checks passed** |
| 真跑证据 | `sandbox/zhi-20261016-protocol-offline/` 9 份（含**分页 / 越界 / 未知工具**三条路径） |

## §1 · 工单 §4 的填实

| §4 项 | 本单结论 |
|---|---|
| **PoC 边界与验收标准** | **边界**：只做**后台侧（MCP 客户端）**协议实现 —— 信封/JSON-RPC 编解码 + 三方法交互；**不做** WebSocket/MQTT 传输、不驱动真设备、不做云端 MCP 那一路。**验收**：① 三方法全链路离线跑通（含**分页**与两类错误码）；② 未知字段必须**原样透传**（上游文档自述 AI 生成、可能滞后）；③ 35 用例全绿 + ruff 全仓绿。 |
| **与现有模块的耦合点** | 落点 `mcpserver/zhi_mcp/`（新）；与 `mcpserver/esp32`(243) 是**设备控制协议 vs 集群仿真**的划界；与 `mcp_registry`/`mcp_manager` 是**对外协议层 vs 仓内工具总线**的划界（详见 README §6、集成图 §5）。 |
| **是否与已发工单重复** | **不重复**（244j 代查：`xiaozhi` 在根目录 45 个工单里零命中）。 |

## §2 · 设计决策

### 2.1 为什么必须"离线可跑"

若把 websocket 库写死进协议层，本模块就**只能连真设备才能测** ⇒ 变成没有 ESP32 就无法回归。
（本仓吃过同款味道：245 的 PCB 夹具因本机无 KiCAD 只能说"手写样本"。）
⇒ 传输抽成**两个方法**（`send`/`recv`）：测试用 `LoopbackTransport` + `FakeZhiDevice` 跑全链路；
真机联调时调用方注入自己的 ws/mqtt 实现。**本模块不替调用方选型，也不把它的依赖带进仓。**

⚠️ 实现期踩到一个只有真跑才暴露的坑：**离线同线程时没人驱动设备** ⇒ 客户端发完请求
一直等到超时。修法是给客户端一个显式的 `pump` 钩子（`pump=device.serve_all`），
并把它写进文档：**真实部署不需要 pump**（设备是独立对端）。

### 2.2 对上游文档"保留意见"的处置

上游 `docs/mcp-protocol_zh.md` 自己写着「**NOTICE: AI 辅助生成, 在实现后台服务时, 请参照代码确认细节!!**」。
⇒ 本模块采取**宽松解析**：未知字段**原样保留并回传**、缺失可选字段不报错。
理由：文档可能滞后于固件，**"校验太严"比"宽松"更危险**（会因为我们拒收而丢消息）。
测试里专门有一条盯这个（多字段必须能往返）。

## §3 · 实现

| 文件 | 作用 |
|---|---|
| `mcpserver/zhi_mcp/envelope.py` | 信封 `{session_id,type,payload}` + JSON-RPC 2.0 编解码 + 错误码 + 文本块解析（**不猜类型**） |
| `mcpserver/zhi_mcp/transport.py` | 传输抽象 + `InMemoryTransport`/`LoopbackTransport`（语义分明的 send/deliver/inject）+ `FakeZhiDevice` |
| `mcpserver/zhi_mcp/client.py` | `ZhiMcpClient`：`initialize` → `tools/list`（**自动翻页 + 防无限翻页**）→ `tools/call`；`ToolCatalog`（命名空间/重名留痕/检索）+ 通知不丢 |
| `mcpserver/zhi_mcp/server.py` | `ZhiMcpBridge`（7 工具）+ CLI |
| `mcpserver/zhi_mcp/{agent-manifest.json,README.md,requirements.txt}` | 注册 / 文档 / 零依赖声明 |
| `mcpserver/zhi_mcp/sandbox/zhi-20261016-protocol-offline/` | 9 份离线真跑输出 |
| `tests/test_zhi_mcp.py`（35 用例） | 编解码 / 假设备 / 客户端 / 契约四层 |
| `docs/integration-graph/zhi_mcp.txt` | 依赖图（含**可插拔传输**的两条路径图） |

## §4 · 验证

- **测试 35 passed**；`ruff check .` 全仓 **All checks passed**
- **真跑证据**（sandbox，可复跑）：
  - `demo_handshake_paged.json`：3 个工具按每页 2 条 ⇒ **3 条请求**（1 initialize + 2 tools/list）
  - `demo_call_volume42.json`：`texts: ["true"]`、`is_error: false`
  - `demo_call_range_error.json`：**-32602**（越界）
  - `demo_call_unknown_tool.json`：**-32601** `Unknown tool: ...`（上游文档点名行为）
  - `parse_request.json`：判 kind = **request**（不是 response）
- **契约**：manifest ↔ `_TOOLS` **逐项相等**；entryPoint 真能解析到带 `handle_handoff` 的类；
  零第三方 import 由 AST 机械校验。

### 实现期抓出的 3 个真 bug（都由测试暴露）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 客户端发完请求一直等到超时 | 离线同线程**没人驱动假设备** | 加显式 `pump` 钩子（真实部署不需要） |
| 2 | `LoopbackTransport` 关闭后仍能发 | 覆写 `send` **绕过了基类的 closed 检查** | 覆写处自己再检一次 |
| 3 | 「有 id 且有 method」的报文被判成 `response` | 判定顺序写成了 `id → method`；**JSON-RPC 的请求同时有 id 与 method** | 改为 `通知 → 请求（有 method）→ 响应` |
| 4 | manifest JSON 非法 | 描述里用了**未转义的 ASCII 引号** | 改「」并加 `json.loads` 自检 |

## §5 · 未落地

1. **未接真设备** —— 本机无 ESP32；`FakeZhiDevice` 是**按文档写的测试替身**，真机报文细节需真设备复核
   （上游文档自己也要求"参照代码确认细节"）。
2. **未实现 WebSocket/MQTT 传输** —— 刻意留给调用方（见 §2.1）。
3. **未做云端 MCP 那一路** —— 上游文档只描述了设备端 MCP。
4. **未做多设备并发**（`session_id` 已贯穿全链路，但未做 session 级并发调度）。

## §6 · 复现

```bash
PY=.venv/Scripts/python.exe
$PY -m mcpserver.zhi_mcp.server spec
$PY -m mcpserver.zhi_mcp.server handshake --page-size 2
$PY -m mcpserver.zhi_mcp.server call --tool self.audio_speaker.set_volume --args '{"volume": 42}'
$PY -m pytest tests/test_zhi_mcp.py -q      # 35 passed
```
