# block/buzz × herdrdev/herdr — 消息协议 × 运行时执行模型 授粉报告

> 工单：D-04 | 许可：Apache-2.0 × 2 | 仓库：block/buzz / herdrdev/herdr
> 报告日期：2026-08-23 | 调研人：沈遥 · 三元融合系统（Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互）语境
> 调研方式：git clone --depth 1 源码 + 官方文档（含 herdr 简体中文文档）阅读，纯调研只读，未写业务代码

---

## 一、仓库画像与许可风险

### 1.1 block/buzz — agent 间消息协议（事件日志即消息总线）

**许可：Apache License 2.0**（README 头标 + LICENSE 文件确认，宽松许可、可商用可修改，无传染性）。

Buzz 是 Block（Square）开源的**自托管协作工作区**，其本质是一个 **Nostr relay（NIP-29 中继）**：人类与 AI agent 在同一"房间"（channel）里共事，而**每一条消息、反应、工作流步骤、评审批准、git 事件，都是同一条签名事件日志中的一条 Nostr 事件**。关键定位：

- **消息协议即身份模型**：人和进程用同一套密钥签名、同一套事件形状、同一条审计轨迹。Agent 不是"机器人账号"，而是**拥有自己密钥、自己频道成员资格、自己审计轨迹的成员**——按身份授权（identity-scoped），而不是按权限标志位（permission flags）授权。
- **协议面**：WebSocket 上原生讲 NIP-29（群组消息 kind:9 + `#h` 频道标签）+ NIP-42 认证；thread（NIP-10 `#e` 标签）、DM（NIP-17 kind:1059 密文）、git 事件（NIP-34：patch/PR/issue/status）、agent 专属 kind（engram 加密记忆、turn metric 令牌计量、私有托管 agent 聚合）。
- **Agent 工程面**：`buzz-agent`（ACP 协议 agent，单进程最多 8 个并发会话，每会话独立 MCP 服务）+ `buzz-dev-mcp`（shell/文件编辑 MCP 服务）+ `buzz-cli`（JSON in/JSON out，为 LLM 工具调用设计）+ `buzz-workflow`（YAML 事件驱动工作流：message/reaction/schedule/webhook 触发器）。
- **审计**：`buzz-audit` 哈希链审计日志，所有事件可追溯。

**一句话画像**：Buzz = 「Nostr 事件日志上的多智能体协作总线」，把聊天、工作流、git、记忆、计量全部压成一种可签名、可搜索、可审计的事件消息协议。

### 1.2 herdrdev/herdr — 运行时执行模型（终端里的 agent 多路复用器）

**许可：Apache License 2.0**（README 徽章 + LICENSE 文件确认，与 buzz 同款宽松许可）。

herdr 是**住在终端里的编程 agent 运行时**（"智能体复用器"）：单个 Rust 二进制，无 Electron，把真实的终端进程持续运行，并在其上叠加结构。关键定位：

- **服务器/客户端分离**：后台 herdr 服务器**拥有**窗格与进程状态；TUI 只是连接上去的客户端。`ctrl+b q` 分离客户端后，**服务器和 agent 继续运行**，可从任意终端或 ssh 重新连接，会话在重启后依然保留。
- **Agent 生命周期状态机**：`blocked`（需要输入/审批/决策）、`working`（运行中）、`done`（完成未查看）、`idle`（完成且已查看）、`unknown`。状态由**前台进程 + 屏幕清单（evidence-based AND/OR 门） + 官方集成**三层证据检测，不是包装过的转述。
- **分层容器**：Workspace（项目容器）→ Tab（布局）→ Pane（真实终端）；命名 Session 是互相独立的持久化服务器命名空间。
- **Socket API 即编排面**：纯点号方法（`pane.split`、`pane.read`、`agent.wait`、`agent.prompt`、`events.subscribe`），agent 可以通过它创建窗格、读输出、**互相等待**；`skills/herdr/SKILL.md` 教 agent 在 `HERDR_ENV=1` 时用 CLI 控制 herdr。
- **多级持久化**：实时持久化（detach/reconnect，进程不死）> 快照恢复（布局）> 窗格屏幕历史回放 > **agent 原生会话恢复**（`claude --resume <id>`、`codex resume <id>`、**`hermes --resume <id>`**…）> 实时交接 `--handoff`（服务器替换时转移活窗格，实验性）。
- **架构纪律**（AGENTS.md 明文）：State 与 Runtime 分离（AppState 纯数据、PaneState ≠ PaneRuntime）、渲染纯函数、服务端拥有运行时协议而 TUI 只是其中一个客户端。

