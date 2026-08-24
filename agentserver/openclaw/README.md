# OpenClaw 集成说明

## 概述

NagaAgent 现已集成 OpenClaw Gateway，支持通过自然语言调度 OpenClaw AI 助手。

**官方文档**: https://docs.openclaw.ai/

## OpenClaw 简介

OpenClaw 是一个自托管的 AI Gateway，可以连接 WhatsApp、Telegram、Discord、iMessage 等多个聊天平台到 AI 编程助手。

## 配置

### 默认配置

- **Gateway 地址**: `http://localhost:18789` (OpenClaw 默认端口)
- **认证**: 使用 `Authorization: Bearer <token>` 头

### 配置 OpenClaw 连接

```bash
# 通过 API 配置
curl -X POST http://localhost:8001/openclaw/config \
  -H "Content-Type: application/json" \
  -d '{
    "gateway_url": "http://localhost:18789",
    "token": "your-token-here"
  }'
```

## API 端点

### 核心功能

| 端点 | 方法 | 说明 | 对应 OpenClaw API |
|------|------|------|-------------------|
| `/openclaw/health` | GET | 健康检查 | - |
| `/openclaw/config` | POST | 配置连接 | - |
| `/openclaw/send` | POST | 发送消息给 Agent | `POST /hooks/agent` |
| `/openclaw/wake` | POST | 触发系统事件 | `POST /hooks/wake` |
| `/openclaw/tools/invoke` | POST | 直接调用工具 | `POST /tools/invoke` |

### 任务管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/openclaw/tasks` | GET | 获取所有本地任务 |
| `/openclaw/tasks/{task_id}` | GET | 获取单个任务 |
| `/openclaw/tasks/completed` | DELETE | 清理已完成任务 |

## 使用示例

### 发送消息给 OpenClaw Agent

```bash
curl -X POST http://localhost:8001/openclaw/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我分析这个项目的架构",
    "session_key": "my-session",
    "name": "Naga"
  }'
```

### 触发系统事件

```bash
curl -X POST http://localhost:8001/openclaw/wake \
  -H "Content-Type: application/json" \
  -d '{
    "text": "检查邮件",
    "mode": "now"
  }'
```

### 直接调用工具

```bash
curl -X POST http://localhost:8001/openclaw/tools/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "Read",
    "args": {"file_path": "/path/to/file"}
  }'
```

## 自然语言调度

当用户对 NagaAgent 说以下话语时，系统会自动调度 OpenClaw：

- "跟 openclaw 说帮我分析这个项目"
- "让 openclaw 帮我写一份报告"
- "用 openclaw 帮我查询..."
- "告诉 openclaw..."

### 工作流程

```
用户: "跟openclaw说帮我分析代码"
        ↓
Agentic Tool Loop 识别 agentType: "openclaw"
        ↓
POST http://localhost:8001/openclaw/send
        ↓
OpenClawClient.send_message()
        ↓
POST http://localhost:18789/hooks/agent
```

## Python 使用示例

```python
from agentserver.openclaw import OpenClawClient, OpenClawConfig

# 创建客户端
config = OpenClawConfig(
    gateway_url="http://localhost:18789",
    token="your-token"
)
client = OpenClawClient(config)

# 发送消息
async def send_task():
    task = await client.send_message(
        message="帮我分析这份代码",
        session_key="analysis-001",
        name="Naga"
    )
    print(f"任务ID: {task.task_id}")
    print(f"状态: {task.status}")

# 调用工具
async def invoke_tool():
    result = await client.invoke_tool(
        tool="Read",
        args={"file_path": "/path/to/file"}
    )
    print(result)

# 触发事件
async def wake_agent():
    result = await client.wake(
        text="检查新消息",
        mode="now"
    )
    print(result)
```

## 注意事项

1. 确保 OpenClaw Gateway 已启动并运行在 `localhost:18789`
2. 如果启用了认证，需要配置正确的 token
3. OpenClaw 的 Cron 任务通过 Gateway 内部管理，不通过 HTTP API

## 渠道接入建议

### 飞书

飞书应优先走 OpenClaw 原生渠道能力，而不是在 Naga 外层模拟消息通道。

- Naga 侧配置入口：`config.openclaw.feishu`
- 启动时会由 [`llm_config_bridge.py`](/Users/qr/Documents/NagaAgentNew/NagaSkill/agentserver/openclaw/llm_config_bridge.py) 注入到 OpenClaw 的 `channels.feishu`
- 建议在从飞书触发探索/长任务时，同时记录：
  - `deliver_channel = "feishu"`
  - `deliver_to = <open_id 或 chat_id>`

这样探索完成后的完整版报告可以直接按飞书会话回传。

### QQ

QQ 暂不建议作为 OpenClaw 原生渠道接入。

- vendored OpenClaw 没有明显的一等 QQ channel 实现
- 更稳的做法是：QQ 入站和出站继续由 Naga 自己负责
- Naga 只把任务执行委托给 OpenClaw，结果再由 Naga 发回 QQ

### 探索任务回传字段

旅行/探索 session 现在支持这些字段：

- `post_to_forum`
- `deliver_full_report`
- `deliver_channel`
- `deliver_to`

其中：

- `post_to_forum=true` 时，探索完成后会尝试自动发布论坛精华帖
- `deliver_full_report=true` 时，探索完成后会尝试将完整版报告按 `deliver_channel / deliver_to` 回传
