# multica 多 agent 任务分配授粉报告 · D-02

> 授粉对象：multica-ai/multica —— 多 agent 任务分配/调度工作台
> 对照基准：BATCH-WORKORDERS-2026-08-23-ALLIN.md（四方向批次）+ BATCH-WORKORDERS-3AGENT.md（三分发批次）
> 日期：2026-08-23 · 授粉人：沈遥（D 组分身）

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
- 对应我们：「沈遥出 SPEC + review」已是人工审查门；缺的是**执行轨迹记录**（谁跑了什么命令、花了多少 token）与**归因字段**。

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
| 审查 | 沈遥人工 review（有，但无状态位） | in_review 状态 + 归因字段 |
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
- 沈遥 review 通过 → `done` + 推分支；不通过 → 退回 `active` 附原因（对应 multica "nothing ships without a human saying so"）。

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

*—— 沈遥 · 拆单的下一步不是拆得更细，是给每张工单装上时钟、闸门和退避。🐾*
