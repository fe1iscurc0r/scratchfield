# mcpserver — 工具总线（使用+维护指南）

这是全系统的"能力插座"：所有工具（MCP）在这里注册、调度。FastAPI 入口 + 三表注册中心 + 统一调度。

## 你能用的工具（使用者视角）

| 模块 | 做什么 | 怎么调 |
|------|--------|--------|
| material_science | 科研（matchat 桥/生物预测/数据集构建） | Lumo 里直接说需求 |
| rf_brain | 射频解调链（建设中） | 等真机 |
| agent_game_guide | 游戏攻略 | 问陆墨 |
| agent_open_launcher | 打开应用 | 说"打开XX" |
| agent_screen_vision | 屏幕视觉 | 截图分析 |
| agent_weather_time | 天气时间 | 问"天气" |
| tts_api | 语音合成 | 桌宠说话 |

## 外部 MCP 服务（可启用，默认关闭）

- toolbox-postgres（数据库）、swarmvault（LLM Wiki/RAG）、mentedb（记忆引擎）、arcrift（编程跨会话记忆）、apify（网页抓取）
- 启用：改 `external_services.example.json` → 合入 `~/.mcporter/config.json`，置 `false` 生效

## 架构三句话

1. **三表注册**：MCP_REGISTRY（服务池）+ MANIFEST_CACHE（manifest 缓存）+ _ADAPTER_CAPABILITIES（adapter 能力）
2. **统一调度**：`POST /schedule` → MCPManager.unified_call() 路由
3. **适配层**：adapters/ 只做凭证 fail-fast + sys.path 注入 + 暴露函数，业务在 vendor 代码里

## 加新工具（开发者）

1. `mcpserver/<name>/` 建目录 + `agent-manifest.json`（name/description/tools/entryPoint，支持 A/B/C/D 四种格式）
2. 或走 mcporter_bridge 外部服务
3. 注册冲突自动检测（WARNING 不阻断）

## 测试与规范

```bash
python -m pytest tests/test_mcp_adapters.py -x   # MCP 适配层
python -m ruff check .                            # 格式化检查
```

- 模块加载白名单：只允许 `mcpserver.` / `vendor.` 前缀
- Adapter 健康检查不过自动跳过，不让全局启动失败
- API Key 走环境变量，不硬编码绝对路径

## 企业级参考（规模化时抄）

- `mcp-gateway-registry`（MIT）：OAuth/Keycloak 集中鉴权、动态工具发现、安全扫描
- `arcade-mcp`（MIT）：Python MCP 框架，声明式 OAuth（GitHub scopes 等 22 provider）

---
*维护：实验田维护者 2026-08-22*
