# multica 多 agent 任务分配授粉报告 · D-02

> 授粉对象：multica-ai/multica —— 多 agent 任务分配/调度工作台
> 对照基准：BATCH-WORKORDERS-2026-08-23-ALLIN.md（四方向批次）+ BATCH-WORKORDERS-3AGENT.md（三分发批次）
> 日期：2026-08-23 · 授粉人：实验田维护者（D 组分身）

---

## 0. 仓库画像与许可风险（必读）

- **形态**：monorepo。前端 Next.js 16 + Electron + Expo；**后端 Go**（Chi router、sqlc、gorilla/websocket）；PostgreSQL 17；agent 执行靠本地 daemon 驱动 23 种 agent CLI（Claude Code / Codex / Cursor / Hermes / Trae CLI / Kimi 等，不内置模型）。
- **一句话定位**：把 agent 当同事 —— 分配 issue、自主认领、报告进度、提出阻塞、交回审查。工作台（board）模型。
- **许可（重要）**：**Multica License = Apache-2.0 全文 + Part I 附加条件**（商业托管限制：不得用其源码向第三方提供托管服务/嵌入商业产品；品牌使用限制）。属「受限 Apache」。任务描述中「商业托管限制→NC 分仓」的判断成立。
- **授粉纪律**：本报告只提炼**思路与机制**，不复制任何代码；未来若需借鉴其 Go 调度器实现（db-backed lease、single-winner claim），必须走独立分仓（NC 分支/分仓）或逐文件评估，不得整段搬运。Apache-2.0 的专利授权与附加条件冲突面也需法务再核 —— **思路无传染，代码有传染**。
- 备注：任务描述称「Go 写」——准确说法是**后端调度/服务层为 Go**，前端为 TS monorepo。调度核心（scheduler/）确为 Go。

---

## 1. 分配策略清单（≥5 条）

### S1. Issue 即工作单元 + 双触发源（assign / status）
- 工作载体是 issue（不是 prompt、不是消息）。agent 是 assignee，生命周期：`backlog → active → in_review → done`。
- **两个触发源**语义分离：`assign`（创建 issue / 改 assignee → 静默停 backlog）；`status`（backlog → active 提升 → 真正开跑）。
- 配套守卫：**自循环抑制**（agent 提升自己的工单不重触发自己正在跑的任务）、**重复 enqueue 抑制**（同 target 已有非终态任务时新触发 coalesce 掉，不重复派发）。
- 对应我们：工单清单 ≈ issue 池，「启动口令」≈ status 触发。但我们缺「改 assignee / 提升状态」这种**无歧义触发语义**，全靠人工读口令。

### S2. Squad 路由：leader 负责路由，成员负责执行
- squad = agent + 人组成的团队；squad 上的工作由 **leader agent 统一路由/执行**（squad leader agent 是实际 runner）。
- 路由责任收敛到单一 leader，避免「多 agent 抢活 / 无人认领」两难。
- 对应我们：D/E/F/G 四组目前靠清单静态分组，无 leader 角色、无动态路由。可引入「组长工单」（组 leader 负责拆解+验收汇总）。

### S3. DB-backed 分布式租约调度（JobSpec 参数化策略）
调度器用 `sys_cron_executions` 表同时充当**分布式锁 + 审计日志**，每个 JobSpec 显式声明全部时序策略：
- **单赢家 claim**：唯一键 `(job_name, scope, plan_time)`，多实例并发 tick 只有 1 个赢家，其余 no-op —— 天然防重复执行。
- **Cadence + ScheduleDelay**：计划桶大小 + 延迟窗口（如 12:00 的计划 12:05 才可认领），保证数据就绪再跑。
- **CatchUpMode 二选一**：`latest_only`（只补最近一期，handler 自带水位线）或 `every_plan`（逐期补，配 CatchUpWindow + MaxPlansPerTick 上限）。
- **租约三件套**：`RunTimeout < StaleTimeout`、`HeartbeatInterval`（心跳续租）、`AllowStaleReentry`（过期租约可被他人**窃取**；非幂等任务则置 FAILED 需人工修复）。
- **重试策略**：`MaxAttempts` + `RetryBackoff[i]`（第 i+2 次尝试前的退避，逐级可配）。
- **PlansForScope 钩子**：非均匀调度（任意 cron 表达式）时替换 Cadence 网格，仍复用租约/重试语义。
- 对应我们：授粉/写码工单目前无超时、无重试退避、无「谁认领」语义 —— 这是**最大的一块空白**。

