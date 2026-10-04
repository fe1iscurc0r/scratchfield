# NEKO × 陆墨 融合大版本指导说明书 v1.1

> **目标**：构建星野遥未来四年的数字科研外骨骼——一个有形象、有声音、有记忆、有知识的 AI 搭档，**全部本地运行**。
> **核心原则**：**单一灵魂**——陆墨是唯一的人格与记忆源，NEKO 是身体/感官/发声器官。
> **v1.1 修订**：按多智能体讨论纪要（docs/NEKO-Lumo-Fusion-Discussion-Minutes.md）修正 5 处硬伤 + 9 处勘误 + 7 项决策点全部拍板。用户裁决：D6 全部本地，不用云服。

---

## 〇、什么是最终目标

```
你的科研外骨骼 = 大脑 + 身体 + 神经系统（全部在天选7pro 本地）

大脑（scratchpad/陆墨）：人格、记忆、知识、科研决策
身体（NEKO）：Live2D 形象、TTS 语音、ASR 耳朵、CUA 手、屏幕感知眼
神经系统（实验田维护者+执行侧）：协议、接口、部署、安全、出故障兜底
```

**部署形态：单机单实例**。全部跑在天选7pro（Windows），关机 = 离线（数据不丢，记忆持久化在本地），开机 = 全在线。不做云服同步、不做多实例。

---

## 一、核心架构：单一灵魂（v1.1 修正）

### NEKO 现状（只读为主，一处豁免修改）

NEKO 是成熟的"AI 伴侣"OS，三服务器进程隔离：

| 服务 | 端口 | 职责 | 本次处理 |
|------|------|------|----------|
| Main Server | 48911 | Web UI / REST / WebSocket / 会话 / TTS | 用 |
| Memory Server | 48912 | 五维记忆 | **不启动**（单一记忆源） |
| Agent Server | 48915 | 任务评估 / 通道分发 | 用（M4 后） |
| Monitor Server | 48913 | 镜像流 | **确认绑定 127.0.0.1**（否则对话泄露） |
| ZMQ Bridge | 48961-48963 | Main↔Agent 事件总线 | 用 |

**注意**：`config/network.py` 未硬编码 48915，Agent 端口实际值以运行日志为准（勘误 E7）。

### 单一灵魂原则（v1.1 细化）

```
NEKO (身体)                          scratchpad/陆墨 (灵魂)
┌──────────────────────┐       ┌──────────────────────┐
│ ASR · 摄像头 (五官)   │       │                      │
│ TTS CosyVoice (嘴)   │  REST │ 人设 (persona API)    │
│ CUA/OpenClaw (手)    │◄─────►│ 记忆 (唯一副本)        │
│ emotion_model 表情   │       │ 知识 (RAG 科研库)      │
│ vision_model 视觉    │       │ 决策 (chat + agent)   │
│                      │       │                      │
│ NEKO记忆 = 关闭      │       │ persona-aware 端点    │
│ NEKO决策 = 关闭      │       │ /v1/chat/completions  │
└──────────────────────┘       └──────────────────────┘
```

**v1.1 细化分工（采纳杜赞方案 + 实验田维护者边界裁决）：**

| 能力 | 归属 | 说明 |
|------|------|------|
| 对话生成 | **陆墨** | conversation_model 归陆墨 |
| 人格/记忆/RAG | **陆墨** | 唯一事实源 |
| Agent 决策 | **陆墨** | agent 指令源在 scratchpad |
| **emotion 表情** | **NEKO 本地** | emotion_model 本地小模型出"情绪标签"（表情用）→ **回传陆墨存储** |
| vision 视觉 | **NEKO** | 身体感知 |
| summary/correction | **NEKO** | 内部管线优化 |
| 主动搭话时机 | **陆墨** | 是否说话/说什么由陆墨决策 |

**关键边界（实验田维护者补充）**：emotion 是"表情"不是"情绪决策"。NEKO 本地小模型出情绪标签 = 脸部表情；但"要不要主动搭话、搭话说什么"的决策必须回陆墨。否则 NEKO 自己"想"说话，违背单一决策源。

---

## 二、五维记忆：当前关闭，备选留档（v1.1 修正关闭方式）

NEKO 五维记忆全部暂不启用。**关闭方式 = 不启动 memory_server 进程**（memory_settings.py 是参数配置，没有总开关——勘误 E3）。

| 层 | 职责 | 当前决策 |
|----|------|----------|
| 工作/事实/反思/人格/向量 | NEKO 五维 | **关**（不启动 48912 进程） |

### 为什么先关

1. **单一事实源**：陆墨已有完整记忆管线（session/rag/persona），两套记忆同时跑 = 事实歧义
2. **融合是大工程**：两种范式，不是"开关"是架构重设计
3. **关 ≠ 删**：NEKO `app/memory_server/` 源码完整保留，M5 阶段反哺

### 后续融合路线（M5 大版本，本地化后简化）

