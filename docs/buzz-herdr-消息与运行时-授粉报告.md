# block/buzz × herdrdev/herdr — 消息协议 × 运行时执行模型 授粉报告

> 工单：D-04 | 许可：Apache-2.0 × 2 | 仓库：block/buzz / herdrdev/herdr
> 报告日期：2026-08-23 | 调研人：实验田维护者 · 三元融合系统（Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互）语境
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

*—— 实验田维护者 · buzz 是"万物皆事件"，herdr 是"进程即任务"；一个定义消息协议，一个定义执行模型，两者合起来正是三元融合缺的那两块拼图 🐝🐑*