### S4. Admission 词表（ReasonCode）：拒绝也要有可机读语义
- 成功路径：`queued / coalesced / deferred`；拒绝路径：`invocation_not_allowed / target_unavailable / runtime_offline / runtime_unusable / agent_runtime_required / attribution_blocked / already_active / self_trigger_suppressed`。
- 铁律：**代码在决策源头生成，绝不从错误字符串反推**；语义稳定、可本地化、不泄露隐私信息。
- 最精妙的一对：`runtime_offline`（机器离线 → **等待能解决**，任务排队）vs `runtime_unusable`（CLI 不可执行 → **等待无意义**，需人修机器）。阻塞被分类成「可等」与「不可等」。
- 对应我们：「阻塞（缺数据/许可/硬件）不硬做，写清原因返回」—— 已有雏形，但原因是自由文本。规则化后应输出稳定 reason code。

### S5. 并发上限 + 队列认领 + 空认领快路径
- 每 agent 有 `max_concurrent_tasks`（默认 6，合法域 1–50，启动时校验）。
- daemon 轮询**认领（claim）**任务队列；`EmptyClaimCache` 缓存「本 runtime 无排队任务」以省掉稳态下的 DB 扫描；`ReclaimCheck` 调度「何时可能有过期派发任务」的回收检查。
- 对应我们：Trae / Hermes 分身目前没有并发上限概念，第三批 4 组并行时可能单 agent 过载。

### S6. 失败处理：自动重试 + 幂等键 + 去重守卫
- 失败 run 自动重试（auto-retry clone **继承幂等键**）；delegated failure recovery；`retry_deferred` 延迟重试；重复 pending task 抑制。
- issueguard 去重门：**标题规范化 + active 状态查重**，默认禁止创建 active 重复 issue，`allow_duplicate=true` 才放行。
- 对应我们：「与既有工单边界」表是人工防重复；规则化后应变成**创建工单前的自动查重门**。

### S7. 审查门（Review Gate）+ 全量执行日志
- agent 完成后 issue 移入 `in_review`，**不进 main** —— "nothing ships without a human saying so"。人审通过才落库/合入。
- 每次 run 有 timestamped 执行日志（工具调用/命令/错误可回放）+ token 用量（per agent per issue）+ **归因**（attribution：fail-closed 下解析不到负责人直接拒跑）。
- 对应我们：「实验田维护者出 SPEC + review」已是人工审查门；缺的是**执行轨迹记录**（谁跑了什么命令、花了多少 token）与**归因字段**。

### S8. Autopilot 定时触发（cron 化例行工作）+ 配额
- cron 触发 standups / audits / reports；执行源四类：`schedule / manual / webhook / api`；60s 去重窗口 + 幂等键；workspace 级周期配额（used / reserved / limit / resetAt）。
- 对应我们：授粉报告的「上游更新复查」「知识库巡检」这类例行工作适合 autopilot 化（cron 自动重跑 + 结果推频道）。

---

## 2. 对照：我们现拆分逻辑的强项与缺口

| 维度 | 现逻辑（BATCH-WORKORDERS） | multica 可补 |
|---|---|---|
| 触发 | 启动口令（人工读清单） | assign/status 双触发语义 |
| 隔离 | 领域矩阵防重叠（强） | 自动查重门（标题规范化） |
| 验收 | 可断言化验收（grep/pytest，强） | 执行日志回放 + token 计量 |
| 阻塞 | 自由文本「写清原因返回」 | 稳定 ReasonCode 分类 |
| 超时/重试 | 无 | RunTimeout/MaxAttempts/RetryBackoff |
| 并发 | 无上限 | max_concurrent_tasks |
| 审查 | 实验田维护者人工 review（有，但无状态位） | in_review 状态 + 归因字段 |
| 例行重跑 | 无 | Autopilot cron + 配额 |
| 认领 | 固定分组（组长缺位） | Squad leader 路由 |
| 幂等 | 无 | 幂等键 + 去重抑制 |

---

## 3. 拆分规则 v2（规则化建议）

> 把 multica 策略落地为**我们工单拆分可直接使用的规则**。v1（现状）是「领域聚组 + 字段模板 + 铁律」；v2 增加**时序语义、阻塞分类、去重门、审查门**四组规则。规则编号 R1–R10。