```
M5 目标：统一记忆体系，单机本地
Phase 1 (当前): 陆墨 session ↔ NEKO 对话请求响应
Phase 2: 陆墨记忆分层（近期/事实/人格）
Phase 3: 可选引入 NEKO 反思层思路（LLM 聚类合并）到陆墨
Phase 4: 统一记忆存储（SQLite/文件，本地持久化）
```

**铁律：单一引擎。** M5 只做"把 NEKO 的好设计反哺进陆墨"，不做双记忆并行。

---

## 三、同步策略：NEKO 上游更新（v1.1 新增 overlay）

### 当前引入方式

NEKO 源码 vendor 在 `scratchpad/NEKO/N.E.K.O/`（Apache 2.0 + NOTICE + 独立 LICENSE）。

### 同步规则

| 方式 | 适用场景 | 操作 |
|------|---------|------|
| **`.upstream-sha`** | 当前（需创建，勘误 E8） | 记录当前 vendor 的 NEKO 上游 commit |
| **Git Submodule** | 未来（如需频繁同步） | `git submodule add` |

### v1.1 铁律 8：配置 overlay（防上游冲掉）

NEKO 侧配置变更**不直接改 NEKO 文件**，通过 scratchpad 侧 overlay 注入：
- `api_providers.json` 加 lumo provider → 用 overlay 文件/启动参数注入
- 上游更新 vendor 时，overlay 重新应用，配置不丢

---

## 四、安全前置条件（v1.1 修正，启用前必须完成）

1. **CUA exec 沙箱收紧**：`brain/computer_use.py:1182-1191`（勘误 E1：不是 engine.py）
   ```python
   exec_env: dict = {"__builtins__": __builtins__}  # 全量暴露 ← 必须收紧
   exec_env["os"] = os                               # os.system 可达 ← 必须收紧
   exec(code, exec_env)                              # RCE 直通车
   ```
   **铁律 3 豁免（决策 D4）**：此修改属"安全前置豁免"，允许改 NEKO 源码，只改这一处，改完在 `.upstream-sha` 标注 local-patch。
2. **monitor_server (48913) 确认绑定 `127.0.0.1`**（勘误 E9，漏了它）
3. **Memory/Agent 端口确认绑定 `127.0.0.1`**，不暴露 `0.0.0.0`
4. **cross_server bullet 通道**：pickle + 关 SSL 验证 → 本地单机无 MITM 风险，但 M4 后若对外开放必须重写
5. **插件隔离**：`plugin/core/host.py` 的 `sys.path.insert(0)` 污染 → 监控，本地可控

---

## 五、鉴权链路（v1.1 新增，决策 D5）

scratchpad 的 openai_proxy / persona / chat 全带 `require_local_auth`。NEKO 跨进程调用必须鉴权：

- **机制**：环境变量共享密钥 `LUMO_PROXY_TOKEN`
- scratchpad persona-aware 端点校验 `Authorization: Bearer $LUMO_PROXY_TOKEN`
- NEKO 启动时从同机环境读取，不落盘明文
- **铁律 7（鉴权边界）**：所有跨进程接口必须校验 token

---

## 六、分阶段实施路线图（v1.1 修正）

### M1：文本打通（修正：新建人格端点 + 鉴权）

```
目标：NEKO 说话，脑子是陆墨
动作：
1. scratchpad 新建 persona-aware OpenAI 兼容端点 /v1/chat/completions
   （包装 build_system_prompt + RAG + session，约 150 行——决策 D2 方案 A）
2. NEKO api_providers.json 新增 lumo provider → 指向该端点（overlay 注入，铁律 8）
3. 不启动 NEKO memory_server 进程（勘误 E3）
4. NEKO 表层角色卡（名字/外观/语气）
5. 定义 LUMO_PROXY_TOKEN（铁律 7）
验证：在 NEKO 输入 → 陆墨人格 + RAG 回复 → NEKO 显示
```

### M2：语音打通（前置：emotion 归属已拍板）

```
目标：NEKO 能说话也能听
动作：
1. NEKO ASR（omni_realtime_client）→ 语音输入
2. NEKO TTS（DashScope CosyVoice——勘误 E5，不是阶跃 StepFun）→ 回复转语音
3. 嘴型同步：前端 RMS 驱动 setMouth（勘误 E6）
4. emotion：NEKO 本地 emotion_model 出标签 → 回传陆墨存储（决策 D1 方案 B）
验证：对 NEKO 说话 → 陆墨语音回答 → 嘴型同步 + 表情
```

### M3：双向事件（修正：改 REST，决策 D3）

```
目标：scratchpad 能主动让 NEKO 说话/换表情
动作：
1. 放弃 WebSocket（NEKO ws_router 是前端协议，无外部注入接口——共识 3）
2. 改 REST：scratchpad → NEKO main_server 已有 REST 路由，POST 触发表情/搭话
3. 拆分 M3a(单向推送) / M3b(双向搭话)
验证：陆墨 RAG 触发新发现 → NEKO 主动说"你的实验数据有异常"
```

