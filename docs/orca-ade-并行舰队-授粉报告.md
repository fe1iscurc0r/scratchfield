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
