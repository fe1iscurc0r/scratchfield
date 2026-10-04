# Lumo Bus 集成总线规范 v1

> **当前阶段: M4 / 实施状态: 仅规范，未实施 / 触发条件: N≥2 或 M5 完成**
> 基于行业最佳实践调研 + NEKO×陆墨融合实战经验
> 调研覆盖: Google A2A / AgentBus / 15 AI Agent Codebases / Azure Orchestration / EDA Anti-Patterns / Plugin Adapter Pattern

---

## 一、行业集成方案调研

### 1.1 Google A2A 协议（Apache 2.0, Linux Foundation 托管）

**定位**: agent-to-agent 通信标准，跨框架、跨供应商。2026 年 150+ 组织采用。

**三层架构**:

```
┌─────────────────────────────────────────┐
│  Discovery Layer (发现层)                 │
│  Agent Card: JSON 描述                    │
│  { name, capabilities, url, auth }       │
├─────────────────────────────────────────┤
│  Task Layer (任务层)                      │
│  State Machine:                          │
│  submit → working → completed/failed     │
│  + input-required / auth-required /      │
│    canceled / rejected                   │
├─────────────────────────────────────────┤
│  Transport Layer (传输层)                 │
│  JSON-RPC / gRPC / HTTP-REST             │
│  SSE Streaming + Push Notification       │
└─────────────────────────────────────────┘
```

**关键设计决策 5 条**:
1. **Embrace agentic capabilities** — 不把 agent 降级为 tool，保留非结构化交互能力
2. **Agent Card = 标准化清单** — 每个 agent 发布一个机器可读的 JSON，声明能力/端点/鉴权
3. **Task 是不可变对象** — 一次创建后不可修改，只能追加 Artifact
4. **streaming + push 双通道** — SSE 用于实时流，Push Notification 用于异步通知
5. **MCP 互补** — MCP 连接 agent 到工具，A2A 连接 agent 到 agent

**对 Lumo Bus 的映射**:
- Agent Card → 新库接入时必写的 JSON 清单
- Task 状态机 → 适用于异步任务（如 TTS 合成），不适用于即时 speak
- Streaming → 已有 lumo_proxy SSE

---

### 1.2 AgentBus（GitHub: Kanevry/agentbus, MIT）

**定位**: 轻量自托管事件总线，webhook 进 → agent 动作出。

**核心架构**:
```
webhook (外部事件源)
    │
    ▼
AgentBus Core
    ├─ 路由规则 (match payload field → agent)
    ├─ 重试队列 (内置 backoff)
    └─ 分发 (HTTP POST → agent endpoint)
```

**设计原则**:
1. **不做重复工作** — HTTP server / retry / queue 全部内置，接入方只写逻辑
2. **任何 AI 框架兼容** — CrewAI / LangGraph / OpenAI SDK / 裸 HTTP 都行
3. **Self-hosted** — 你控制路由规则，不依赖云服务

**对 Lumo Bus 的映射**:
- 你的 `lumo_event` 就是当前的手动版 AgentBus
- 缺的是: 路由规则 / 自动重试 / 多订阅者 fanout
- 可以后续加一个轻量的 `lumo_bus.py` 做路由层

---

### 1.3 "读了 15 个 AI Agent 代码库" — 关键教训（dev.to, 2026/04）

**分析对象**: Claude Code, OpenHands, Goose, Dify, TaskWeaver, MetaGPT, AutoGen, ChatDev, SWE-Agent, Aider, Devon, OpenDevin, Camel, CrewAI, Langroid

**5 条核心教训**:

| # | 教训 | 作者原话 | 对你的映射 |
|---|------|----------|-----------|
| 1 | **God Object 必然膨胀** | "Goose pushes all capabilities to MCP extensions, keeping the agent loop deliberately minimal. The lesson: if your architecture doesn't actively resist the God Object, you will grow one." | 露墨核心不 import 新库，只通过事件通道通信 |
| 2 | **MCP 是最稳定的扩展边界** | 绝大多数 codebase 用 MCP 隔离工具/能力。MCP Server 独立进程，崩溃不影响主循环 | 每个新库起独立 adapter 进程 |
| 3 | **ReAct loop 是共识，但不够** | 几乎所有 agent 都是 ReAct (observe→think→act)，但纯 ReAct 在长任务中退化 | 需要事件驱动的主动通知，不只是轮询 |
| 4 | **安全审计普遍缺失** | 15 个代码库中仅 3 个有输入验证，0 个有沙箱隔离 | require_proxy_token 已经比行业平均好 |
| 5 | **Memory 是最大差异化点** | "The memory system is where agents actually diverge — everyone does ReAct, but how you remember determines the ceiling" | M5 记忆融合要重视 |