### M4：Agent 执行（前置：CUA 沙箱已收紧）

```
目标：NEKO 的手归陆墨指挥
动作：
1. 先修 computer_use.py 沙箱（安全前置 1，铁律 3 豁免）
2. scratchpad agent 决策 → NEKO task_executor（HTTP 桥接，加 neko_cua 分支）
3. Agent 指令源 = 陆墨，NEKO brain 不自决策
验证：用户说"帮我查这篇论文" → 陆墨决策 → NEKO 操作浏览器
```

### M5：记忆融合（大版本，单机本地化）

```
目标：统一记忆体系
动作：按第二章融合路线四步走
前置：M1-M4 稳定 + 陆墨记忆体系成熟（"成熟"定义：session 记忆 + RAG + 分层，验证标准在 M5 启动时另写）
```

---

## 七、部署拓扑（v1.1 修正：全部本地）

```
天选7pro (Windows · 唯一节点)
├── NEKO 三服务器 (Main 48911 / Memory 48912=不启动 / Agent 48915)
│   ├── Live2D · TTS(CosyVoice) · ASR · CUA(沙箱已收紧)
│   └── api_providers.json(lumo provider, overlay 注入) → localhost
├── scratchpad 后端 (FastAPI)
│   ├── 陆墨 persona · RAG · session · 记忆(本地持久化)
│   ├── persona-aware /v1/chat/completions :8000
│   └── LUMO_PROXY_TOKEN 鉴权
└── Trae IDE

关机 = 离线（记忆不丢，本地持久化）
开机 = 全在线，localhost 零延迟
```

**不做**：云服同步、多实例、远程访问（用户裁决 D6：全部本地）。

---

## 八、不可违反的铁律（v1.1：6 + 2 = 8 条）

1. **人格唯一**：陆墨 persona 只能由 scratchpad 的 persona API 定义
2. **记忆唯一**：所有记忆写入 scratchpad（本地持久化），NEKO 记忆进程不启动
3. **不修改 NEKO 源码**（**安全前置豁免除外**——CUA 沙箱是唯一允许的 local-patch，改完在 `.upstream-sha` 标注）
4. **安全前置**：CUA 沙箱不收紧之前，NEKO 不得接陆墨 Agent 功能
5. **降级优先**：NEKO 任何一个服务挂了，scratchpad 应能独立运行文字对话
6. **留下回去的路**：NEKO 上游更新只换 vendor 目录 + 重放 overlay，耦合层不变
7. **鉴权边界**：跨进程调用必须校验 `LUMO_PROXY_TOKEN`
8. **配置 overlay**：NEKO 侧配置变更不直接改文件，scratchpad 侧 overlay 注入

---

## 九、勘误对照表（v1.0 → v1.1）

| # | v1.0 原文 | 实际 | 修正 |
|---|---|------|------|
| E1 | `brain/cua/core/engine.py` 沙箱 | `brain/computer_use.py:1182-1191` | ✅ 已改 |
| E2 | openai_proxy 实现"陆墨回答" | 透传，不注入人格 | ✅ 新建 persona-aware 端点 |
| E3 | memory_settings 关记忆 | 无总开关 | ✅ 不启动 memory_server |
| E4 | 8 家文本 + 6 家 Realtime | 19 家文本 + 8 家 Realtime | ✅ 勘误 |
| E5 | CosyVoice 免费阶跃版 | CosyVoice(DashScope) ≠ StepFun | ✅ 勘误 |
| E6 | 嘴型同步"参数映射" | 前端 RMS 驱动 setMouth | ✅ 勘误 |
| E7 | Agent 端口 48915 | config/network.py 未定义 | ✅ 以运行日志为准 |
| E8 | `.upstream-sha` 已存在 | 不存在 | ✅ 需创建 |
| E9 | 只查 Memory/Agent 端口 | monitor_server 48913 0.0.0.0 | ✅ 已补 |

---

## 十、决策点裁决表（7 项已全部拍板）

| # | 决策点 | 裁决 | 拍板人 |
|---|--------|------|--------|
| D1 | emotion 归属 | **B** NEKO 出 + 回传陆墨存储 | 用户（小模型可行）+ 纪要建议 |
| D2 | M1 人格端点 | **A** 新建 `/v1/chat/completions` | 纪要建议 |
| D3 | M3 通信方式 | **B** REST | 纪要建议 |
| D4 | CUA 沙箱收紧 | **A** 改 NEKO 源码（豁免铁律 3） | 纪要建议 |
| D5 | 鉴权机制 | **A** 环境变量共享密钥 | 纪要建议 |
| D6 | 记忆一致性 | **全部本地，不用云服**（单机单实例） | **用户** |
| D7 | api_providers.json | **B** scratchpad 侧 overlay 注入 | 纪要建议 |

---

*v1.1 由实验田维护者修订，采纳多智能体讨论纪要（铁锚/杜赞/Hermes 审查），用户拍板 D1/D6。*
