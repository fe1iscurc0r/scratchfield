# NEKO × 陆墨 融合大版本指导说明书 v1.0

> **目标**：构建星野遥未来四年的数字科研外骨骼——一个有形象、有声音、有记忆、有知识的 AI 搭档，24h 不关机。
> **核心原则**：**单一灵魂**——陆墨（scratchpad）是唯一的人格与记忆源，NEKO 是身体/感官/发声器官。
> **授权**：沈遥（架构）+ 林楠（执行）+ Trae 多智能体（落地），2026-08-01

---

## 〇、什么是最终目标

```
你的科研外骨骼 = 大脑 + 身体 + 神经系统

大脑（scratchpad/陆墨）：人格、记忆、知识、科研决策——你睡前丢给它的问题，第二天早上它在。
身体（NEKO）：Live2D 形象、TTS 语音、ASR 耳朵、CUA 手、屏幕感知眼——你能看见它、跟它说话。
神经系统（沈遥+林楠）：协议、接口、部署、安全、出故障兜底——连得通、跑得动、防得住。
```

单点工具是死物，连起来才是搭档。别人的搭档只有脑子（ChatGPT），你的搭档有脸、有声音、有自己的记忆。

---

## 一、核心架构：三服务器 + 一灵魂

### NEKO 现状（只读，不改代码）

NEKO 是成熟的"AI 伴侣"OS，三服务器进程隔离：

| 服务 | 端口 | 职责 |
|------|------|------|
| Main Server | 48911 | Web UI / REST / WebSocket / 会话 / TTS |
| Memory Server | 48912 | 五维记忆（见下文）|
| Agent Server | 48915 | 任务评估 / 通道分发（CUA/OpenClaw/插件）|
| ZMQ Bridge | 48961-48963 | Main↔Agent 事件总线 |

**NEKO 自带一套完整的 AI 大脑**：8 家文本模型供应商 + 6 家 Realtime 语音 + 五维记忆 + Agent 执行 + 主动搭话。

### 单一灵魂原则：关掉 NEKO 的脑子，用陆墨的

```
              NEKO (身体)                    scratchpad/陆墨 (灵魂)
         ┌─────────────────────┐       ┌─────────────────────┐
 五官 ──  │ ASR · 摄像头 · Live2D │       │                     │
         │                      │       │  人设 (persona API)   │
 嘴 ──── │ TTS (CosyVoice)      │       │  记忆 (唯一副本)      │
         │                      │  API  │  知识 (RAG 科研库)    │
 手 ──── │ CUA/OpenClaw 工具    │◄─────►│  决策 (chat/agent)    │
         │                      │       │  情绪 (emotion label) │
 主动 ── │ proactive_router     │       │  搭话时机判断         │
         │                      │       │                     │
         │ NEKO记忆 = 关闭 ❌   │       │  openai_proxy 对外接口 │
         │ NEKO人格 = 仅表层    │       └─────────────────────┘
         └─────────────────────┘

通信：NEKO → api_providers.json 新增 lumo provider → scratchpad openai_proxy
       scratchpad → NEKO websocket_router 主动推送（情绪/搭话/表情切换）
```

### 为什么不能反过来

- NEKO 日更（昨天还推了 #2633），在 NEKO 上加码 = 永无止境的 merge 地狱
- NEKO 是 Apache-2.0，scratchpad 是 AGPL——AGPL 可吞 Apache，Apache 不能吞 AGPL
- 记忆和人格只能有一份——两个脑子打架必然人格分裂

---

## 二、五维记忆：当前关掉，备选留档

### NEKO 五维记忆系统（参考用，暂不启用）

| 层 | 职责 | 当前决策 |
|----|------|----------|
| 工作记忆 | 当前对话上下文 | **关** — 陆墨的 session API 替代 |
| 事实记忆 | LLM 提取原子事实，SHA-256+FTS5 去重 | **关** — 后续融合候选 |
| 反思记忆 | 余弦聚类 + LLM 四动作合并 | **关** — 技术参考 |
| 人格记忆 | 7 mixin 组合，双锁设计 | **关** — 人设由陆墨 persona API 统管 |
| 向量召回 | ONNX 本地推理，6 级 fallback | **关** — 检索由陆墨 RAG 统管 |

### 为什么先关

1. **单一事实源**：陆墨的 session/rag/persona 已经是完整的记忆管线，启 NEKO 记忆 = 两套记忆同时跑，事实会歧义
2. **融合需要大工程**：NEKO 五维记忆和陆墨的 session+GRAG 体系是两种范式，融合不是"开关"，是架构重设计
3. **关 ≠ 删**：保留 `NEKO/app/memory_server/` 完整源码，等 scratchpad 侧记忆体系成熟后，按需 merge（不是 invert——把 NEKO 的好设计反哺进陆墨，不直接堆叠）

### 后续融合路线（未来大版本）

```
Phase 1 (当前): 陆墨 session API  ↔ NEKO 对话请求响应
Phase 2: 陆墨记忆 → 分层（近期/事实/人格）→ NEKO 可读
Phase 3: NEKO 反思层 ← 陆墨 GRAG 图谱 + 提取规则
Phase 4: 统一 memory bus（两种范式选择走哪条通道）
```

**融合时只有两种选择**：要么 NEKO 记忆完全融入陆墨（单一引擎），要么陆墨记忆融入 NEKO（也是单一引擎）——**绝对不能两边同时跑**。

