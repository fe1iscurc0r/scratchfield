# companion durable-execution 授粉 SPEC（2026-09-25）—— NEKO 伴侣状态持久化

> 卷154（NEKO线）· 落盘：砚 · 状态：**仅 SPEC（未写实现代码；NEKO 源码零改动）**
> 参考实现：[`The-Vibe-Company/companion`](https://github.com/The-Vibe-Company/companion)（**MIT**，2402★，gh api 实测 2026-09-25，非 archived）
> 防重复对照：卷139 `mcpserver/graph_memory_adapter`（轻量 KG 记忆）关注**记忆内容**；本 SPEC 关注**执行/状态机层面的持久化**，两者不重叠。
> NEKO 铁律：上游源吃更新、**不改**。本文件只落 `docs/`，`git diff --stat -- NEKO` 必须为 0。
> 匿名铁律：不写真实姓名。

## 0. 结论先说

companion 的"durable execution"不是什么重型框架（**不是 Temporal**），而是三件朴素但成体系的机制：

| 机制 | 实现位置（实测） | 一句话 |
|---|---|---|
| **执行账本** | `packages/agent/src/journal.ts:13` `RunJournal` | 每次 run 落 SQLite（**WAL + synchronous=FULL**），带**状态机** |
| **准入幂等** | `apps/server/src/admission.ts:19` | `requestId` + **指纹** + `pg_advisory_xact_lock`，同 id 不同内容直接冲突 |
| **变更留痕** | `packages/agent/src/memory-store.ts:54` | `memory_mutations` 变更表 + `memory_index_dirty` 索引脏标记 |

**NEKO 的缺口**：现有实现里**没有通用的 checkpoint/状态文件层**（在 `brain/`、`app/` 全量检索 `checkpoint|save_state|state_file|sqlite` 无命中，只有零散的 `json.dumps` 业务调用）。
⇒ 本 SPEC 给出**旁路引入**方案：新起一个 `checkpoint` 侧车，NEKO 三服务器只**挂回调**，不改上游逻辑。

## 1. companion 实测事实（源码引用，非转述）

### 1.1 执行账本：run 状态机 + 崩溃可见性

`packages/agent/src/journal.ts`

- `L1`：`import { Database } from "bun:sqlite"` —— 单文件 SQLite 账本，无外部服务
- `L19`：`PRAGMA journal_mode = WAL; PRAGMA synchronous = FULL; PRAGMA busy_timeout = 5000;`
  —— **WAL + 全同步 + 忙等 5s**：掉电丢的不是"半条记录"，而是"最多最后一个已确认事务"
- `L21-38`：`CREATE TABLE runs (id, request_hash, content, instructions, status CHECK IN ('running','succeeded','failed','interrupted','cancelled'), text, error, lane, response_root_id, publish_to_chat, parked, created_at, updated_at)`
  —— **状态机是表约束**（不是代码里的散装 if）；`parked` 单列表达"挂起待恢复"
- `L40-42`：先 `PRAGMA table_info(runs)` 查列再 `ALTER TABLE ... ADD COLUMN`
  —— **渐进式 schema 演进**（老库直接升级，不需要迁移脚本）

`packages/agent/src/daemon.ts`

- `L22`：`this.journal = new RunJournal(join(stateDir, "runs.sqlite"))` —— 账本按 stateDir 落盘
- `L55`：路由 `/runs/{id}(/cancel|/suspend|/resume)?` —— **恢复是显式的一等操作**
- `L65`：`POST /resume` → `this.park(id, false)` —— 恢复即"取消挂起位"，没有隐式自动重跑
- `L150`：`parked ? executor.suspend(rootId) : executor.resume(rootId)` —— 挂起/恢复下沉到执行器接口

### 1.2 准入幂等：requestId + 指纹 + 咨询锁

`apps/server/src/admission.ts`

- `L6`：`MachineAdmissionInput{requestId: string; companionId: string; kind: MachineAdmissionKind}`
- `L19`：`requestMachineAdmissionInTransaction(...)` 的顺序是：
  1. `SELECT pg_advisory_xact_lock(${globalAdmissionLock})` —— **全局准入串行化**
  2. 按 `id = requestId` 查历史：若已存在且 `fingerprint !== digest` → `AdmissionConflict('Admission request identifier changed.')`
  3. 否则**幂等返回历史结果**（不重复落库）
  4. 再校验 companion 可用性（`FOR UPDATE` 行锁）+ 单机单活跃请求
  5. 最后 `INSERT ... state='queued'`

`apps/server/src/lifecycle.ts`

- `L53`：`requestPreparation(ownerId, companionId, sql, requestId?)`
- `L58`：`kind: companion.archived_at ? 'resume' : 'configuration'` —— **恢复与配置走同一准入通道**
- `L131`：被拒（`refused`）时把原因写回 `companions.error`（`prepare_requested=false`）—— 失败也持久化，重启后能解释"为什么没准备好"

### 1.3 记忆变更留痕

`packages/agent/src/memory-store.ts`

- `L40`：`join(this.memoryDir, "memory.sqlite")`
- `L46`：`CREATE TABLE memories` —— 记忆本体
- `L54`：`CREATE TABLE memory_mutations` —— **每一次变更单独留痕**（可审计/可回溯）
- `L58`：`memory_meta(key, value)` —— 版本/元信息
- `L59`：`memory_index_dirty(id)` —— **索引脏标记**：检索索引崩了/落后了可重建，而不是"记忆丢了"

### 1.4 一条原则（写在它自己的 agent 约定里）

`AGENTS.md:9`：
> "An ambiguous execution must never be automatically replayed. **Agent request IDs survive restart.**"

两条可借的硬规矩：**① 语义模糊的执行绝不自动重放；② 请求 id 必须跨重启存活**。

## 2. NEKO 现状（要映射的目标域）

来自 `NEKO-逻辑理解报告.md`（仓内既有审视报告）与源码实测：

| 层 | 现状 | 与本 SPEC 的关系 |
|---|---|---|
| **四服务器进程隔离** | Main `:48911`（Web UI/REST/WS/会话管理）、Memory `:48912`（对话摄入/事实·反思·人格/recall）、Agent `:48915`（能力状态/任务评估/通道分发）、插件 `:48916` | **天然适合旁路**：进程边界即持久化边界 |
| `app/main_server/` | `character_runtime.py`、`api_runtime.py`、`web_app.py` | 会话/角色运行态在**内存**里，重启即丢（除业务自带落盘） |
| `brain/` | `agent_session.py`、`task_executor.py`、`computer_use.py`、`browser_use_adapter.py`、`openclaw_adapter.py` | 执行侧大量"跑一半"的中间态，**没有统一 checkpoint** |
| 记忆侧 | Memory 服务器管事实/反思/人格 + recall | 有内容层，缺 companion 那种**变更留痕 + 索引脏标记** |

**实测证据（缺口）**：`grep -rnE "checkpoint|save_state|load_state|state_file|sqlite" NEKO/N.E.K.O/brain/*.py NEKO/N.E.K.O/app/*.py` → **无命中**（只有零散 `json.dumps` 业务调用）。⇒ NEKO 目前**没有通用状态持久化层**。

## 3. 源 → 目标映射表（授粉方式）

| companion 组件 | NEKO 对应层 | 授粉方式 | 收益 |
|---|---|---|---|
| `RunJournal`（run 状态机 + WAL） | `brain/task_executor.py` 的任务生命周期 | **旁路**：新 `checkpoint` 侧车（独立 SQLite），NEKO 只调 `record(state)` | 重启后知道"哪些任务跑到哪、哪些是 interrupted" |
| `runs.status CHECK(...)` 状态机 | 任务/会话状态 | **照搬约束思路**（状态集封闭，禁止魔法字符串） | 状态判断不再散落各处 |
| `parked` + `/suspend`·`/resume` | Agent 服务器能力状态（`:48915`） | **旁路**：暴露挂起/恢复 HTTP 端点，勾到既有 API 路由 | 长任务可挂起跨重启续跑 |
| `requestId + fingerprint + 咨询锁` | Main 服务器会话/请求入口（`:48911`） | **照搬语义**（SQLite 用唯一索引 + 事务代替咨询锁） | 客户端重试不产生重复副作用（幂等） |
| `memory_mutations` 变更表 | Memory 服务器事实/反思写入（`:48912`） | **旁路**：在既有写入路径**之后**追加变更记录（不改上游写逻辑） | 人格/事实可回溯、可解释 |
| `memory_index_dirty` 脏标记 | recall 索引 | **旁路**：索引重建任务读脏表 | 索引坏了可重建，不必重灌记忆 |
| `AGENTS.md:9` 两条原则 | 全局约定 | **写进本仓 rules/SPEC** | 模糊执行不自动重放 + 请求 id 跨重启存活 |

## 4. 数据结构共鸣（三处）

1. **状态机 vs 散装布尔**：companion 把 run 状态做成表约束（`journal.ts:21-38`），
   NEKO 侧任务是多个布尔/字符串字段拼出来的 ⇒ 建议 NEKO 侧 checkpoint 表也用**封闭状态集**
   （`pending|running|parked|succeeded|failed|interrupted`），并把"挂起"做成独立状态而不是布尔位。
2. **变更留痕 vs 只存结果**：companion 的 `memory_mutations`（`memory-store.ts:54`）保留了**过程**；
   NEKO 的记忆写入目前只保结果 ⇒ 引入变更表后，"为什么这句人格变成这样"才有答案。
3. **脏标记 vs 全量重算**：`memory_index_dirty`（`memory-store.ts:59`）把"索引坏了"降级为可修的小问题；
   NEKO 的 recall 索引若失效目前只能重灌 ⇒ 脏表是低成本的韧性提升。

## 5. checkpoint 触发时机与恢复流程（旁路设计）

**触发时机（从便宜到贵）**：
1. **状态转移时**（任务进入/离开 running/parked/…）—— 必写，成本 O(1)
2. **长任务心跳**（如 30s）—— 只更新 `updated_at` + 进度摘要
3. **显式检查点**（工具调用边界、外部动作前后）—— 写"意图 + 结果"，供幂等判断
4. ~~每次 token~~（不做：写放大）

**恢复流程**：
```
重启 → 读 checkpoint 表 → 取 status IN ('running','parked','interrupted') 的记录
     → 对每条：① 有 requestId 且已完成的 → 直接复用结果（幂等，不重放）
               ② parked → 交给用户/策略决定是否 /resume（**不自动**）
               ③ running 但无终态 → 标 interrupted，写入原因，等人工确认
```

**崩溃恢复语义（照 companion 的口径，写清楚不糊）**：
- **at-least-once**（不是 exactly-once）：执行可能重跑，因此**副作用必须有幂等键**（对应 `admission.ts:19` 的 fingerprint 冲突检测）
- **模糊执行不自动重放**（`AGENTS.md:9`）：宁可按 interrupted 停下，也不猜

## 6. 难度 × 收益

| 项 | 难度 | 收益 | 档位 |
|---|---|---|---|
| checkpoint 侧车（独立 SQLite + 三处回调） | 低 | 高（重启不丢档） | **立即授粉** |
| 准入幂等（唯一索引 + 指纹） | 低 | 高（重试不重复副作用） | **立即授粉** |
| 脏标记 + 索引重建任务 | 低 | 中 | **立即授粉** |
| parked/suspend/resume 端点 | 中 | 中高（长任务跨重启） | 暂缓（等 checkpoint 侧车稳定） |
| memory_mutations 变更表接 Memory 服务器 | 中 | 中（可解释性） | 暂缓（需先敲定写入路径挂点） |
| 用 Postgres 替代 SQLite 控制面 | 高 | 低（本机场景不需要） | 参考（NEKO 是桌面端） |

## 7. 未决项 / 边界

1. **本卷只出 SPEC**：无实现、无适配器；`git diff --stat -- NEKO` 为 0（不碰上游）。
2. **companion 的持久化依赖 Postgres 控制面**（`apps/server/src/config.ts:40`），而 NEKO 是**桌面端**（本仓偏好 Windows 一键 + SQLite）⇒ 照搬的是**机制**，不是部署形态；控制面那一层明确**不引**。
3. **未跑 companion**（TS/bun monorepo，本机未装 bun）⇒ 本文结论来自**源码阅读**，不是运行时实测。
4. **NEKO 侧的挂点未逐行确认**：`brain/task_executor.py` 与 `app/agent_server/api_routes.py` 的具体插桩位置需在实现卷再核。
