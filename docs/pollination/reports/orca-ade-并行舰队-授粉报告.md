# stablyai/orca ADE 并行舰队编排 — 授粉报告

> 工单：D-01 | 许可：MIT | 仓库：stablyai/orca (51k★) | 报告日期：2026-08-23
> 调研人：沈遥 · 三元融合系统（Hermes + NagaAgent + N.E.K.O.）语境

---

## 一、Orca 到底是什么

Orca（MIT）是 Stability AI 出品的**桌面 AI 编排器**，核心理念：

> "Run Codex, ClaudeCode, OpenCode or Pi side-by-side — each in its own worktree, tracked in one place."

**注意**：仓库中不存在 "ADE"（Agent Development Environment）这个独立概念。Orca 将整个桌面环境视为一个分布式 Agent Development Environment，但代码中的 `ade` 字符串是 `Tiptap` 编辑器库中的标记名（auto-generated ID），与编排无关。本报告以**并行舰队编排**为分析核心。

---

## 二、核心编排模式

### 2.1 架构三元素

| 元素 | 含义 | 类比 |
|------|------|------|
| **Run** | 协调者命名空间 + 消息收件箱 | 会议室 |
| **Task** | 工作项，描述 spec + 状态（pending/ready/dispatched/completed/failed/blocked） | 任务卡 |
| **Dispatch** | 一次 Task 到具体 Agent Terminal 的分配尝试 | 任务指派 |

- **Task 与 Dispatch 分离**：一个 Task 可多次 Dispatch（重试），但 Dispatch 是 Terminal 级别的一次性绑定。
- **Task DAG**：Task 有 `deps`（依赖数组）和 `parent`（父子链），支持有向无环图编排。
- **Decision Gate**：`gate-create / gate-resolve` 提供协调者主导的阻塞式决策点，区别于 `ask`（worker 向协调者提问）。

### 2.2 编排模式 ASCII 图

```
┌─────────────────────────────────────────────────────────┐
│                    COORDINATOR RUN                       │
│  收件箱：worker_done / escalation / question / heartbeat  │
└──────┬──────────────┬──────────────┬────────────────────┘
       │              │              │
       │ task-create  │ task-create  │ task-create
       ▼              ▼              ▼
   Task A         Task B         Task C
  (deps:[])     (deps:[A])     (deps:[A])
       │              │              │
       │worker-start  │              │
       ▼              │              │
   Terminal 1◄──dispatch──┘         │
  (Codex Agent)                      │
       │                              │
       │ check --wait                 │
       │ ──worker_done──►             │
       │ ──escalation──►              │
       │ ──question──►               │
       │                              │
       │  gate-create                 │
       │  (blocking)                  │
       │                              │
       │      └──────────────────────┘
       │             task-create
       │                Task D
       │            (deps:[B,C])
       │                 │
       │                 │ worker-start
       │                 ▼
       │            Terminal 2
       │          (Claude Agent)
       │                 │
       └─────◄──── dispatch (blocking ask from D)
```

**并行度控制**：Orca 不做自动调度，由协调者控制并发数量。文档明确说：

> "Coordinators should use `task-list --ready` as external memory, **dispatch parallel waves**, and avoid dependency chains deeper than 3-4 steps."

### 2.3 生命周期消息协议

```
worker_done    → worker 正常/异常结束，协调者收报告
escalation     → worker 权限升级请求
question       → worker 向协调者阻塞提问（协调者 reply 回答）
heartbeat      → 存活心跳（15s 间隔 JSON 到 stderr）
decision_gate  → 协调者阻塞等待外部决策
```

### 2.4 隔离机制：git worktree

Orca 的每个 worker 运行在**独立的 git worktree** 中：

- 同一 repo 的多个 agent 并行工作在独立分支
- 不会产生 git 冲突
- 协调者可切换/合并 winner
- 也支持 folder workspace（非 git）

### 2.5 远程执行