**一句话画像**：herdr = 「以终端窗格为执行单元、以状态机为生命周期、以 socket API 为编排面的 agent 运行时执行模型」。

### 1.3 许可风险小结

| 项 | block/buzz | herdrdev/herdr |
|---|---|---|
| 许可 | Apache-2.0 | Apache-2.0 |
| 传染性 | 无（宽松） | 无（宽松） |
| 引用方式 | 提炼事件协议与 kind 语义设计 | 提炼状态机与 socket 编排模式 |
| 风险点 | Rust 单体大仓（213+ 顶层文件），不宜直接合入 | 深绑 PTY/终端渲染，移植面窄，只取模式 |

---

## 二、消息协议字段表（buzz 消息关键字段/语义）

buzz 的消息就是一条 **Nostr 事件**：统一形状（字段固定）+ 统一验签（`sig`）+ 统一检索（按 kind/tags 过滤）。核心字段如下：

| # | 字段 | 类型/示例 | 语义 |
|---|------|-----------|------|
| 1 | `id` | 64-hex（sha256 事件序列化） | 事件哈希，全局唯一，是消息的寻址/引用锚点（`#e` 引用它） |
| 2 | `pubkey` | 64-hex 公钥 | 作者身份——人/agent 同一套密钥模型；权限按身份作用域而非标志位 |
| 3 | `created_at` | Unix 时间戳 | 事件时序；配合服务端 `received_at` 构成审计时间轴 |
| 4 | `kind` | u32 注册表编号 | 事件类型：9 群聊、7 反应、5 删除、1059 DM、1617-1633 git、10100 agent profile、30174 engram 记忆、30179 私有托管 agent、44200 agent turn 计量、39000-39002 relay 签名组元数据 |
| 5 | `content` | 明文或 NIP-44 v2 密文 | 消息正文；DM/记忆/计量等敏感载荷一律加密（agent→owner 定向解密） |
| 6 | `tags` | 数组 `["h","<channel-uuid>"]` 等 | 路由与语义标签：`#h` 频道归属、`#e` 线程根/回复（NIP-10）、`#p` 提及/收件人、`#d` 可替换事件地址、`#name` 组元数据 |
| 7 | `sig` | Schnorr 签名 | 验签通过才入库 → 防伪造、防篡改，审计链的密码学底座 |
| 8 | `channel_id` | UUID（服务端派生，StoredEvent 字段） | 事件所属频道；reaction/deletion 的频道由目标事件 `#e` 推导，客户端 `#h` 被忽略 |
| 9 | `received_at` | DateTime<Utc>（StoredEvent 字段） | 中继接收时间，与作者 `created_at` 分离，供审计/排序 |
| 10 | `d_tag`（engram 专用） | `HMAC(agent↔owner 会话密钥, slug)` | NIP-AE 加密记忆寻址键：按 `(pubkey, kind, d_tag)` 定位，`d-tag` 域前缀带版本号；记忆只对 agent 与其 owner 可见 |
| 11 | `not_before`（提醒专用） | 时间标签 | NIP-ER 事件提醒的到期门；目标/备注/状态 NIP-44 加密仅作者可读 |
| 12 | 元数据签名方 | relay-signed | 39000/39001/39002（组元数据/管理员/成员）由**中继签名**，成员关系不可被参与者伪造 |

**设计要点**：① 所有事件同形状 → 聊天/补丁/CI/审批/工作流全进同一个搜索索引（一个社区、一种身份模型、一条事件日志）；② 加密与签名分离——`sig` 保证"谁说的"，NIP-44 密文保证"谁能看"；③ agent 专属 kind 让"记忆（engram）、计量（turn metric）、托管配置（PMA）"都变成可审计的事件流，而非旁路数据库。

---

## 三、运行时生命周期图（herdr 如何调度/执行 agent 任务）

herdr 的执行模型：**服务器拥有进程，客户端只做视图；任务 = 窗格里的 agent 进程；调度 = socket API 的创建/等待/读取**。生命周期分三段：容器装配 → agent 生命周期状态机 → 跨 agent 协作与持久化。