---

### 1.4 Azure AI Agent 编排五模式（Microsoft, 2025）

| 模式 | 结构 | 适用场景 | 你的映射 |
|------|------|----------|----------|
| **Sequential** | A→B→C 管道 | 文档审查链 | ❌ 不需要 |
| **Handoff** | A 决定交给 B | LLM 判断后用哪个 agent | ✅ lumo_proxy 做 LLM 交接 |
| **Concurrent** | A+B+C 并行 | 同时调多个源 | ⚠️ 待建（多数据源并行检索） |
| **Group Chat** | 多 agent 自主对话 | 多智能体讨论 | ⚠️ 你已有铁锚/杜赞/Hermes/实验田维护者模式 |
| **Magnetic** | 动态路由到最合适的 agent | 意图识别后分发 | ⚠️ 需要总线支持 |

---

### 1.5 EDA 反模式（Event-Driven Architecture — 血的教训）

| # | 反模式 | 现象 | 你的经历 |
|---|--------|------|----------|
| 1 | **Command-Event Confusion** | 用事件来触发动作 → 循环/时序混乱 | M3 speak 踩过 |
| 2 | **Fat Events** | 事件携带过多数据 → 耦合放大 | lumo_event 有 Pydantic schema，已防护 |
| 3 | **No Retry/DLQ** | fire-and-forget 无回调 → 消息黑洞 | M4 done_callback 刚修 |
| 4 | **Inside Events Leaking** | 内部实现事件暴露给外部 → 外界依赖你的内部状态 | 需要 Bounded Context 隔离 |
| 5 | **Point-to-Point Instead of Bus** | N 个点对点连接 = N² 复杂度 | 你现在是 1 对 1，以后会炸 |

---

### 1.6 Plugin Adapter Pattern（Inferensys, 2026）

**定义**: 一个专用 adapter 插在核心系统与外部系统之间，负责协议转换。

```
┌──────────┐    标准接口     ┌──────────┐    原接口    ┌──────────┐
│ Lumo Bus │ ◄────────────► │ Adapter  │ ◄─────────► │ 新库 X   │
└──────────┘                └──────────┘             └──────────┘
                            翻译: 事件格式转换
                            错误映射
                            重试策略
                            协议转换(WS→HTTP等)
```

**关键原则**:
- Adapter 是独立进程，崩溃不拖累核心
- Adapter 只做翻译，不做业务逻辑
- 每个新库对应一个 adapter

---

## 二、Lumo Bus 规范（基于调研整合）

### 2.1 三层总线架构

```
                    ┌─────────────────────┐
                    │  Lumo Bus Core       │
                    │  (事件路由 + 指令分发)  │
                    └──────┬──────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                  │
    ┌────┴────┐      ┌─────┴─────┐     ┌─────┴─────┐
    │ Event   │      │ Command   │     │ Discovery │
    │ Channel │      │ Channel   │     │ Channel   │
    │ (反向)  │      │ (正向)    │     │ (双向)    │
    └─────────┘      └───────────┘     └───────────┘
    新库→露墨上报     露墨→新库指令      新库注册/心跳
```

### 2.2 新库接入三步 Checklist

```
第一步: 注册
  1. 写 Agent Card JSON (name/capabilities/endpoints/auth/events/commands)
  2. 在 lumo_event.py 注册新事件类型 (若现有 6 类不覆盖)
  3. 在 lumo_bus.py 注册路由规则 (若需要露墨→新库指令)

第二步: 进程隔离
  1. 起独立 adapter 进程 (不 import 露墨核心代码)
  2. require_proxy_token 鉴权 (复用, 不裸开端口)
  3. 错误降级链 (超时→重试→DLQ→告警)

第三步: 运行时验证
  1. Agent Card 心跳检测
  2. 事件收发 smoke test
  3. 指令执行 smoke test
```

### 2.3 Agent Card 模板

```json
{
  "name": "cosyvoice",
  "version": "1.0.0",
  "description": "CosyVoice TTS 引擎适配器",
  "license": "Apache-2.0",
  "capabilities": ["tts_synthesize", "voice_clone"],
  "endpoints": {
    "events": {
      "url": "http://127.0.0.1:8010/api/events",
      "auth": "proxy_token",
      "events_published": ["tts_start", "tts_end", "tts_error"]
    },
    "commands": {
      "url": "http://127.0.0.1:8010/api/commands",
      "auth": "proxy_token",
      "commands_accepted": ["speak_synthesize"]
    },
    "health": "http://127.0.0.1:8010/health"
  },
  "sandbox": {
    "level": "process",
    "network": "127.0.0.1 only",
    "filesystem": "read-only /opt/radio_brain/models/cosyvoice"
  },
  "resources": {
    "memory_mb": 512,
    "disk_mb": 2000,
    "gpu": "optional"
  }
}
```