Worktree 可分布到 SSH 远端或 Orca Server：

```
Mac 本地 Run home ──dispatch──► Windows Worker (--on windows)
```

Orca RPC 路由通过 Dispatch ID 跨服务器寻址，不依赖终端句柄的远程传播。

---

## 三、对照 INTEGRATION_PLAN.md

| 维度 | INTEGRATION_PLAN 定位 | Orca 编排可借鉴点 |
|------|----------------------|------------------|
| 多智能体编排 | D 组工单（无专门章节） | Orca 是最完整的参考实现 |
| Task DAG | 无 | Orca 原生支持 deps + parent |
| 决策门 | 无 | Orca gate-create 支持协调者阻塞决策 |
| Worker 隔离 | 无 | git worktree 天然隔离 |
| 结果汇聚 | 无 | worker_done 消息带 files_modified/report_path |
| 消息总线 | 无 | inbox/check/send/reply/ask 完整协议 |

**结论**：INTEGRATION_PLAN 中多智能体编排是空白项，Orca 的 Run/Task/Dispatch 三层模型可直接填补。

---

## 四、针对三元融合的授粉建议

### 建议 1：采用 Task/Dispatch 双层抽象统一编排层

**原理**：Orca 的 Run=命名空间/收件箱、Task=工作项、Dispatch=分配 三层，与 Hermes（智能体运行时）+ NagaAgent（本地 agent 服务）+ N.E.K.O.（记忆模块）的三角结构天然正交。

**具体建议**：在 `mcpserver/` 下新建 `orchestration/` 模块，复刻 Orca 三层：

```
scratchpad/mcpserver/orchestration/
├── models.py      # Run/Task/Dispatch 数据类
├── message.py     # worker_done/heartbeat/ask/escalation 协议
├── dispatcher.py  # Task → Agent 分配逻辑
└── inbox.py       # 消息收件箱（类似 Orca Run inbox）
```

**验收**：

```bash
# 验收1：目录存在且含核心文件
ls /home/ubuntu/scratchpad/mcpserver/orchestration/

# 验收2：models.py 含三元素
grep -E "class (Run|Task|Dispatch)" /home/ubuntu/scratchpad/mcpserver/orchestration/models.py

# 验收3：message.py 含 worker_done
grep "worker_done" /home/ubuntu/scratchpad/mcpserver/orchestration/message.py
```

**结论**：**参考**（不直接合入 MIT 代码）— 设计可移植，MIT 可直接借鉴。

---

### 建议 2：引入 Decision Gate 机制作为三元融合的协调者阻塞点

**原理**：Orca 的 `gate-create` 让协调者在关键节点等待人工/外部决策，类似三元融合中 Hermes 协调者（NagaAgent 执行层）在重大决策前的暂停点。

**具体建议**：在 `mcpserver/` 增加决策门表：

```python
# mcpserver/orchestration/decision_gate.py
class DecisionGate:
    task_id: str
    question: str          # 决策问题
    options: list[str]     # 可选决策
    status: str            # pending/resolved
    resolution: str | None
    created_at: datetime
```

决策门可以是：
- Hermes 发起的「战略决策」等待（N.E.K.O. 提供上下文）
- NagaAgent 执行层发起的「路径选择」等待（多方案选一）
- 人工介入点（外部触发 resolve）

**验收**：

```bash
# 验收1：DecisionGate 类存在
grep -E "class DecisionGate" /home/ubuntu/scratchpad/mcpserver/orchestration/decision_gate.py

# 验收2：status 字段含 pending/resolved
grep "pending\|resolved" /home/ubuntu/scratchpad/mcpserver/orchestration/decision_gate.py

# 验收3：task_id 外键关联 Task
grep "task_id" /home/ubuntu/scratchpad/mcpserver/orchestration/decision_gate.py
```

**结论**：**直接可用**（架构简单，纯 Python，无外部依赖）。