```text
┌────────────────────────── herdr 服务器（后台，拥有一切状态） ──────────────────────────┐
│                                                                                        │
│  启动:  herdr            →  会话(命名空间)  →  workspace(项目)  →  tab(布局)  →  pane    │
│                                                                                        │
│  pane = 真实终端进程；agent = pane 内被识别出的进程（前台进程 / 屏幕清单 / 官方集成）      │
│                                                                                        │
│  ┌───────────── agent 生命周期状态机 ─────────────┐                                     │
│  │                                                │                                     │
│  │        ┌──────────┐    检测到运行     ┌────────┐│                                     │
│  │        │  spawned │ ───────────────► │ working ││                                     │
│  │        └──────────┘                   └───┬────┘│                                     │
│  │                                           │     │                                     │
│  │                    需要输入/审批/决策      │     │ 完成且未查看                        │
│  │                    ┌──────────────────────┘     ▼                                    │
│  │                    ▼                          ┌────┐                                 │
│  │              ┌──────────┐                    │done│                                 │
│  │              │ blocked  │                    └─┬──┘                                 │
│  │              └────┬─────┘                      │ 已被查看                            │
│  │                   │ agent.prompt 注入输入      ▼                                     │
│  │                   └──────────────────────►  idle ──────► (可再次工作)                │
│  │              （agent.prompt 带 wait{until,timeout_ms}，                              │
│  │                若已 blocked 直接返回 agent_blocked 避免竞态）                          │
│  └────────────────────────────────────────────────┘                                     │
│                                                                                        │
│  编排面:  socket API（agent 也可调用）                                                   │
│    agent A:  pane.split → pane.run "npx test"   ──►  pane B（并行）                     │
│    agent A:  agent.wait B --until done          ──►  服务器事件驱动，固定到占用者       │
│    agent A:  pane.read B --lines 50             ──►  读取输出（证据而非转述）           │
│    agent A:  agent.prompt C {until: blocked}    ──►  阻塞等待 C 决策，超时可控           │
│    events.subscribe / events.wait               ──►  长轮询事件流                       │
│                                                                                        │
│  客户端:  ctrl+b q 分离 ──► 服务器与 agent 继续运行 ──► 任意终端 herdr 重新连接          │
│                                                                                        │
│  恢复分级（服务器重启后）:                                                               │
│    快照恢复(布局) → 屏幕历史回放(可选) → agent 原生会话恢复(claude --resume /            │
│    hermes --resume …) → 实时交接 --handoff(活窗格跨服务器迁移, 实验性)                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**调度要点**：
- **不抢焦点的并行**：`pane split` + `pane run` 在相邻窗格启动辅助进程，主 agent 不必等它完成即可继续；`agent.wait --until done` 把"等待"变成服务器侧事件驱动的原语，替换后的进程不能冒充满足等待。
- **证据而非转述**：状态由屏幕检测（AND/OR 门匹配不变式控件）推导，读取用 `pane.read --source detection/recent`，不是 agent 自报。
- **进程永生 + 状态重建分层**：detach 不杀进程（最强）；服务器重启则按"布局 → 历史 → 原生会话引用 → 活交接"逐级降档恢复——每个 agent 的恢复能力取决于其集成是否上报了会话引用（如 `hermes --resume <id>`）。

---

## 四、对照 NagaAgent 的落地建议（三元融合：Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互）

> NagaAgent 定位为本地 agent 执行服务（API/MCP 桥接），对应 herdr 的"执行层"；Hermes 对应 herdr 的"编排客户端 + 决策者"；N.E.K.O. 对应 buzz 的"记忆/交互"。

### 建议 1：给 NagaAgent 引入 buzz 式"事件即消息"协议——执行结果以签名事件回传，而非裸文本

**原理**：buzz 把聊天/工作流/git/计量全部压成一种 Nostr 事件（`id/pubkey/kind/tags/content/sig`），一个社区一条事件日志一个搜索索引；`agent_turn_metric`（kind:44200）证明"计量也是事件"。

**落地**：NagaAgent 每次任务完成，向 Hermes 回传结构化事件（字段：`task_id`（≈`#e` 引用）、`kind`（exec_done / exec_blocked / exec_metric）、`status`、`output_ref`、`sig`），Hermes 决策层消费同一事件流；审计链（哈希链）沿用 buzz-audit 思路，把"谁在什么时候执行了什么"变成不可篡改的日志。