### 2.4 事件类型注册表（可扩展）

```python
# 现存 6 类 — 已注册
class EventType(str, Enum):
    USER_INPUT = "user_input"
    ASR_RESULT = "asr_result"
    TTS_START = "tts_start"
    TTS_END = "tts_end"
    USER_ACTION = "user_action"
    ERROR = "error"

# 扩展模板 — 新库接入时在此注册
# class EventType(str, Enum):
#     RAG_HIT = "rag_hit"          # Materials Project 命中
#     SENSOR_DATA = "sensor_data"  # IoT 传感器数据
#     SCHEDULER_TICK = "scheduler_tick"  # 定时器触发
```

### 2.5 命令类型注册表（可扩展）

```python
# 现存 2 类 — 已注册
class CommandType(str, Enum):
    SPEAK = "speak"        # 注入说话指令
    EMOTION = "emotion"    # 注入表情切换

# 扩展模板
# class CommandType(str, Enum):
#     ACTION = "action"         # 通用动作指令
#     QUERY = "query"           # 通用查询指令
#     INJECT = "inject"         # 通用注入
```

---

## 三、行业反模式警示（摘自 EDA + 15 Codebases + AgentBus 文档）

| # | 反模式 | 现象 | 预防 |
|---|--------|------|------|
| 1 | **God Object** | 核心模块膨胀，import 所有新库 | 核心不 import，事件通道是唯一通信方式 |
| 2 | **命令当事件用** | "我让你说话"用事件推送 → 循环 | 命令走 Command Channel，事件走 Event Channel |
| 3 | **Fat Events** | 事件携带 10KB 上下文 | 事件只带 id + type，详细数据走 GET API |
| 4 | **Fire-and-Forget** | 无 done_callback → 消息黑洞 | 统一的 done_callback + DLQ |
| 5 | **点对点耦合** | N 个系统两两直连 = N² 复杂度 | 全部通过 Bus，消息格式标准化 |
| 6 | **无标准类型** | 每个新库自定事件格式 | 新事件类型先在 Pydantic schema 注册 |
| 7 | **内部事件泄露** | 内部实现细节对外暴露 | Bounded Context：只发布 Integration Events |
| 8 | **无版本管理** | Agent Card 改了就炸 | Card 带 version 字段 + 兼容性声明 |

---

## 四、从"集成地狱"到"PCIe 总线" — 路线图

### 现状（M4 完成时）
```
lumo_proxy + lumo_event + require_proxy_token
│ 自研 7 文件，已打通 NEKO，但每次新库要手写
```

### 短期（M4 smoke test 后）
```
│
├─ Agent Card 规范 + 模板 ← 这份文档
├─ lumo_event 事件类型注册表扩展
├─ 调试后门 /debug/dump/* ← 已定规范
│
```

### 中期（下一个库接入前）
```
│
├─ lumo_bus.py ← 简单路由层（参考 AgentBus）
│   路由规则 / 自动重试 / 多订阅者 fanout
├─ Adapter 进程模板 ← 新库照着改
│   agent_card.json + adapter.py + Dockerfile (可选)
│
```

### 长期（3+ 库接入后）
```
│
├─ Agent Card Registry ← 自动发现
├─ Health Check Dashboard ← 所有 adapter 心跳
├─ 沙箱级别选配 ← process / container / VM
│
```

---

## 五、参考资料

| 来源 | URL | 许可 | 关键价值 |
|------|-----|------|----------|
| Google A2A Protocol | github.com/a2aproject/A2A | Apache 2.0 | Agent Card + Task 状态机 |
| AgentBus | github.com/Kanevry/agentbus | MIT | Webhook 路由 + 重试 |
| 15 AI Agent Codebases | dev.to/neuzhou | 公开文章 | God Object / MCP 隔离 |
| Azure Agent Patterns | learn.microsoft.com | 公开文档 | 5 种编排模式 |
| EDA Anti-Patterns | codeopinion.com / ben-morris.com | 公开文章 | Command/Event 分离 |
| Plugin Adapter Pattern | inferensys.com | 公开文章 | Adapter 隔离模式 |

---

*整合: 实验田维护者 (deepseek-v4-pro)*
*数据来源: 2026-08 网络调研 + scratchpad M1-M4 实战*
*本规范为 Lumo Bus v1 草案，随下一个新库接入实战验证后升级为 v1.0*
