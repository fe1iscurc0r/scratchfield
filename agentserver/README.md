# NagaAgent Server

独立的智能体调度服务，提供任务管理、军牌系统（心跳检查 + 屏幕主动感知）和 OpenClaw 集成。

## 目录结构

```
agentserver/
├── agent_server.py          # FastAPI 主服务
├── config.py                # 服务配置（端口、OpenClaw 等）
├── utils.py                 # 工具函数（时间范围判断）
├── dogtag/                  # 军牌系统 — 统一后台任务调度
│   ├── models.py            #   DogTag / TriggerType / DutyStatus / ActivationCondition
│   ├── registry.py          #   DogTagRegistry 任务池（注册 / 查询 / 状态管理）
│   ├── scheduler.py         #   DogTagScheduler 统一调度器（主循环 + 事件驱动）
│   ├── checklist.py         #   心跳持久化待办清单
│   ├── heartbeat_config.py  #   心跳配置模型与持久化
│   ├── heartbeat_prompt.py  #   心跳 LLM 提示词模板
│   ├── duties/
│   │   ├── heartbeat_duty.py      # 心跳执行器 + DogTag 工厂
│   │   └── screen_vision_duty.py  # 屏幕感知 DogTag 工厂
│   └── screen_vision/       #   屏幕主动感知子系统
│       ├── config.py        #     触发规则与配置模型
│       ├── config_loader.py #     默认规则与配置持久化
│       ├── analyzer.py      #     截屏分析引擎（感知哈希 + AI）
│       ├── trigger.py       #     消息发送与冷却控制
│       └── metrics.py       #     Prometheus 风格指标
├── openclaw/                # OpenClaw 集成
│   ├── openclaw_client.py   #   Gateway HTTP 客户端
│   ├── embedded_runtime.py  #   内嵌 Node.js 运行时管理
│   ├── detector.py          #   安装状态检测
│   ├── config_manager.py    #   配置安全编辑器
│   ├── llm_config_bridge.py #   LLM 配置自动生成
│   ├── installer.py         #   安装编排
│   └── test_connection.py   #   连接测试
└── OPENCLAW_FLOW.md         # OpenClaw 调度流程文档
```

## 核心组件

### Agent Server (`agent_server.py`)

FastAPI 主服务，统一管理以下子系统：
- DogTag — 军牌系统，统一调度心跳检查与屏幕主动感知
- OpenClaw Client — 与 OpenClaw Gateway 通信，执行电脑操作任务

### DogTag — 军牌系统 (`dogtag/`)

统一后台任务调度系统，将心跳检查和屏幕感知纳入同一个调度框架管理。

**核心架构：**

```
DogTagScheduler（统一调度器）
  ├── DogTagRegistry 任务池
  │     ├── [heartbeat]      事件驱动，对话结束 → 延迟 N 分钟 → LLM 检查
  │     └── [screen_vision]  周期执行，每 N 秒 → 截屏 → AI 分析 → 规则匹配
  │
  ├── 全局状态
  │     ├── window_mode          (classic / ball / compact / full)
  │     ├── conversation_active
  │     └── last_user_activity
  │
  └── 调度逻辑
        ├── 主循环 (1s tick)  → 遍历周期任务 → 检查条件 → 执行
        └── 事件回调          → 对话结束 → 启动延迟倒计时 → 执行
```

**DogTag 数据模型：**
- `TriggerType`：`EVENT_DRIVEN`（事件驱动）/ `PERIODIC`（周期执行）
- `DutyStatus`：`ENABLED` / `DISABLED` / `PAUSED`
- `ActivationCondition`：窗口模式过滤、活跃时段、用户活跃度要求

**心跳检查（`heartbeat` 职责）：**
- 对话结束后延迟触发，调用 LLM 审查对话历史
- 管理持久化待办清单（`~/.naga/heartbeat_checklist.json`）
- 支持清单指令：`[ADD_ITEM]`、`[DONE_ITEM]`、`[DISMISS_ITEM]`
- 静默模式：LLM 回复 `HEARTBEAT_OK` 且字数少于阈值时不推送
- 遵守活跃时段配置

**屏幕感知（`screen_vision` 职责）：**
1. 定时截取屏幕截图
2. 感知哈希（pHash/dHash/aHash）对比前后帧差异
3. 画面无变化时跳过 AI 分析（节省 API 调用）
4. 画面变化时调用 AI（screen_vision MCP 服务）分析内容
5. 匹配触发规则（关键词 + AI 判断），满足条件时推送消息

运行条件：
- 仅在悬浮球模式（ball/compact/full）下运行，经典模式自动暂停
- 遵守安静时段和用户活跃度设置
- 每条规则独立冷却时间，避免重复触发

### OpenClaw — 电脑操作代理 (`openclaw/`)