**结论**：**参考**——协议形状直接借鉴，事件字段需按三元融合重定义，不复制 buzz 代码。

### 建议 2：把 herdr 的五态状态机 + `wait/prompt(until, timeout)` 原语引入 NagaAgent 任务 API

**原理**：herdr 的 `blocked/working/done/idle/unknown` 五态 + `agent.wait`（事件驱动、固定占用者）+ `agent.prompt {until, timeout_ms}`（单请求提交+等待、避免竞态、已阻塞时返回 `agent_blocked`）是"执行层对外暴露进度与阻塞"的成熟模型。

**落地**：
- NagaAgent 任务对象增加五态（尤其 `blocked`——需要 Hermes 决策或人工审批时显式挂起）；
- Hermes 侧提供 `naga.wait <task> --until done` 与 `naga.prompt <task> --until blocked --timeout 30s` 两个原语，超时未决由 Hermes 走决策门（与 D-01 Orca Decision Gate 呼应）；
- 状态必须来自执行层事实（进程/检测），而非 agent 自报——对应 herdr 的"证据而非转述"。

**结论**：**直接可用**——纯状态机 + 两个原语，可立即在 NagaAgent 任务模型落地。

### 建议 3：NagaAgent 任务持久化采用 herdr 分级恢复——"进程不死 > 快照 > 会话引用恢复"

**原理**：herdr 恢复分级：detach 不杀进程（最强）→ 快照恢复布局 → agent 原生会话恢复（`--resume <id>`）→ 实时交接。且 herdr 官方集成表里**直接支持 Hermes Agent**（`hermes --resume <id>`）。

**落地**：NagaAgent 每任务持久化 `(task_id, cwd, status, agent 会话引用)`；Hermes/NagaAgent 重启后按级恢复：①后台进程仍在→直接重连；②仅布局/清单→按 cwd 重启任务；③集成上报了会话引用→`hermes --resume <id>` / `codex resume <id>` 恢复对话；④实验性的活交接留作后续。同时遵循 herdr 架构纪律：**State 与 Runtime 分离**（任务清单是纯数据可序列化，运行时对象可重建）。

**结论**：**参考**——分级恢复表可直接映射，`--resume` 链路的集成方式照搬 herdr 与各家 CLI 的对接模式。

### 建议 4：N.E.K.O. 记忆层借鉴 NIP-AE engram——记忆带身份绑定与可寻址键

**原理**：buzz engram（kind:30174）按 `(pubkey, kind, d_tag)` 寻址，`d_tag = HMAC(agent↔owner 会话密钥, slug)`，内容 NIP-44 加密——记忆是"agent 与其 owner 之间"的定向资产，且作为事件进审计日志。

**落地**：N.E.K.O. 记忆条目增加 `(owner_key, memory_key)` 绑定与加密（至少对敏感记忆），记忆读写走"事件"通道进入审计流；slug 域前缀带版本号（`agent-memory/v1/d-tag`）的做法可直接借鉴，避免寻址键跨版本失效。

**结论**：**参考**——加密寻址机制可取，具体密钥体系按 N.E.K.O. 现有存储改造。

### 建议汇总

| # | 建议 | 来源 | 结论 |
|---|------|------|------|
| 1 | NagaAgent 执行结果事件化（签名事件 + 审计链） | buzz | 参考 |
| 2 | 五态状态机 + `wait/prompt(until,timeout)` 原语 | herdr | **直接可用** |
| 3 | 任务持久化分级恢复 + State/Runtime 分离 | herdr | 参考 |
| 4 | N.E.K.O. 记忆 engram 化（身份绑定 + 可寻址键） | buzz | 参考 |

**综合评级**：**参考**。buzz 证明"消息协议统一一切（聊天=git=工作流=记忆=计量）"，herdr 证明"执行层要暴露真实状态、允许证据读取、支持进程级持久化"。两者都是 Apache-2.0，但 buzz 是 Rust 大仓、herdr 深绑 PTY，均**不建议合入代码**；建议 2 形态最小、可直接落地，其余三条抽取设计后新写实现。

---

## 五、授粉纪律声明

