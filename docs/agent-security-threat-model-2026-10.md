# Agent 安全威胁模型清单（2026-10）

> 工单205 任务一 · 出单：沈遥 · 落地：砚 · 2026-10-07
> 来源：论文流水线 2026-10-07 轮（+1090 篇）的 cs.CR / cs.MA 安全论文 5 篇（均已在 corpus 核验）
> 结构：**威胁 → scratchpad 对应暴露面 → 缓解措施 → 来源论文 ID**

## 一、威胁清单

### 1. Prompt Injection 的"自蒸馏"防线

| 项 | 内容 |
|---|---|
| **威胁** | 外部内容（网页/文档/工具返回）中夹带的指令被 agent 当作任务执行；论文提出用模型自身对注入样本做自蒸馏以增强辨识 |
| **scratchpad 暴露面** | ① `mcpserver/` 中所有**读取外部内容**的工具：`academic` / `chembl` / `paper_miner` / `webapp-testing` / `headroom`（网页抓取）返回的文本直接进 LLM 上下文；② `apiserver/agentic_tool_loop` 的工具结果拼装路径；③ NEKO 转录文本经 `/api/lumo/*` 注入 |
| **缓解措施** | ① 工具返回值统一走**结构化包装**（`{status, data, source}`），外部文本进 `data` 且标注 `untrusted: true`；② 系统提示中把工具返回区与指令区显式分隔（现有 `agentic_loop_parts/context.py` 已是分隔点，可直接挂标记）；③ 对 `webapp-testing` / `headroom` 这类高噪声源，默认**只在被显式要求时**返回原文，否则返回摘要 |
| **来源** | 2610.06401（RAISED） |

### 2. 良性技能组合成恶意行为（Runaway Reaction）

| 项 | 内容 |
|---|---|
| **威胁** | 单个工具都无害，但**组合调用**（如"读文件 → 编码 → 外发"）可构成攻击链；防御需在**调用序列**层面而非单工具层面判断 |
| **scratchpad 暴露面** | ① `mcpserver` 的域分组注册（工单204 任务二）目前只有 `tier`（read-only / local-write / process-control / offensive），**没有"组合风险"维度**；② `apiserver/event_bus/workflow/chains.py` 的链编排天然是"多工具序列"的执行者；③ 工具画像（`mcpserver/telemetry.py`）已记录调用序列，是现成的检测数据源 |
| **缓解措施** | ① 域分组注册处补**风险等级**（low/medium/high，见 §二），并把 `local-write` + 网络出口的组合标为 high；② 链编排（chains）执行前做**组合预检**：序列中同时出现"文件写入类"与"网络出站类"时要求显式确认；③ 复用 telemetry 的调用序列做**离线回溯**（不阻塞在线路径） |
| **来源** | 2610.05943（Runaway Reaction） |

### 3. 任务级授权审计（Paired Replay）

| 项 | 内容 |
|---|---|
| **威胁** | 授权边界通常在**会话级**设定，但实际决策发生在**任务级**；缺任务级证据链时，事后无法回答"这一步是谁授权的" |
| **scratchpad 暴露面** | ① `agentserver/` 的会话管理只有实例/历史，**没有"每个任务的工具调用链"记录**；② `apiserver/` 的 `task_store` 记任务但不记工具序列；③ 确认门（`confirm_gate`）的 veto 决策目前只在事件总线内流转，**不落盘** |
| **缓解措施** | ① 任务结束时落一条**工具调用链摘要**（任务 ID → 工具序列 → 每步的 source/domain/风险等级）到 `agentserver` 数据目录，**只落盘不分析**（为审计留证据链）；② 摘要复用 telemetry 的 `tool_calls` 表，避免重复埋点；③ 确认门的 veto 结论同时写入该摘要（谁在何时拦下了什么） |
| **来源** | 2610.05840（Compromise Is Not Consequence） |

### 4. LLM 网关的跨租户干扰（Cooldown Landmines）

| 项 | 内容 |
|---|---|
| **威胁** | 共享网关的**退避/冷却策略**被一个租户的行为污染（如连续失败触发全局冷却），导致其他租户被"埋雷" |
| **scratchpad 暴露面** | ① `mcpserver/telemetry.py` 的**熔断器**：5 分钟窗失败率 > 50% → 熔断 10 分钟 —— 目前按 `tool` 粒度，若同一工具被多个 agent 调用，一个 agent 的失败会熔断其他 agent；② `apiserver/llm_service.py` 的模型调用重试；③ 内置 manifest 型工具已豁免熔断（good），但 external/adapter 未区分调用方 |
| **缓解措施** | ① 熔断键从 `tool` 扩展为 **`(tool, caller)`**（telemetry 已记录 caller，改动限于熔断器取键）；② 保留"全局熔断"作为二级策略，但阈值高于按调用方的阈值；③ 冷却状态目前是**进程内**（已知局限），多进程部署时需外置——列入待办而非本次 |
| **来源** | 2610.05089（Cooldown Landmines） |

### 5. 多 Agent 间接注入防护

| 项 | 内容 |
|---|---|
| **威胁** | Agent A 的输出成为 Agent B 的输入，注入可**跨 agent 传递并被放大**；单点防护不足以阻断链式传播 |
| **scratchpad 暴露面** | ① `mcpserver/` 的 53 个工具可由不同 agent 组合调用（工单204 任务二域分组后更明显：material 域产出 → radio 域消费）；② `workflow/chains.py` 的链式编排是**跨域数据流**的现成载体；③ NEKO 注入通道（`/api/lumo/speak|emotion`）是出站边界，目前只做 token 鉴权、**不做内容溯源** |
| **缓解措施** | ① 链编排的步骤间传参带**来源标记**（`origin_agent` / `origin_tool`），跨域传递时保留；② 出站注入（NEKO 通道）前做一次**来源校验**：仅允许来自受信 agent 的内容；③ 高风险域（offensive tier）的输出**不得**直接成为其他 agent 的指令输入 |
| **来源** | 2610.05640（Can CaMeLs Talk?） |

## 二、风险等级注解（配合 §一.2）

在工单204 任务二落地的**域分组注册接口**上补 `risk` 字段（只加注解不改行为）：

| 等级 | 判定 | 示例 |
|---|---|---|
| `low` | 只读、无外部副作用 | `parse_glycan`、`to_tree`、`linkk` |
| `medium` | 读外部/写本地、可逆 | `glytoucan_lookup`（出站查询）、`memclaw` 写入 |
| `high` | **文件写入 / 命令执行 / 网络出站**，或组合后可构成攻击链 | `agent_decompile`、`browseskill` 类、`offensive` tier 全部 |

**兼容**：字段缺省不改变既有装配行为（与工单204 的 `classification` 同款口径——缺省 = 不限制）。

## 三、落地状态

| 项 | 状态 |
|---|---|
| 威胁模型文档 | ✅ 本文件（5 篇论文 ID 全含） |
| mcpserver 风险注解字段 | 见 `mcpserver/mcp_registry.py` 的 `RISK_*` 常量与 `get_service_risk()` |
| agentserver 工具调用链摘要 | 见 `agentserver/` 任务收尾落盘（只落不析） |

— 砚 · 工单205 任务一 · 威胁面按 scratchpad 实际暴露面逐条对齐（非泛泛而谈）