---

### 建议 3：移植 git worktree 隔离模式到 Hermes subagent 进程管理

**原理**：Orca 用 git worktree 实现 agent 隔离，避免并行冲突。三元融合中 Hermes 调度多个 subagent（如 rf_brain 的 phase 执行器）若共享工作目录会产生竞争。

**具体建议**：为 Hermes 的 subagent 池引入「工作树」概念：

```python
# mcpserver/orchestration/worktree.py
class AgentWorktree:
    """轻量 subagent 进程隔离，类 git worktree 但基于文件系统快照"""
    worktree_id: str
    work_dir: Path          # 隔离工作目录
    agent_type: str         # 'naga' / 'neko' / 'hermes'
    status: str             # active / reclaimable / released
```

实现：subagent 启动前 `os.fork()` + `chdir(隔离目录)`，或直接用 `tempfile.mkdtemp()` + `PYTHONPATH` 隔离。

**验收**：

```bash
# 验收1：AgentWorktree 类存在
grep -E "class AgentWorktree" /home/ubuntu/scratchpad/mcpserver/orchestration/worktree.py

# 验收2：work_dir 隔离字段
grep "work_dir\|worktree_id" /home/ubuntu/scratchpad/mcpserver/orchestration/worktree.py

# 验收3：状态机含 active / reclaimable / released
grep "active\|reclaimable\|released" /home/ubuntu/scratchpad/mcpserver/orchestration/worktree.py
```

**结论**：**参考**（Orca worktree 强依赖 Git，不宜直接合入；可抽取隔离思路实现）。

---

## 五、结论分级

| 建议 | 结论 | 理由 |
|------|------|------|
| 1. Task/Dispatch 双层抽象 | **参考** | 设计可移植，MIT 无传染；建议新写实现而非克隆 orca 代码 |
| 2. Decision Gate 机制 | **直接可用** | 纯 Python 数据类，无外部依赖；可立即在 `mcpserver/orchestration/` 落地 |
| 3. git worktree 隔离模式 | **参考** | Orca worktree 强绑 Git，不适合合入；建议抽取「进程隔离」思路独立实现 |

**综合评级**：**参考** — Orca 编排架构是迄今最完整的多智能体舰队实现，其设计可直接映射到三元融合的 Hermes 协调层 + NagaAgent 执行层，但 Orca 本身（Electron 桌面应用 + Rust 运行时）不适合直接合入。Decision Gate 可**直接可用**，其他两条作为架构参照。

---

## 六、Orca 关键源码索引

| 文件 | 关键内容 |
|------|---------|
| `skill-guides/orchestration.md` | 编排完整协议文档（Run/Task/Dispatch/gate/worker 生命周期） |
| `src/cli/handlers/orchestration.ts` | 1327 行编排 CLI 命令实现 |
| `src/shared/orchestration-rpc-contract.ts` | 38 个 RPC 方法名常量 |
| `src/cli/handlers/worktree.ts` | git worktree 创建/删除/列表管理 |
| `skills/orchestration/SKILL.md` | Orca Agent Skill 规范 |

---

*—— 沈遥 · Orca 并行舰队：Task/Dispatch 是壳，Decision Gate 是魂，worktree 隔离是盾 🐾*

---

> **【附录：另一会话同题报告原文】** 以下为同名授粉报告的另一版本（2026-08-23 并行会话产出），与上文互为补充，合并时保留以防资料丢失。

# orca ADE 并行舰队 · 授粉报告（D-01）

