# apiserver/ — Agent 引导

本模块是陆墨的 FastAPI 后端服务层，提供 RESTful API 接口，连接前端 UI 与后端智能体/LLM/MCP 工具链。

## 模块职责

- 对话处理：普通对话 (`/chat`) 和流式 SSE 对话 (`/chat/stream`)
- 认证与会话管理：NagaCAS 登录/注册/Token 刷新、会话 CRUD
- 工具调度：Agentic 工具调用循环、WebSocket 实时通信、工具状态轮询
- 扩展功能：OpenClaw 市场/任务、MCP 服务管理、技能导入、旅行系统、记忆查询
- TTS/ASR 代理：语音合成与识别透传
- 系统管理：配置读写、健康检查、版本更新、日志统计

## 关键入口文件

| 文件 | 职责 |
|------|------|
| `api_server.py` | FastAPI 实例、lifespan、CORS 中间件、Pydantic 公共模型、路由注册 |
| `start_server.py` | 统一启动脚本（`python apiserver/start_server.py api`） |
| `llm_service.py` | LLM API 调用（支持本地/网关两种模式） |
| `message_manager.py` | 会话与消息统一管理 |
| `agentic_tool_loop.py` | Agentic 工具调用循环（流式/非流式） |
| `intent_router.py` | 意图路由（技能选择） |
| `routes/` | 按功能域拆分的路由模块（chat/auth/session/system/tools/extensions） |

## 数据契约位置

- **请求/响应模型**：`api_server.py` 中的 Pydantic `BaseModel`（`ChatRequest` 等）
- **工具 Schema 生成**：`tool_schemas.py` — 将 MCP manifests + OpenClaw 工具表转换为 OpenAI function calling 格式
- **路由级模型**：`routes/*.py` 中各路由模块内定义的请求/响应模型
- **配置契约**：`system/config.py` — `config.json` 读写与默认值
- **技能模板**：`skills_templates/` — 内置技能的 SKILL.md 模板

## 测试路由

```bash
# 后端冒烟测试（无账号）
uv run python scripts/smoke_backend.py --skip-auth --start-if-needed

# 后端冒烟测试（有 NagaCAS 账号）
uv run python scripts/smoke_backend.py --username "$NAGA_SMOKE_USERNAME" --password "$NAGA_SMOKE_PASSWORD" --start-if-needed

# 配置与工具相关单元测试
python -m pytest tests/test_config_and_tools.py -x

# 更新与 TTS 测试
python -m pytest tests/test_updates_and_tts.py -x
```

## 模块特有约束

1. **认证链路**：所有需要身份的接口走 NagaCAS（`naga_auth.py`）。未登录且 `api.use_gateway=false` 时，OpenAI 兼容代理只接受真实本地 API 配置，占位 key 会被拒绝。
2. **网关模式**：`api.use_gateway=true` 时 LLM 调用走 NagaModel 网关；`false` 时直连本地 API。`/tts/speech` 在网关模式下使用角色元数据中的 voice，否则回退到本地 Edge TTS。
3. **配置持久化**：`/system/config` 读写 `config.json`，优先项目根目录，回退用户数据目录。保存时过滤运行时不稳定字段。
4. **技能名称安全**：技能管理接口只允许单段名称，禁止路径穿越（`..`、`/`、`\`、绝对路径、控制字符）。
5. **流式 SSE**：`/chat/stream` 通过 SSE 推送文本片段，`streaming_tool_extractor.py` 负责句子切割和 TTS 推送。
6. **WebSocket**：`websocket_manager.py` 管理连接，`/ws` 为实时通信端点。
7. **工具函数命名**：`tool_schemas.py` 生成 `{agentType}__{service_name}__{tool_name}` 格式，MCP 中文/空格名经 sanitize 后登记到 `_mcp_name_map` 反查。
8. **上游更新源**：`/update/latest` 以 GitHub Latest Release 为主源，NagaBusiness 为回退源。
9. **Python 格式化**：使用 `ruff`（`python -m ruff check .`）。
10. **不要硬编码绝对路径**，所有 API Key/Token 走环境变量。