1. **只提炼思路与机制，不复制代码**：本报告所有结论均来自对两仓库 README/官方文档/核心模块（buzz `kind.rs`、`event.rs`、`engram.rs`；herdr `concepts/session-state/socket-api` 文档与 AGENTS.md）的阅读提炼，未将任何源码片段整段复制进本报告，也未合入任何业务代码。
2. **设计可移植、代码不搬运**：Apache-2.0 允许复制修改，但授粉纪律要求——涉及的具体实现（事件结构、状态机、socket 方法）一律按三元融合语境**重新设计**，仅保留协议形状、状态语义、恢复分级等机制层面的借鉴。
3. **标注来源与边界**：涉及 buzz/herdr 的具体事实均可在克隆仓库中溯源（见下方源码索引）；"直接可用/参考"分级只代表机制可借鉴度，不代表许可或耦合度的豁免。
4. **后续落地须评审**：任何把上述建议落为代码的工单，需在实现前单独评审，确认无 buzz/herdr 代码被逐字带入。

---

## 六、关键源码索引

| 仓库 | 路径 | 关键内容 |
|------|------|---------|
| buzz | `NOSTR.md` | NIP-29 直连支持矩阵（kind 9/7/5/1059/9000-9022/39000-39002/20001/20002…） |
| buzz | `crates/buzz-core/src/kind.rs` | 完整 kind 注册表（agent 10100/30174/30179，git 1617-1633，turn 44200） |
| buzz | `crates/buzz-core/src/event.rs` | StoredEvent（event + channel_id + received_at） |
| buzz | `crates/buzz-core/src/engram.rs` | NIP-AE 记忆寻址（d-tag HMAC、NIP-44 加密、CORE_SLUG） |
| buzz | `crates/buzz-core/src/agent_turn_metric.rs` | NIP-AM turn 计量（token/cost 可空语义） |
| buzz | `crates/buzz-workflow/src/schema.rs` | 事件触发工作流（trigger/step/reply_in_thread） |
| buzz | `VISION_AGENT.md` | ACP agent + MCP 工具面、并发会话隔离 |
| herdr | `docs/next/website/src/content/docs/zh-cn/concepts.mdx` | 五态状态机、workspace/tab/pane/session 层级 |
| herdr | `docs/next/website/src/content/docs/zh-cn/session-state.mdx` | 五级持久化恢复 + 各 agent `--resume` 对照表 |
| herdr | `docs/next/website/src/content/docs/zh-cn/socket-api.mdx` | 全部 socket 方法（workspace/tab/pane/agent/events） |
| herdr | `docs/next/website/src/content/docs/zh-cn/agent-skill.mdx` | HERDR_ENV=1 技能护栏 |
| herdr | `AGENTS.md` | State/Runtime 分离、服务端拥有运行时协议 |

---

*—— 沈遥 · buzz 是"万物皆事件"，herdr 是"进程即任务"；一个定义消息协议，一个定义执行模型，两者合起来正是三元融合缺的那两块拼图 🐝🐑*

---

> **【附录：另一会话同题报告原文】** 以下为同名授粉报告的另一版本（2026-08-23 并行会话产出），与上文互为补充，合并时保留以防资料丢失。

# buzz 蜂群消息 + herdr 运行时 · 授粉报告（D-04）