> 智能体 D · 2026-08-23 · 只读调研，未写一行业务码
> 上游：[stablyai/orca](https://github.com/stablyai/orca)（MIT，Lovecast Inc.，~49k★，
> Electron 桌面 ADE——"the ADE for working with a fleet of parallel agents"）
> 调研方式：浅克隆至仓外临时目录通读源码（代码未进主仓）；行号引用相对 orca 仓库根。
> 对照基准：本仓 `INTEGRATION_PLAN.md`（知识底座五阶段融合计划）+ 三元融合现状
> （Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互，定义见 `docs/TRAE_PROMPT-low-star-fusion-v1.md:12`）

---

## 一、一句话结论

**Orca 本体不内置 LLM 任务分解器。**"coordinator"是跑在 Orca 终端里的一个 LLM
agent，通过 `orca orchestration ...` CLI 原语（Run/Task/worker-start/check/gate）
自己完成分解、分发、等待与汇聚；Orca 提供的是四件持久化基础设施——SQLite 状态库
（WAL + busy_timeout）、消息总线、worker 生命周期监督（心跳/熔断/接管）、
worktree/PTY/终端基础设施。**编排智能在 agent 侧，编排确定性在宿主侧**——这是
对三元融合最值得抄的架构判断。

## 二、编排模式图（任务分解 → 并行 → 汇聚）

```
┌─────────────────────────────────────────────────────────────────────┐
│ 用户一条 objective                                                    │
│   │  orca orchestration run-create --objective <text>                │
│   ▼                                                                  │
│ [Run]  namespace + coordinator 收件箱（从不调度 worker）               │
│   │                                                                  │
│ │1│ 任务分解（coordinator LLM 逐条 task-create）                      │
│   │  Task: {spec, task_title, deps[], parent_id, status}             │
│   │  初始状态：deps 未全 completed → pending；否则 → ready            │
│   ▼                                                                  │
│ │2│ 并行分发 dispatchReadyTasks（宿主确定性循环）                      │
│   │  · max_concurrent（内置 Coordinator 默认 4）                      │
│   │  · 每 tick 至多新开 1 个终端（防瞬时炸开）                         │
│   │  · dispatch 锁：一个终端同时只持一个 active dispatch               │
│   │  · stale-base 守卫：worktree 落后 base → 拒发，下 tick 重试        │
│   ▼                                                                  │
│ ┌───────────────┬───────────────┬───────────────┐                    │
│ │  Worker A     │  Worker B     │  Worker C …   │  每人：             │
│ │ worktree(独立) │ worktree      │ worktree      │  · git worktree    │
│ │ PTY+agent CLI │               │               │    --no-track -b   │
│ │ preamble 注入  │               │               │  · PTY 起本地 CLI  │
│ │ (任务协议)     │               │               │  · preamble 教会   │
│ └──────┬────────┴──────┬────────┴──────┬────────┘    agent 用 CLI     │
│        │ heartbeat 5min（10min 无心跳只告警不判死）                     │
│        │ ask / escalation（阻塞问答升级到人）                           │
│   ▼    ▼               ▼               ▼                              │
│ │3│ 结果汇聚 worker_done（恰一次，outcome+3句摘要+files+report_path）  │
│   │  reconcileWorkerDone 严格鉴权（pane/handle/taskId+dispatchId 双匹配）│
│   │  → tasks.result 落库；deps 全 completed → promoteReadyTasks        │
│   ▼                                                                  │
│ │4│ DAG 收敛 evaluateDagConvergence：empty / all-done / active/Stuck   │
│   │  coordinator LLM 读各 worker result 自行综合（无自动评分选优）      │
│   │  人裁决 → decision gate（kind=gate，永不自动 resolve）             │
│   ▼                                                                  │
│ 产出落地：worktree 分支 → push → GitHub PR（gh CLI + 限流断路器）       │
│          Linear/GitHub issue 反向"一键开 worktree"                     │
└─────────────────────────────────────────────────────────────────────┘

状态机  Task: pending → ready → dispatched → completed|failed|blocked
        Dispatch: pending/dispatched/completed/failed/circuit_broken
        熔断：同任务连续失败 3 次 → circuit_broken（DISPATCH_CIRCUIT_BREAK_FAILURES=3）
        Gate: pending / resolved / timeout（必须人用 gate-resolve）
```

## 三、关键机制与源码锚点

| 机制 | 事实 | 源码锚点 |
| --- | --- | --- |
| 分解主体 | 内置 Coordinator 明确"不做自动分解，任务须预先创建" | `src/main/runtime/orchestration/coordinator.ts:145-156` |
| Run/Task schema | tasks 表：spec/deps(JSON DAG)/parent_id/result + 创建者血统四元组 | `db/schema/create-graph-tables-sql.ts:88-108`、`types.ts:246-262` |
| 并行限流 | `maxConcurrent` 默认 4；每 tick ≤1 新终端 | `coordinator.ts:35,228-299` |
| 依赖推进 | 完成事务内 promoteReadyTasks；全 blocked 无 active → Stuck 告警 | `db/tasks/task-store.ts:194-213`、`coordinator-dag-convergence.ts:6-32` |
| worker 协议 | preamble 注入 PTY：worker_done 恰一次/heartbeat 5min/ask/escalation | `preamble.ts:47-145` |
| 隔离 | worktree `--no-track -b` 集中于 `~/orca/workspaces`；凭证不注入 worker（各 CLI 自己 OAuth，per-account home 热切换） | `src/main/git/worktree.ts:952-1072`、`claude-accounts/environment.ts:1-38` |
| 汇聚结算 | worker_done 严格鉴权后写 tasks.result；无自动选优 | `lifecycle-reconciliation.ts:174-305` |
| 熔断/守卫 | 3 连败熔断；stale-base 拒发 | `dispatch-circuit-breaker.ts:2`、`coordinator-task-dispatch.ts:79-89` |
| 中断恢复 | 状态全在 SQLite；CLI 幂等（mutation_receipts）；coordinator 崩溃 takeover（fence 旧实例+迁移 pending 邮件） | `db/orchestration-db.ts:24-34`、`runs.consumer_generation` |
| 消息类型 | 9 种：status/dispatch/worker_done/merge_ready/escalation/handoff/decision_gate/question/heartbeat | `types.ts:2-12` |

## 四、对照 INTEGRATION_PLAN.md 与三元融合现状

`INTEGRATION_PLAN.md` 是知识底座五阶段融合计划（语义网→逻辑引擎→混合检索→
Obsidian 桥→热力学材料，36 项），**通篇没有"任务编排层"条目**——它是"融合什么"
的清单，不含"多 agent 怎么协同施工"。三元融合现状里最接近 orca 能力的资产：

| orca 机制 | 三元融合现状 | 差距 |
| --- | --- | --- |
| Run/Task DAG 状态库 | `research/planner/planner.py`（PlannerExecutor，Send() 式 map-reduce） | planner 有分解/并行/归约，但**无持久状态库**：进程退出即失忆，无 ready/pending/blocked 状态推进 |
| worker preamble 协议 | 工单 prompt（TRAE_WORKORDER_PROMPT_AGENT_*.md，自包含工单+验收+硬约束） | 工单是"一次性文本"，无 worker_done/heartbeat/ask 的**结构化回报通道**（现在靠 commit message 人读） |
| 并行限流/熔断 | BATCH-WORKORDERS 分发说明表（人肉排序"执行顺序"） | 无机器可执行的并发预算与失败熔断 |
| decision gate | 沈 遥（Hermes 人格位）出 SPEC + review；PR merge-back 人工合并 | 审查是流程惯例，不是协议化 gate（无 pending/resolved 状态） |
| worktree 隔离 | `trae/agent-a..g` 独立分支 + PR merge-back（已同构！见 agent-e 分支 PR#36 回收 61 提交） | 分支隔离已有；缺 stale-base 守卫（main 漂移后 rebase 检查）与 dispatch 锁 |

## 五、三元融合可落地建议（≥3 条）

**建议 1：把 Run/Task DAG 状态库立为三元编排底座（决策→执行→交互的全链账本）。**
新建 `mcpserver/orchestration/`（或挂 agentserver），SQLite WAL 单库存
`runs(objective, coordinator)` + `tasks(spec, deps[], parent_id, status, result)`
+ `dispatches(agent, attempt, circuit_broken)`。映射三元：Hermes 决策 =
task-create + gate-resolve（人）；NagaAgent 执行 = dispatch→worker（各
trae/agent-* 分支即 worker，worktree/分支模式现成）；NEKO 交互 = task 状态变更
经 lumo_event → 桌宠播报（"工单 WO-03 已完成，等你验收"）。第一步可以把
`research/planner` 的 `LocalBackend.submit_batch` 升级为写这张表，即获得断点续跑
与 Stuck 检测，不动 apiserver 主流程。

**建议 2：用 orca 的 9 种消息类型扩展 lumo_event，让工单回报结构化。**
现状 `apiserver/routes/lumo_event.py:211` 把 NEKO 来的 6 类事件统一 emit 成单个
`USER_INPUT_RECEIVED` topic。借 orca 消息模型定义 Lumo 协作消息枚举：
`task.dispatch / task.done / task.blocked / question / escalation /
decision_gate / heartbeat`（先取 7 种）。落法：工单模板加一节"回报契约"
（对应 orca preamble）——智能体完成一单报 `task.done`（含 commit、验收结果、
阻塞说明），沈遥验收通过回 `gate.resolved`。这些消息同时喂 EventBus v2
（`apiserver/event_bus/`，已落地）与记忆五件套 index_cards（写卡即索），一箭三雕。

**建议 3：给现有 trae/agent-* 分支模式补三件确定性保险丝。**
分支隔离与 PR merge-back 已与 orca 同构，缺的是宿主侧确定性守卫：
(a) **熔断**——同一工单连续失败 3 次标 `circuit_broken`，不再自动重派，升级为
escalation（对应 orca `DISPATCH_CIRCUIT_BREAK_FAILURES=3`）；
(b) **stale-base 守卫**——merge-back 前检查 main 自分叉后是否漂移，漂移超阈值
拒绝合并要求 rebase（对应 `coordinator-task-dispatch.ts:79-89`）；
(c) **takeover**——工单执行者失联时，"接管"语义 = fence 旧分支 + 迁移 pending
状态给新 agent（对应 `run-use --takeover-legacy` 与 `runs.consumer_generation`）。
三件都可以先做成 merge-back 前的检查脚本（纯增量，不碰主流程）。

**建议 4（进阶）：coordinator-as-agent 的编排哲学直接可抄。**
Orca 把"分解智能"放在 LLM（跑在终端里、用 CLI 原语）而把"调度确定性"放在宿主。
对应到本仓：让陆墨（Lumo）担任 coordinator——它已有 intent_router +
agentic_tool_loop 并行工具调用（`apiserver/agentic_tool_loop.py:1198-1218`），
只需把"工具"换成"工单 CLI 原语"（create-task/dispatch/check/gate-resolve），
即可从"并行调工具"升级为"并行派舰队"。这与 M4 决策铁律"指令源=陆墨，NEKO brain
不自决策"完全一致。

## 六、许可与边界

- orca MIT（`LICENSE`，Copyright 2026 Lovecast Inc.）——机制借鉴无传染风险；
  本报告只授粉设计，不合入其源码。
- 本单零代码改动（硬约束满足）；上游浅克隆留在仓外临时目录，用后即弃。

## 附：信息来源

源码通读（临时克隆 `C:\Users\ASUS\AppData\Local\Temp\agentd-haul\orca` @
7a739c6b）；上游官网 [onorca.dev](https://www.onorca.dev/)；社区评测
[知乎：当 IDE 变成 ADE](https://zhuanlan.zhihu.com/)、
[awesome-agent-orchestrators](https://github.com/andyrewlee/awesome-agent-orchestrators)。