与 OpenClaw Gateway 的完整集成：
- **检测**：自动检测 OpenClaw 安装状态、Gateway 配置、Hooks 配置
- **安装**：支持自动安装和内嵌运行时（打包模式）
- **配置**：白名单式安全配置编辑，自动生成 LLM 配置
- **通信**：通过 HTTP 与 Gateway 通信，支持消息发送、工具调用、会话管理
- **任务追踪**：本地任务状态追踪，持久化会话 ID

详见 [OPENCLAW_FLOW.md](./OPENCLAW_FLOW.md)

## API 接口总览

### 健康检查 & 调度

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 基础健康检查 |
| GET  | `/health/full` | 完整系统健康检查 |

### 军牌系统（统一调度）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/dogtag/status` | 调度器状态 + 全部任务状态 |
| GET  | `/dogtag/duties` | 已注册任务列表 |
| POST | `/dogtag/duties/{id}/enable` | 启用指定任务 |
| POST | `/dogtag/duties/{id}/disable` | 禁用指定任务 |
| POST | `/dogtag/duties/{id}/trigger` | 手动触发指定任务 |
| POST | `/dogtag/conversation_event` | 对话生命周期事件 |

### 心跳系统

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/heartbeat/conversation_event` | 对话生命周期事件（委托给军牌系统） |
| GET  | `/heartbeat/config` | 获取心跳配置 |
| POST | `/heartbeat/config` | 更新心跳配置 |
| POST | `/heartbeat/enable` | 启用/禁用心跳 |
| POST | `/heartbeat/trigger` | 手动触发心跳 |
| GET  | `/heartbeat/status` | 心跳状态 |
| GET  | `/heartbeat/checklist` | 待办清单 |
| POST | `/heartbeat/checklist` | 添加待办项 |
| PUT  | `/heartbeat/checklist/{item_id}` | 更新待办项 |
| DELETE | `/heartbeat/checklist/{item_id}` | 删除待办项 |

### 屏幕主动感知

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/proactive_vision/config` | 获取感知配置 |
| POST | `/proactive_vision/config` | 更新感知配置 |
| POST | `/proactive_vision/enable` | 启用/禁用 |
| GET  | `/proactive_vision/status` | 运行状态 |
| POST | `/proactive_vision/trigger/test` | 测试触发 |
| POST | `/proactive_vision/activity` | 更新用户活跃度 |
| POST | `/proactive_vision/window_mode` | 设置窗口模式 |
| POST | `/proactive_vision/reset_timer` | 重置检查计时器 |
| GET  | `/proactive_vision/metrics` | 性能指标 |
| GET  | `/proactive_vision/metrics/prometheus` | Prometheus 格式指标 |

### OpenClaw 集成

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/openclaw/health` | OpenClaw 健康检查 |
| GET  | `/openclaw/status` | 运行状态 |
| GET  | `/openclaw/config` | 获取配置 |
| POST | `/openclaw/config` | 初始化配置 |
| POST | `/openclaw/config/set` | 修改配置 |
| POST | `/openclaw/config/model` | 设置模型 |
| POST | `/openclaw/config/hooks` | 配置 Hooks |
| POST | `/openclaw/send` | 发送消息 |
| POST | `/openclaw/wake` | 唤醒 |
| POST | `/openclaw/tools/invoke` | 调用工具 |
| GET  | `/openclaw/session` | 会话信息 |
| GET  | `/openclaw/history` | 历史记录 |
| GET  | `/openclaw/tasks` | 本地任务列表 |
| GET  | `/openclaw/tasks/{task_id}` | 任务详情 |
| GET  | `/openclaw/tasks/{task_id}/detail` | 任务完整详情 |
| DELETE | `/openclaw/tasks/completed` | 清除已完成任务 |
| GET  | `/openclaw/install/check` | 检查安装状态 |
| POST | `/openclaw/install` | 安装 OpenClaw |
| POST | `/openclaw/setup` | 初始化设置 |
| GET  | `/openclaw/doctor` | 诊断检查 |
| POST | `/openclaw/gateway/start` | 启动 Gateway |
| POST | `/openclaw/gateway/stop` | 停止 Gateway |
| POST | `/openclaw/gateway/restart` | 重启 Gateway |
| POST | `/openclaw/gateway/install` | 安装 Gateway 服务 |
| GET  | `/openclaw/gateway/status` | Gateway 状态 |
| GET  | `/openclaw/skills` | 技能列表 |
| POST | `/openclaw/skills/install` | 安装技能 |
| POST | `/openclaw/skills/enable` | 启用技能 |

### 旅行功能

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/travel/execute` | 执行旅行会话 |

## 启动方式

### 统一启动（推荐）

通过 `main.py` 统一启动所有服务：

```bash
python main.py
```

### 独立启动（开发调试）

```bash
uvicorn agentserver.agent_server:app --host 0.0.0.0 --port 8001
```

## 与 apiserver 的关系

- apiserver（端口 8000）是面向前端的 API 层
- agentserver（端口 8001）是后端智能体调度层
- apiserver 通过 HTTP 调用 agentserver 的接口（如 `/openclaw/*`）
- 军牌系统通过 apiserver 的 `/queue/push` 推送消息给前端