### R1. 工单卡字段模板 v2（在 v1 基础上扩展）
每张工单必须含：
```
- 层: Skill / MCP / 授粉 / 耦合 / 施工        （已有）
- 输入: 上游仓库 + 许可标注                     （已有）
- 动作: 动词开头，明确产出物                     （已有）
- 验收: 可自动断言的验收（grep/pytest/命令退出码） （已有，强化为强制）
- 硬约束: 只读/不碰目录/不写码                   （已有）
- 归属: assignee + reviewer（新增）
- 时限: run_timeout + 重试上限（新增）
- 依赖: 前置工单 or 无（新增）
- 幂等键: 唯一工单标识，重跑不重复建（新增）
```

### R2. 双触发语义（对口令机制做规则化）
- 拆单 = `assign`：工单创建即入 **backlog**（静默，不跑）。
- 启动 = `status`：口令「开始执行」= backlog→active **提升**，才真正开跑。
- 「只跑 D-xx」= 按工单号提升，单张开跑。
- 规则：**任何执行都必须由一次显式 status 提升触发**；assign 阶段只做查重/边界校验，不得隐式开跑。

### R3. 阻塞分级（ReasonCode 化）
阻塞原因不再自由文本，固定五类：
- `BLOCK_WAIT_EXTERNAL`：缺硬件/缺真机/等上游 —— **保留排队**，任务不取消。
- `BLOCK_WAIT_PERMISSION`：缺许可/需法务核 —— 排队 + 标记，定期复查。
- `BLOCK_DEAD_END`：方案不可行/上游归档废弃 —— **立即返回**，取消工单，原因一句话。
- `BLOCK_ENV`：工具链不可用（无 Docker/无 GPU）—— 等价 multica `runtime_unusable`，等待无意义，需人先修环境。
- `BLOCK_ATTRIBUTION`：找不到负责人/无法归因 —— fail-closed，拒跑。
- 规则：验收卡住时先打分类码，再写细节；**可等（前两类）与不可等（后三类）分开管理**。

### R4. 重试与超时（JobSpec 落地）
- 每张工单显式声明 `run_timeout`（如授粉 2h / 写码 6h）与 `max_attempts`（默认 3）。
- 重试退避固定档：`1h → 4h → 24h`；超过 max_attempts 置 FAILED，转人工。
- **非幂等动作（写码 commit、推分支）禁止自动重入**，必须人工确认后再试（对应 `AllowStaleReentry=false`）。

### R5. 去重门（创建工单前自动查重）
- 标题规范化（小写 + 折叠空白）后与**全部批次**（含既往 BATCH-WORKORDERS 与 docs/ 既有报告）做 active 查重。
- 命中即拒建，除非显式 `allow_duplicate=true`（如「对照报告」类需重复对比同一上游时）。
- 第三批「施工范围矩阵」的防重叠铁律，从此由人工检查升级为**创建时强制门**。

### R6. 并发上限
- 每 agent（Trae / 各 Hermes 分身）同时 in-flight 工单 ≤ 3（默认），超出排队。
- 批次级总并发 ≤ 组内 agent 数 × 3；单 agent 过载时后建工单自动降级为 backlog。

### R7. 审查门（Review Gate）
- agent 完成后工单进入 **in_review** 状态，不直接 commit 推分支。
- 实验田维护者 review 通过 → `done` + 推分支；不通过 → 退回 `active` 附原因（对应 multica "nothing ships without a human saying so"）。

### R8. 归因与执行日志
- 每张工单带 `assignee + reviewer + originator` 字段；无法归因的工单拒绝派发。
- 执行中记录轨迹（关键命令 + 结果 + 时间戳），验收时一并回报 —— 不用完整回放，但至少保留「命令→退出码」链供回溯。

### R9. 周期复查 autopilot 化
- 授粉类工单（D 组/G 组为主）自动登记 30 天复查 cron：上游版本变更/归档状态变化 → 推结果到频道，人工决定是否重授粉。
- 例行巡检（知识库、上游许可变更）同机制；配额按周。

### R10. 组长路由（Squad leader）
- 每组（D/E/F/G）指定组长工单：组长负责 ① 组内工单查重预检 ② 验收汇总 ③ 阻塞分类初判。
- 跨组争议工单（如「授粉产出需写码验证」）由组长上报总协调，不自行越界 —— 保持领域隔离铁律。

---

## 4. 落地建议优先级

- **P0（本周，低代价高收益）**：R2 双触发语义 + R3 阻塞分级 —— 纯流程规则，不改工具。
- **P1（下周）**：R5 去重门 + R7 审查门 —— 拆单脚本里加 10 行查重即可。
- **P2（视需求）**：R4 超时/重试、R6 并发上限、R9 cron 复查 —— 需要跑批/定时基础设施，评估后决定是否自建（借鉴思路，不搬代码）。