> 智能体 D · 2026-08-23 · 只读调研，未写一行业务码
> A = [block/buzz](https://github.com/block/buzz)（Apache-2.0，Block/Square 官方，
> Nostr 协议自托管协作空间，Rust 30+ crates + Postgres + Redis + MinIO）
> B = [herdrdev/herdr](https://github.com/herdrdev/herdr)（Apache-2.0，单 Rust
> 二进制，"the runtime your coding agents live on"——PTY 终端运行时）
> 对照对象：NagaAgent（本仓主干：apiserver:8000 + agentserver:8001 军牌调度 +
> Electron 前端）。调研方式：浅克隆仓外临时目录通读；行号相对各仓库根。
> 事实先行：**两仓库互不引用**（grep 交叉零命中），herdr 是终端进程层运行时，
> buzz 是消息/事件日志层协作空间，本报告分述后给 NagaAgent 对照建议。

---

## 一、buzz 消息协议（频道/线程/同步语义）

### 1.1 事件信封（Nostr NIP-01 六字段）

| 字段 | 类型 | 语义 | 备注 |
| --- | --- | --- | --- |
| `id` | 32B hex | 事件指纹 | 内容哈希，去重键（DB `ON CONFLICT DO NOTHING` 幂等） |
| `pubkey` | 32B hex | **发送者身份=公钥** | "密钥对即身份——无 token 无其他鉴权"（`crates/buzz-cli/src/lib.rs:2010-2016`） |
| `kind` | u16 | **唯一分发开关** | 注册表 127 种（`crates/buzz-core/src/kind.rs`）；新功能=新 kind 号=旧客户端零破坏 |
| `tags` | array | 路由/线程/引用元数据 | `["e",<id>,<relay>,"root"\|"reply"]`（NIP-10）；`["h",<channel-uuid>]` 频道作用域；`#p` 提及门控 |
| `content` | string ≤64KB | 业务载荷 | patch 则为 diff 正文；DM 则 NIP-44 加密 |
| `sig` | 64B | Schnorr 签名 | 入站 12 步管线第 6 步 `spawn_blocking` 验签（`ARCHITECTURE.md` §4） |

### 1.2 核心 kind 号（节选自 `buzz-core/src/kind.rs`，范围约定：0-9999 标准 /
10000-19999 replaceable / 20000-29999 ephemeral / 30000-39999 参数化 /
**40000-49999 Buzz 自定义**）

| 类别 | kind | 用途 |
| --- | --- | --- |
| 消息 | 9 / 40002 / 40003 / 40008 | 群聊消息 / v2 消息 / 编辑 / 引用 diff |
| 频道管理 | 9000/9001/9002/9005/9008/9021/9022 | 加人/移除(含 last-owner guard)/改元数据/管理员删事件/删组/加入(open)/离开 |
| 组发现 | 39000/39001/39002/44100/44101 | relay 签名的频道元数据/管理员/成员/加入/移除广播 |
| DM | 1059 | gift wrap（NIP-44 加密，p-gated） |
| 存在感 | 20001/20002 | presence/typing（ephemeral 不落库） |
| repo/项目 | 30617/30620/30621 | repo 宣告（`buzz-channel` tag 绑频道）/workflow 定义/项目分组 |
| 代码协作 | 1617/1618/1621/1630-1633 | patch（NIP-34，60KB 上限）/PR/issue/状态 open/merged/closed/draft |
| workflow | 46001-46012 | triggered/step started/completed/failed/…/approval requested/granted/denied |
| agent 受雇 | 43001-43006 | job request/accepted/progress/result/cancel/error（特意不用 NIP-90：要求 auth chain depth≤3） |
| agent 身份 | 10100/30174/30175/30179/24200 | agent 档案/加密记忆 Engram/Persona/私有托管 agent/owner 遥测帧（NIP-44） |

### 1.3 频道与线程

- **频道**（`buzz-db/src/channel.rs:21` ChannelRecord）：4 型
  `Stream/Forum/Dm/Workflow`——**workflow 执行本身就是一类频道**；Open/Private；
  `ttl_seconds` 临时频道自动归档；角色 `Owner>Admin>Member>Guest`，**Bot 是独立
  designation 不进层级**（`permission_level()=0`，须显式授权）。
- **"Branch as room"**（`VISION_PROJECTS.md`）：feature branch 自动建频道，
  patch/CI/review/merge 决策同室发生，merge 后频道归档为"代码为什么存在"的永久记录。
- **线程 = NIP-10 marker**：`["e",root,…,"root"]`+`["e",parent,…,"reply"]` 双
  tag 定位；服务端物化 `thread_metadata`（parent/root/depth/reply_count/
  descendant_count，回复到达原子更新，`buzz-db/src/thread.rs:100`）。

### 1.4 同步语义（实时 + 离线 + 最终一致三合一）

| 语义 | 机制 |
| --- | --- |
| 实时订阅 | WS `REQ` → 三层 fan-out 索引 `(channel,kind)` 精确→channel 通配→全局扫描；**全局订阅拿不到频道事件（显式安全边界）**；多节点 Redis pub/sub topic `buzz:{community}:channel:{id}` |
| 离线拉取 | 历史 REQ 回放 + `EOSE`（每 filter 上限 500）；`ON CONFLICT DO NOTHING` 幂等入账 |
| 限流背压 | 连接+handler 信号量(1024)、Redis 固定窗口 admission、帧 64KB、30s 心跳、慢客户端 3 次满缓冲即断、搜索索引有界队列 1000（失败不阻塞提交） |
| agent 身份 | NIP-42 WS 挑战签名 / NIP-98 HTTP 签名请求；**NIP-OA owner 委托**：agent 每个签名事件附 owner 证明 tag，relay 据此让 agent 继承 owner 权限且可瞬间吊销 |

## 二、herdr 运行时（任务执行/隔离/生命周期）

### 2.1 执行与隔离模型

- **层级**：`workspace > tab > pane`；pane 挂一个 PTY 终端，agent（22 种 CLI：
  Claude Code/Codex/Cursor/OpenCode…）是 pane 里的**普通进程**——"herdr 不包装
  不替换它们，只拥有它们的终端"。合盖/断网/重启后 agent 继续跑，任意终端重连。
- **隔离 = 进程级 + git worktree**：`src/worktree.rs` 生成
  `worktree/<形容词>-<名词>-<hex>` 分支；Windows Job Objects；API 通道 Unix
  socket 0o600 / 命名管道 SDDL 仅 SYSTEM+owner。**不做容器级沙箱**——凭证隔离
  交给 agent 本身。
- **任务定义/提交 = JSON socket API**（100+ 方法，`src/api/schema.rs:45`）：
  `workspace.* / tab.* / pane.split… / agent.start/prompt/**wait**/read /
  worktree.* / session.snapshot / server.live_handoff`；schema 由 schemars 生成
  随二进制分发（`docs/next/api/herdr-api.schema.json`），协议带版本号+能力协商。
- **agent 互相协作原语**：`agent.prompt`（向另一 agent 发提示）+
  `agent.wait {until: Vec<AgentStatus>, timeout_ms}`——**一个 agent 可以阻塞等
  另一个真正 idle/blocked 再接手**。

### 2.2 运行时生命周期图

```
                    ┌──────────────── 多源状态仲裁（三方证据）────────────────┐
                    │ ① 屏幕检测：20 agent 的 screen manifest AND/OR 门匹配     │
                    │    （读快照不碰解析器；证据制，不匹配偶然文本）            │
                    │ ② PTY 活动：Working 的常规权威                           │
                    │ ③ 集成 hook 自报：HookAuthority（更可靠，带 session id）  │
                    └───────────────────────────┬────────────────────────────┘
                                                ▼
  AgentState（内部四态）:  Idle ⇄ Working ⇄ Blocked     Unknown（无法确信分类）
                           ▲        │  ▲                （"不证明完成"）
              提示符可见 ───┘        │  └── 识别审批/提问 UI 或 hook 上报
                           │        │
  AgentStatus（API 五态）:  Done = Idle 且 tab 无人看过（PaneState.seen 标志：
                           聚焦/查看过的完成只是 Idle；后台完成的才叫 Done）
                           其余同上 + launch_pending / interactive_ready（agent
                           start 要求 pane 处于 shell 交互提示符）

  pane 生命周期:  spawn →(agent 退出/释放/替换)→ PendingAgentRelease →
                  respawn_shell_on_exit；关闭的 pane/tab ID 永不复用

  会话可存活:    SessionSnapshot v3（全 workspace/tab/pane 序列化）
                 → restore / handoff；live handoff（PTY fd 复制+
                 preserve_processes_on_drop）支持二进制升级不杀进程；
                 AgentResumePlan 按 agent 种类取 session id/path 续跑
```

超时/配额：`agent.start timeout_ms`（3s-300s 校验）、`agent.wait timeout_ms`；
无全局任务配额（本地单用户运行时）。性能纪律："乘法路径"防渲染/检测爆炸、
"State 与 runtime 分离、渲染纯函数、无上帝对象"（`AGENTS.md`）。

## 三、对照 NagaAgent 建议（≥3 条）

NagaAgent 现状锚点：agentserver:8001 军牌调度（`dogtag/`：DogTagRegistry 任务池
+ DogTagScheduler 1s tick，heartbeat 心跳 + screen_vision 屏幕感知 pHash 两源）+
OpenClaw 会话执行 + 任务注册表（spawn/去重/TTL 清理，`NEKO/N.E.K.O/app/agent_server/registry.py`）+
mcpserver 工具农场经 agentic_tool_loop 并行调用。

**建议 1：消息层——单一事件底座 + kind 注册表，替代"每功能一套 API"。**
buzz 的核心设计是**人、agent、workflow、repo 全是同一形状的签名事件**：一个
身份模型、一条事件日志、一个搜索索引、一条审计链，kind 号是唯一分发开关
（新功能零破坏）。对照 NagaAgent：lumo_event 6 类事件挤单 topic、军牌消息走
`/queue/push`、GRAG 五元组自成体系——三者可统一为一张 kind 注册表
（复用 D-03 建议 1 的 7 种任务消息 + 既有 6 类 UI 事件起步，预留号段规则
"标准/replaceable/ephemeral/自定义"四段）。收益：审计链（buzz-audit 哈希链
设计可后置）+ 事后可检索 + 新事件类型不改总线。

**建议 2：状态层——给军牌调度补第三源仲裁与 blocked/done 语义。**
herdr 的 agent 状态是**三方证据仲裁**（屏幕 manifest 检测 / PTY 活动权威 /
集成 hook 自报），且区分 `Idle` 与 `Done`（**done = 无人看过的完成**，seen
标志）。对照 agentserver DogTag：现有两源（heartbeat + screen_vision pHash）
正好对应前两类，缺：(a) **hook 自报源**——让被编排的 agent（trae/mcp 工具）
主动上报状态与 session id（对应 herdr HookAuthority，最可靠）；
(b) **Blocked 态**——识别"agent 在等只有人能答的提示"（herdr 的
`agentWait` 观测），军牌目前只有心跳在/不在；落法：DogTag Duty 加一个
blocked 检测位 + `LUMO_TASK_SEEN` 等价 seen 标志，完成但未被查看的工单在
桌宠侧保持提醒（衔接 NEKO 交互层）。

**建议 3：运行时层——会话可存活三件套（快照/恢复/接管）。**
herdr "服务器拥有终端"使合盖断网不丢 agent；对照 NagaAgent：OpenClaw 会话与
任务注册表已有 spawn/去重/TTL，但无快照恢复——重启后进行中的工单即失联
（本仓 8-23 批共享工作树竞态正是失联的变种）。建议按序补：
(a) 任务台账快照（对应 SessionSnapshot——落到 D-01/D-02 的 Run/Task 库即可，
一张表两用）；(b) **AgentResumePlan 式续跑**——按 agent 类型记录 session
id/path，重启后 resume 而非重派；(c) **takeover 语义**——执行者失联时 fence
旧分支+迁移 pending 状态（orca takeover 与 herdr live handoff 同构，两家独立
验证了这条路）。

**建议 4（补充）：Branch-as-room 对接记忆血统。**
buzz 的"feature branch 自动开频道、merge 后归档成永久记录"，与本仓
trae/agent-* 分支 + PR merge-back + 记忆五件套 lineage（会话血统）三者天然
同构：每张工单分支即一个"房间"，工单事件（dispatch/done/gate）进同一 topic，
merge-back 时把房间时间线写成一张 index_card（血统记 parent 工单）——
"代码为什么存在"从此可被 hybrid_search 检索。这是 buzz 模式在本仓的最低成本
移植：不需要 Nostr 服务器，只需要 topic 纪律。

**建议 5（可选远期）：密钥对身份。**
buzz "密钥对即身份 + NIP-OA owner 委托（可瞬间吊销）"对跨机 agent 舰队
（天选7/云服/手机三实例）有吸引力——GitHub PAT 换发频繁且权限粒度粗。列为
远期评估，不急于落地。

## 四、许可与边界

buzz / herdr 均 Apache-2.0——机制借鉴无风险；两仓库均为重基础设施
（Rust workspace），**不合入源码**（本单硬约束：只读）。上游克隆留在仓外
临时目录，用后即弃。

## 附：信息来源

源码通读（临时克隆 `C:\Users\ASUS\AppData\Local\Temp\agentd-haul\{buzz,herdr}`，
buzz@e236329 / herdr@d6dae88）；buzz `ARCHITECTURE.md`（事件管线 12 步）、
`VISION_PROJECTS.md`（Branch as room）、`crates/buzz-core/src/kind.rs`（127 kind）；
herdr `skills/herdr/SKILL.md`（agent 契约）、`src/detect/mod.rs:11`（AgentState）、
`src/persist/snapshot.rs:15`（SessionSnapshot v3）。
