# ChemGraph 授粉报告 · 科研 agent 框架 → Lumo 计算/实验任务调度 + 实验记录持久化

> 来源：argonne-lcf/ChemGraph（146★，Apache-2.0，Python，LangGraph + ASE + MCP）
> 审查：实验田维护者（Hermes）｜日期：2026-08-17
> 定位：融合参考层——不整包吞，提取「多后端执行抽象 + Planner-Executor 任务分解 + 会话/实验记录持久化」三大件，授粉到 Lumo 科研大脑。

---

## 一、这是什么

ChemGraph 是 Argonne 国家实验室（LCF）出的 agentic 框架，把「自然语言 → 分子模拟工作流」自动化：LLM 规划任务，通过 LangGraph 多 agent 图分解执行，后端接 NWChem/ORCA/XTB/MACE 等计算引擎（走 ASE 抽象），支持本地 / Parsl / Globus Compute 多后端，MCP 封装计算工具。对 Lumo 的价值不在化学本身，在**「科研任务怎么被 agent 编排 + 怎么调度执行 + 怎么持久化」**这三层骨架。

---

## 二、源领域 → 目标域 映射

| 源（ChemGraph） | 目标（Lumo 科研大脑） | 授粉方式 | 收益 |
|---|---|---|---|
| `ExecutionBackend` 抽象（`execution/base.py`） | Lumo 计算/实验任务的设备抽象层（本地/远程/HPC） | 抄 ABC + TaskSpec + 两个关键 property | 高 |
| `is_async_remote` + `shares_filesystem` 判据 | Lumo 任务「同步 vs 异步」「共享 vs 无共享文件系统」路由 | 抄两个 property 的语义 | 高 |
| Planner-Executor `Send()` map-reduce（`graphs/multi_agent.py`） | Lumo 科研任务分解 → 并行执行 → 汇总 | 抄图结构 + 状态 reducer | 中 |
| `memory/store.py` SQLite 四表 + 前缀增量同步 | Lumo 实验记录/会话持久化 | 抄 schema + `synchronize_messages` 逻辑 | 高 |
| MCP 工具封装（`mcp/*_mcp_hpc.py`：ASE/XANES/Docking/GRASPA/MACE） | Lumo 计算工具 MCP 化 | 参考封装模式 | 中 |

---

## 三、核心数据结构共鸣（四处最值钱的）

### 3.1 ExecutionBackend 多后端抽象 —— Lumo 的设备抽象层

```python
# execution/base.py:91 附近
class ExecutionBackend(ABC):
    @property
    def is_async_remote(self) -> bool:
        """远程队列（作业可能几分钟到几小时）→ MCP 工具提交后立即返回，
        另提供 status/result 工具，而不是阻塞到完成。"""
        return False

    @property
    def shares_filesystem(self) -> bool:
        """worker 是否与提交方共享文件系统。True（默认）路径直读；
        Globus Compute 覆写为 False（远端无共享 FS），走 inline embedding 传输。"""
        return True

    def submit(self, task: TaskSpec) -> Future: ...
```

**共鸣点**：这是 Lumo 最该抄的一处。记忆里 Lumo 的方向是「协议无关设备抽象层」，ChemGraph 给了现成判据：**用两个 property 区分任务的时空形态**——`is_async_remote` 决定「提交后立即返回 vs 阻塞等待」，`shares_filesystem` 决定「路径直读 vs inline 打包传输」。Lumo 跑实验/计算任务（本地跑 / 云服跑 / HPC 跑）正好缺这两个维度的显式建模。

### 3.2 TaskSpec —— 统一任务单元

```python
# execution/base.py:21 附近
class TaskSpec(BaseModel):
    task_id: str
    task_type: Literal["python", "shell"] = "python"
    callable: Optional[Callable] = None     # python 模式
    command: Optional[str] = None           # shell 模式
    # 资源 hints（advisory，后端可不认）：
    num_nodes: int = 1
    processes_per_node: int = 1
    gpus_per_task: int = 0
    env: Dict[str, str] = {}
```

**共鸣点**：Lumo 的「实验/计算任务」现在没有统一数据模型。`TaskSpec` 用一个 Pydantic 模型统一了「python callable」和「shell command」两种执行形态 + 资源 hints（node/进程/GPU）。授粉后 Lumo 的任务队列里所有任务都是 `TaskSpec`，后端只认这一个类型——设备抽象层的第一块砖。

### 3.3 Planner-Executor `Send()` map-reduce —— 科研任务分解并行