---

## 5. 一句话结论

multica 最大的可授粉点不是「多 agent」，而是**把调度时序（超时/重试/认领/去重/审查）从人脑里搬进显式参数**——我们缺的从来不是拆单模板，是工单的「运行语义」。

*—— 实验田维护者 · 拆单的下一步不是拆得更细，是给每张工单装上时钟、闸门和退避。🐾*

---

> **【附录：另一会话同题报告原文】** 以下为同名授粉报告的另一版本（2026-08-23 并行会话产出），与上文互为补充，合并时保留以防资料丢失。

# multica 任务分配 · 授粉报告 + 拆分规则 v2（D-02）

> 智能体 D · 2026-08-23 · 只读调研，未写一行业务码
> 上游：[multica-ai/multica](https://github.com/multica-ai/multica)（15.4k★@2026-01 开源，
> Go 单二进制 + Next.js + PostgreSQL 398 个迁移；"把 issue 像派给同事一样派给 AI agent"）
> 调研方式：浅克隆至仓外临时目录通读源码；对照本仓 `BATCH-WORKORDERS-2026-08-22.md` 拆分逻辑。
> 行号引用相对 multica 仓库根（HEAD bedad9e）。

---

## 〇、许可与合仓结论（硬约束前置）

`LICENSE` = "Multica License"（Apache-2.0 全文 + Part I 附加条件）：
(a) 用源码向**组织外第三方**提供托管/嵌入服务需商业许可（组织内部使用免费）；
(b) 不得移除 UI 品牌/版权；(c) 只用后端/daemon/CLI 时须保留 NOTICE 归属。

**结论：按工单硬约束，multica 代码不进主仓（NC 分仓处理），本报告只授粉分配机制。**
补充事实：其 `SELF_HOSTING.md` 提供 Docker Compose/Helm 自托管（组织内免费，
云能力默认关闭），若未来要独立部署一个"任务分配台"，走独立部署不动主仓即可。

## 一、multica 任务分配机制五件套（事实底座）

| 机制 | 事实 | 源码锚点 |
| --- | --- | --- |
| 派发谓词 | `WillEnqueueRun`：assign（改 assignee）或 status（backlog→活跃）才触发；**backlog 是停车场**，分进去不启动；done/cancelled 重派会立即触发 | `server/internal/service/issue_trigger.go` |
| 唯一性锁 | 每 (issue, agent) 只允许一个 pending 任务（部分唯一索引 `idx_one_pending_task_per_issue_agent_v2`） | 同上 + 迁移 |
| squad 路由 | assignee=squad 时派给 **leader agent**；leader 系统提示注入三段：Squad Operating Protocol（只协调不干活，@mention 派活）+ Roster（含各成员**已绑定技能名**）+ 自定义路由规则 | `server/internal/handler/squad_briefing.go` |
| agent 档案 | `agent` 表：description/instructions/model/max_concurrent_tasks/permission_mode…；**没有历史成功率字段**——"能力画像"=描述+指令+技能名，供人或 leader 阅读判断 | `server/pkg/db/generated/models.go:24` |
| 队列调度 | `agent_task_queue`：deferred→queued→dispatched→running→终态；认领排序 `priority DESC, created_at ASC` | `server/pkg/db/queries/agent.sql:723` |
| 三层并发 | agent 级 `max_concurrent_tasks`（默认 6，1–50）+ (issue,agent) 串行（同 agent 同 issue 不并行，异 agent 可并行同 issue）+ daemon 信号量（默认 20）+ 本地目录锁 | `server/internal/agentconfig/concurrency.go`、`service/task.go:3076`、`daemon/daemon.go:4663` |
| 任务切片 | **平台不自动拆**；agent 自己建 sub-issue（`parent_issue_id` + `stage` 分组），子 issue status=todo 即触发执行、backlog 停车 | `daemon/execenv/runtime_config_sections.go:726` |
| 阶段屏障 | 兄弟子 issue 全终态（无 stage）或最低未完成 stage 全终态（frontier closure）→ 父被唤醒（系统评论+dispatch），**服务端只检测屏障，推进由 agent 决定** | `server/internal/handler/issue_child_done.go` |
| 汇报通道 | **评论是唯一交付通道**（终端输出不算交付）；task 逐条 transcript（task_message 表）实时回放；状态 agent 自管：in_progress/in_review(人审门)/blocked | `runtime_config_sections.go:688`、`docs/tasks.mdx` |
| 技能复利 | skill（SKILL.md）多对多挂 agent；claim 时打包写入工作目录各 CLI 技能目录（hash 校验）；brief 只放技能名索引省 token；**无自动蒸馏**——复利=一处维护多 agent 复用+可从生态导入 | `service/task.go:5996`、`builtin_skills/`（9 个平台内置技能） |
| 可靠性 | dispatched 5 分钟 stale 回收重投；queued 2 小时未认领过期；瞬态故障自动重试 2 次/网络类 3 次 | `ReclaimStaleDispatchedTask`、`MULTICA_TASK_QUEUED_TTL` |

## 二、分配策略清单（从 multica 提炼，≥5 条）

| # | 策略 | multica 出处 | 一句话 |
| --- | --- | --- | --- |
| S1 | **指派即触发，backlog 停车** | `issue_trigger.go` | 只有 assign/状态提升才启动；塞 backlog = 显式"暂不做" |
| S2 | **squad leader 路由（LLM 派单）** | `squad_briefing.go` | leader 只协调不干活；按成员技能名+自定义规则 @mention 精确派活，派完即停，每回合记录决策 |
| S3 | **(任务,执行者) 唯一 pending 锁** | 部分唯一索引 v2 | 同一任务对同一执行者不会重复派发；不同执行者可并行同一任务 |
| S4 | **三层并发预算** | agent/机器/目录锁 | agent 级上限（默认6）+ 执行机信号量（默认20）+ 同目录互斥，逐层限流 |
| S5 | **优先级+FIFO 派发序** | `ClaimAgentTask` | priority DESC → created_at ASC → id ASC，urgent=4…none=0 |
| S6 | **阶段屏障推进** | `issue_child_done.go` | 同 stage 子任务全部终态才唤醒父；推进决策留给 agent，服务端只做屏障检测 |
| S7 | **stale 回收 + 分级自动重试** | daemon/retry | 5min 回收重投、2h 过期、瞬态 2 次/网络 3 次，耗尽才升级给人（inbox action_required） |
| S8 | **技能名索引进 brief**（省 token 的能力匹配） | `LoadAgentSkillBundles` | 派单提示只放技能名清单，SKILL.md 全文落工作目录——leader 按能力而非猜测派活 |

## 三、对照 BATCH-WORKORDERS 拆分逻辑（现状差距）

现有 `BATCH-WORKORDERS-2026-08-22.md`：8 字段工单（层/目标/输入/动作/验收/
硬约束/委托对象/启动条件）+ WO/HW 分组 + 尾部"分发说明表/执行顺序/启动口令"，
第二批起按领域拆给智能体 A/B/C（trae/agent-* 分支），第三批 D/E/F/G 带
"施工范围矩阵（防重复）"。**这是人肉版的 S1（启动条件=依赖）+ S5（执行顺序表）**，
与 multica 的差距：

| 维度 | 现状（人肉） | multica 机制 | 差距 |
| --- | --- | --- | --- |
| 触发 | 实验田维护者发口令启动 | assign 即触发、backlog 停车 | 无机器可读触发谓词 |
| 去重 | "施工范围矩阵"人工防重复 | (issue,agent) 唯一 pending 索引 | 无锁，靠自觉 |
| 并发 | 无上限（8-23 那批 A~G 七个并行） | agent 级 6 + 机器级 20 | 无预算，共享工作树已实际发生分支竞态（本单 D-01 提交曾被并行 agent 切分支劫持，见过程记录） |
| 依赖 | "启动条件: WO-0X 后"线性链 | deps/stage 屏障 + frontier closure | 只支持全序，不支持 DAG/阶段分组 |
| 汇报 | commit message + 报数（"完成一个报一个"） | 评论=唯一交付通道 + transcript 回放 | 无结构化回报契约 |
| 失败 | "阻塞不硬做写清原因返回" | stale 回收/分级重试/升级 inbox | 无自动重试与升级路径 |
| 验收 | grep/assert 写在工单里（好！） | acceptance_criteria 字段 | 验收已有，但结果不回写状态 |

值得说明：**工单的"验收(grep/assert)"字段已经优于 multica**（multica 的
acceptance_criteria 只是文本）；差距纯在执行侧的机器化。

## 四、拆分规则 v2（规则化拆分建议）

在 8 字段基础上扩展为 13 字段，全部机器可校验（YAML 示例随后）：

| 新增字段 | 取值 | 对应机制 |
| --- | --- | --- |
| `id` / `parent` | 工单号 / 父工单号 | sub-issue 结构（S6） |
| `stage` | 整数阶段号（同 stage 全终态才唤醒父） | 阶段屏障 frontier closure |
| `deps` | 工单 id 列表（DAG 边） | orca `tasks.deps` 同构（D-01 建议 1） |
| `assignee` | 智能体标识（agent-b/agent-d/…） | assignee_type=agent |
| `priority` | urgent/high/medium/low/none → 4..0 | S5 派发序 |
| `max_concurrent`（按 agent 汇总） | 默认 ≤3 单/agent，全队 ≤7 | S4 三层并发（本仓共享工作树，更须限） |
| `retry` | {瞬态:2, 网络:3, 熔断:3 连败} | S7 + orca 熔断 |
| `report_contract` | done 须含：路径清单+验收命令输出+commit hash | 评论=唯一交付通道 |

**v2 工单模板（YAML）：**

```yaml
id: WO-XX
parent: BATCH-2026-08-22          # 或父工单号
stage: 1                          # 同 stage 兄弟全终态 → 唤醒 parent
deps: [WO-01, WO-04]              # DAG：两者完成才 ready
assignee: agent-b                 # (id, assignee) 唯一 pending
priority: high                    # urgent=4 … none=0
层: mcp / docs / skill / …
目标: …
输入: <repo url> + <本地路径>
动作: [1. …, 2. …]
验收:                             # 全部可执行
  - "pytest tests/test_x.py"
  - "grep -r 'MODEL_INTERFACE' mcpserver/academic | wc -l"   # ≥4
硬约束: [不碰 NEKO/apiserver 主流程, …]
retry: {transient: 2, network: 3, circuit_break: 3}
report_contract:                   # done 回报必含
  fields: [paths, acceptance_output, commit_hash, blockers]
停车场: false                      # true = backlog，分派但不启动
```

**拆分规则 v2 十条（执行细则）：**
1. 每工单必须可独立验收（grep/pytest/ls 任一可跑），不可验收的拆成"调研文档单"并降 priority。
2. 同 agent 在途工单 ≤3（并发预算）；超出的进停车场（`停车场: true`），完成一单自动出队下一单。
3. 触发谓词固定两种：assign 变更、backlog→todo 状态提升；其余变更不触发。
4. (工单, agent) 唯一 pending——重派前必须先结算旧单（done/failed/cancelled）。
5. 依赖只用 deps + stage 表达；"启动条件"字段升级为 deps 列表，禁止自然语言依赖。
6. stage 屏障由台账检测（同 stage 全终态→@唤醒父单 assignee），推进与否由父单 agent 决定。
7. 失败分级：瞬态重试 2 次 → 网络类 3 次 → 3 连败熔断标 `circuit_broken` 并升级人工（inbox/action_required 语义）。
8. 交付只认结构化回报（report_contract），commit message 只是佐证；"完成一个报一个"落为 `task.done` 消息（衔接 D-01 建议 2 的消息枚举）。
9. 每单开工先登记台账（对应 multica `manage-state.sh --action add-finite`：不登记的 agent 会被误判 idle）。
10. 验收回写：验收命令通过 → done；失败 → blocked + 重试计数 +1；实验田维护者终审 → gate.resolved（对应 multica 的 in_review 人审门：done 基本留给人类）。

## 五、落地路径建议（不写码，仅指路）

- 台账载体：D-01 建议的 Run/Task 状态库直接复用（tasks 表加 `stage/priority/
  parking` 三列即等价 multica 队列）；或最小起步——`lumo-task-tracker/` 目前是
  mock 演示壳（`js/api.js:1-23` 留了"替换 fetchTasks 即接真实后端"的桩），
  把工单 YAML 目录作为其第一个真实数据源即可闭环展示。
- leader 路由：陆墨已有 agent_directory（干员通讯录）+ 多次 agent_relay 协作
  提示（`apiserver/routes/chat.py:398-406`），给它注入 multica 式三段
  briefing（协议/Roster 技能名索引/自定义规则）即可升级为 squad leader。

## 附：信息来源

源码通读（临时克隆 `C:\Users\ASUS\AppData\Local\Temp\agentd-haul\multica` @
bedad9e）；[multica.ai](https://www.multica.ai/)；
[Agent Team 功能请求 #1173](https://github.com/multica-ai/multica/issues/1173)。