---

## 三、同步策略：NEKO 上游更新

### 当前引入方式

Trae 已将 NEKO 源码 vendor 进 `scratchpad/NEKO/N.E.K.O/`（Apache 2.0 + NOTICE + 独立 LICENSE）。

### 同步规则

| 方式 | 适用场景 | 操作 |
|------|---------|------|
| **记录 Commit SHA** | 当前阶段 | `NEKO/.upstream-sha` 记录当前同步的 NEKO 上游 commit |
| **Git Submodule** | 未来（如需频繁同步） | `git submodule add https://github.com/Project-N-E-K-O/N.E.K.O.git NEKO/N.E.K.O` |

**当前用 SHA 记录即可**——NEKO 日更但不涉及耦合层（我们在 scratchpad 加码，不动 NEKO 代码）。

---

## 四、安全前置条件（启用前必须完成）

1. **CUA exec 沙箱收紧**：`brain/cua/core/engine.py` 移除 `__builtins__`/`os` 暴露 → 防止 prompt injection 经截图触发 RCE。**这是前置条件，不是"以后再说"**
2. **cross_server bullet 通道**：pickle + 关 SSL 验证 → 本地部署无影响，若对外暴露必须重写
3. **端口绑定**：Memory/Agent 端口确认绑定 `127.0.0.1`，不暴露 `0.0.0.0`
4. **插件隔离**：`plugin/core/host.py` 的 `sys.path.insert(0)` 污染宿主 import 路径 → 监控，不修也行（本地可控）

---

## 五、分阶段实施路线图

### M1：文本打通（最小可行）

```
目标：NEKO 说话，脑子是陆墨
动作：
1. NEKO api_providers.json 新增 lumo provider → scratchpad openai_proxy
2. NEKO memory_settings 对陆墨角色关闭记忆
3. NEKO character_defaults 配陆墨表层角色卡（名字/外观/语气）
验证：在 NEKO 里输入 → 陆墨回答 → NEKO 显示文字
```

### M2：语音打通

```
目标：NEKO 能说话也能听
动作：
1. NEKO ASR（已有 omni_realtime_client）→ 语音输入
2. NEKO TTS（已有 CosyVoice 免费阶跃版）→ 陆墨回复转语音
3. 嘴型同步（已有 Live2D 参数映射）
验证：对 NEKO 说话 → 陆墨语音回答 → 嘴型同步
```

### M3：双向事件

```
目标：scratchpad 能主动让 NEKO 说话/换表情
动作：
1. scratchpad 端新增 event_bridge.py（WebSocket → NEKO ws_router）
2. NEKO emotion 表情切换指令接收
3. scratchpad 判断"该说话了"→ push → NEKO 主动搭话
验证：陆墨 RAG 触发新发现 → NEKO 主动说"你的实验数据有异常"
```

### M4：Agent 执行

```
目标：NEKO 的手（CUA/OpenClaw）归陆墨指挥
动作：
1. Agent 指令源切到 scratchpad（不要 NEKO brain 自决策）
2. scratchpad agentic_tool_loop → NEKO task_executor
验证：用户说"帮我查这篇论文的引用" → 陆墨决策 → NEKO 执行浏览器操作
```

### M5：记忆融合（大版本）

```
目标：统一记忆体系
动作：按第二章"后续融合路线"四步走
前置：M1-M4 全部稳定 + scratchpad 记忆体系成熟
```

---

## 六、部署拓扑

```
天选7pro (Windows · 非24h)
├── NEKO 三服务器 (Main/Memory/Agent)
│   ├── Live2D · TTS · ASR · CUA
│   └── api_providers.json → localhost scratchpad
├── scratchpad 后端 (FastAPI)
│   ├── 陆墨 persona · RAG · session
│   └── openai_proxy :8000
└── Trae IDE

韩国云服 (24h)
├── 沈遥 + 陆墨 QQ Bot (lumo profile)
└── 数据归档 · backup

Kali 冥王峡谷 (24h 无头)
├── 林楠 (代码执行)
└── ML 长任务兜底
```

**关键规则**：
- 笔记本关机 = 形象离线，大脑仍在（云服陆墨 + Kali 林楠）
- 天选7pro 开机 = 形象+大脑全在线，走 localhost 零延迟
- Kohberger / 陆墨 QQ Bot = 云服独立运行，不依赖 NEKO

---

## 七、不可违反的铁律

1. **人格唯一**：陆墨 persona 只能由 scratchpad 的 persona API 定义，NEKO 角色卡只做表层（名字/模型/音量等 UI 配置）
2. **记忆唯一**：所有对话/事实/反思记忆写入 scratchpad，NEKO 记忆系统不启动
3. **不修改 NEKO 源码**：合入 scratchpad 后保留原始 LICENSE + NOTICE + `.upstream-sha`，所有耦合逻辑写在 scratchpad 侧
4. **安全前置**：CUA 沙箱不收紧之前，NEKO 不得接陆墨 Agent 功能
5. **降级优先**：任何一个 NEKO 服务挂了，scratchpad 应能独立运行（文字对话），不形成单点依赖
6. **留下回去的路**：NEKO 上游更新时只需更新 vendor 目录，耦合层不变

---

*本说明书由沈遥审定，铁锚/杜赞并行审查（待补充）*