```python
# state/multi_agent_state.py:25 附近
class ExecutorState(TypedDict):
    """每个 Send() 派生一个独立状态副本，隔离各自的 ReAct 对话。"""
    messages: Annotated[list, add_messages]
    executor_id: str
    task_index: int      # 关联到 planner 的哪个任务
    retry_count: int

class PlannerState(TypedDict):
    executor_results: Annotated[list, operator.add]   # 所有 executor 结果合并
    failed_tasks: Annotated[list, operator.add]        # 失败累积，供重试决策
    planner_iterations: int                            # 防无限 Planner→Executor 循环
    clarification: Optional[str]                       # ask_human 路由的问题文本
```

```python
# graphs/multi_agent.py:7
# Planner --condition--> Send(executor_subgraph, task1..N) --> Planner
```

**共鸣点**：Lumo 的科研工作流（「查文献 → 设计实验 → 跑计算 → 汇总」）天然是「规划 → 分解 → 并行执行 → 汇总 → 失败重试」。ChemGraph 的 `Send()` map-reduce + reducer 合并（`operator.add`）+ `failed_tasks` 累积 + `planner_iterations` 防循环，正好是 Lumo 要的骨架。尤其 `clarification` 字段——planner 可以路由到 `ask_human`，这是「agent 拿不准就问人」的显式建模，Lumo 实验设计里「AI 不确定配方参数时问用户」直接复用。

### 3.4 SQLite 会话存储 + 前缀增量同步 —— Lumo 实验记录持久化

```python
# memory/store.py:360 附近 synchronize_messages
stored_ids = [row["message_id"] for row in stored]
incoming_ids = [m.message_id for m in messages]
is_prefix = (all(stored_ids) and len(stored_ids) <= len(incoming_ids)
             and stored_ids == incoming_ids[: len(stored_ids)])
if is_prefix:
    suffix = messages[len(stored_ids):]      # 前缀一致 → 只追加 suffix
else:
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    suffix = messages                        # 不一致 → 全删重写
```

**共鸣点**：Lumo 的实验记录（多轮科研会话 + subagent 跑的计算）需要一个可靠的持久化 + 幂等同步。ChemGraph 的四表设计（`sessions` / `messages` / `subagent_runs` / `subagent_messages`）+ WAL + 0o600 权限，以及「**前缀判断做增量同步**」——`stored_ids == incoming[:len]` 就只追加，否则全删重写——这跟 cascade 授粉的「读回确认」是同一哲学，且是生产级实验记录库的现成 schema。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| `ExecutionBackend` + `TaskSpec` 抽象 | **低**（纯 Python，无硬件依赖，~200 行） | **高**（Lumo 设备抽象层第一块砖） | **立即授粉**，先落 local 后端跑通 |
| `is_async_remote` + `shares_filesystem` 判据 | **低**（两个 property） | **高**（任务时空形态路由） | **立即授粉**，随 TaskSpec 一起 |
| SQLite 四表 + 前缀增量同步 | **低**（SQLite 无依赖） | **高**（实验记录持久化） | **立即授粉**，schema 直接抄 |
| Planner-Executor `Send()` map-reduce | **中**（依赖 LangGraph） | **中**（科研任务并行分解） | 参考，Lumo 若不用 LangGraph 可自己实现 fan-out |
| MCP 工具封装（ASE/XANES/Docking） | **中**（依赖 ASE/RDKit） | **中**（计算工具 MCP 化） | 暂缓，等 Lumo 有真实计算需求再拉 |

**总评**：ChemGraph 的 146★ 值在「科研 agent 的工程骨架」——不是化学（Lumo 不搞 DFT），是**任务抽象（TaskSpec）+ 执行路由（is_async_remote/shares_filesystem）+ 持久化（SQLite 前缀增量）**三件套。最高优先级是 3.1/3.2（执行抽象）和 3.4（记录持久化），都是纯 Python/零依赖、可直接抄进 Lumo 的 `research/` 模块。LangGraph 的 Planner-Executor 图结构参考即可，不必引入 LangGraph 依赖。

---

## 五、可执行验收（可 grep / assert）

```bash
# 1. 本报告含三大件（工单验收）
grep -c "源领域" docs/ChemGraph-授粉报告.md        # ≥1
grep -c "数据结构共鸣" docs/ChemGraph-授粉报告.md   # ≥1
grep -c "难度 × 收益" docs/ChemGraph-授粉报告.md    # ≥1

# 2. 授粉引用到真实源码文件
grep -c "execution/base.py" docs/ChemGraph-授粉报告.md      # ≥2
grep -c "memory/store.py" docs/ChemGraph-授粉报告.md        # ≥2
grep -c "multi_agent" docs/ChemGraph-授粉报告.md            # ≥1

# 3. 不碰主流程（本报告只落 docs，无代码改动）
git diff --stat -- NEKO apiserver | wc -l                   # 0
```

---

*授权：Apache-2.0 → 主仓 AGPL v3 允许直接吞。本报告仅授粉，不拉源码进主仓（源码归档在 github_haul/fusion/chemgraph/）。*
