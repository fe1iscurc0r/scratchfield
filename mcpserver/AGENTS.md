# mcpserver/ — Agent 引导

本模块是陆墨的 MCP（Model Context Protocol）工具体系，负责第三方能力包的 manifest 注册、agent 实例创建、统一工具调度与服务发现。

## 模块职责

- **三表注册中心**：`MCP_REGISTRY`（服务池）、`MANIFEST_CACHE`（manifest 缓存）、`_ADAPTER_CAPABILITIES`（adapter 能力登记）
- **统一调度**：`MCPManager.unified_call()` 路由工具调用到正确的 agent 实例
- **本地 Agent**：内置 agent 子模块（game_guide / open_launcher / screen_vision / weather_time / material_science）
- **适配层**：`adapters/` 封装第三方 vendor 能力（vulnclaw / agent_reach / memclaw / headroom / paper_miner / llm4decompile / markitdown）
- **外部 MCP 桥接**：`mcporter_bridge.py` 加载外部 MCP 服务配置
- **外部服务模板**：`external_services.example.json` 提供 mcporter 格式的外部 MCP 服务接入模板（合入 `~/.mcporter/config.json` 生效）
- **外部服务清单**：toolbox-postgres（Google 数据库 MCP）、swarmvault（LLM Wiki/RAG）、mentedb（AI 记忆引擎）、arcrift（编程跨会话记忆）、apify（网页抓取/搜索/数据提取 MCP）——默认 `_disabled`，就绪后置 `false` 启用
- **企业级参考**：`mcp-gateway-registry`（agentic-community，MIT）是 MCP 网关/注册中心的**基础设施参考**——集中鉴权（OAuth/Keycloak/Cognito）、动态工具发现、安全扫描、服务注册。本仓 `mcp_registry.py` 是轻量版，规模化（多 server 集中管理/细粒度 scope/审计）时可借其架构
- **框架参考**：`arcade-mcp`（ArcadeAI，MIT）是 Python 构建 MCP server/tools 的**框架参考**——decorator API 覆盖全 MCP spec、`requires_auth=GitHub(scopes=...)` 声明式 OAuth（token 注入不落 LLM）、22 个现成鉴权 provider。本仓自制 agent 需带鉴权时借其声明式鉴权模式
- **独立部署参考**：`TTS-WebUI`（rsxdalv，MIT codebase）是重型 TTS/Audio**独立部署服务**——Gradio+React 全功能 UI、多 TTS 模型（含 Kokoro）、OpenAI 兼容端点 `/v1/audio/speech`。与已融合的 `kokoro-onnx` 离线兜底互补；本仓不内置，仅在需要全功能 TTS 服务作独立部署时参考其 OpenAI 兼容 API 与扩展机制
- **安全边界**：`security_utils.py` 提供模块加载白名单与路径校验

## 关键入口文件

| 文件 | 职责 |
|------|------|
| `mcp_server.py` | FastAPI HTTP 入口，`POST /schedule` 统一调度 |
| `mcp_registry.py` | 三表注册中心，manifest 扫描/加载/查询，跨源冲突检测 |
| `mcp_manager.py` | `MCPManager` 单例，`unified_call` 路由 |
| `mcporter_bridge.py` | 外部 MCP 服务加载与 `ExternalMCPAgent` 封装 |
| `security_utils.py` | 模块加载白名单（`ALLOWED_MODULE_PREFIXES`）与路径校验 |
| `adapters/__init__.py` | `register_all_adapters()` 总入口 |
| `__init__.py` | 包级文档字符串，描述子模块职责 |

## 数据契约位置

- **Agent Manifest**：各子模块下的 `agent-manifest.json`（定义 name/description/tools/entryPoint）
  - `agent_game_guide/agent-manifest.json`
  - `agent_open_launcher/agent-manifest.json`
  - `agent_screen_vision/agent-manifest.json`
  - `agent_weather_time/agent-manifest.json`
  - `material_science/agent-manifest.json`
- **调度请求/响应**：`mcp_server.py` 中的 `ScheduleRequest`、`ToolCallRequest`
- **适配层契约**：`adapters/README.md` — 每个 adapter 的职责（凭证 fail-fast / sys.path 注入 / 暴露适配函数）
- **注册表全局状态**：`mcp_registry.py` 中的 `MCP_REGISTRY`、`MANIFEST_CACHE`、`_ADAPTER_CAPABILITIES`

## 测试路由

```bash
# MCP 适配层测试
python -m pytest tests/test_mcp_adapters.py -x

# 全量测试（包含 MCP 相关）
python -m pytest tests/ -x
```

## 模块特有约束

1. **模块加载白名单**：`ALLOWED_MODULE_PREFIXES = ["mcpserver.", "vendor."]`，只允许这两个前缀的模块通过 `importlib` 动态加载。
2. **跨源冲突检测**：manifest / mcporter / adapter 三条写入路径各自维护注册表，登记前统一调用 `_check_cross_source_conflict()` 做跨源检测。不做阻断，只打 WARNING 并在 `list_registered_capabilities` 附 `conflict_sources` 字段。
3. **Adapter 不做业务逻辑**：`adapters/` 只做凭证 fail-fast、sys.path 注入、暴露适配函数，直接透传 vendor 代码里的已注册工具。
4. **Adapter 健康检查**：未通过健康检查（凭证缺失/依赖未装/Windows Rust wheel 不可用等）的 adapter 自动跳过并打日志，不让全局启动失败。
5. **entryPoint 多格式支持**：manifest 支持 Format A (spec) / B (legacy) / C (string) / D (derive from dirname) 四种格式。
6. **外部 MCP 服务**：通过 `mcporter_bridge.py` 加载，封装为 `ExternalMCPAgent`，与本地 manifest agent 共享 `MCP_REGISTRY`。
7. **material_science 模块**：包含 matchat_bridge（材料数据库桥接）、biopred（生物预测）、build_dataset（数据集构建）等科研工具，是体积最大的 agent 子模块。
8. **Python 格式化**：使用 `ruff`（`python -m ruff check .`）。
9. **不要硬编码绝对路径**，所有 API Key/Token 走环境变量。
