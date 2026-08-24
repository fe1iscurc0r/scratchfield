# 多 Agent 协作对照报告：AgentTeams × ccg-workflow × 三元融合

> 工单：D-03 ｜ 类型：授粉/调研（只读，不写码）
> 日期：2026-08-23
> 基线：`scratchpad/INTEGRATION_PLAN.md`（36 项融合计划）+ `docs/NEKO-Lumo-Fusion-Blueprint-v1.1.md` + `docs/Fusion-Topology-Audit-v1.md`
> 目标系统：三元融合 —— **Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互**（单一灵魂：陆墨=大脑，NEKO=身体）
> 调研对象：
> - **AgentTeams**（agentscope-ai/AgentTeams，Apache-2.0）—— 人在回路协作协议、Manager-Workers 运行时平台
> - **ccg-workflow**（fengshao1227/ccg-workflow，MIT）—— Claude 主控 + 多模型编排工作流引擎

---

## 一、三方速览

| 系统 | 定位 | 一句话 |
|------|------|--------|
| **AgentTeams** | 企业级多 Agent 协作运行时平台 | Manager 协调 Worker/Team，真人全程在 Matrix 房间可见、可干预、可审批；K8s 原生，多运行时（OpenClaw/QwenPaw/**Hermes**）共存 |
| **ccg-workflow** | Claude Code 的工作流引擎 | Claude 当主控，把专项工作分派给 Codex/Grok/Kimi/Antigravity 等外部模型（Go 二进制桥），阶段状态机 + 质量门 + 循环检测 |
| **三元融合（现状）** | 单机科研外骨骼 | 陆墨（scratchpad，NagaAgent AGPL fork）= 人格/记忆/知识/决策唯一源；NEKO（Apache-2.0）= Live2D/TTS/ASR/CUA 身体；Hermes = 决策层；HTTP 双向桥接 |

**直接相关发现**：AgentTeams 官方提供 `agentteams-hermes-worker`（Hermes 作为自治编码 Worker 容器）——Hermes 与 AgentTeams 是"互补而非竞争"关系（README 明说 *does not compete with other Agent runtimes*），三元融合可白嫖其 Hermes Worker 契约设计。

---

## 二、三方对照表（12 行）

| # | 维度 | AgentTeams | ccg-workflow | 三元融合（现状） |
|---|------|-----------|--------------|------------------|
| 1 | 定位/许可 | 多 Agent 协作运行时（Apache-2.0） | Claude 多模型编排引擎（MIT） | 单机科研伴侣（AGPL 主体 + NEKO Apache-2.0 vendor） |
| 2 | 架构模式 | Manager-Workers 三层（Manager→Team Leader→Worker）+ Human CRD | 单主控（Claude）+ 外部模型桥（Go wrapper）+ 子代理 | 决策（Hermes）/执行（scratchpad 陆墨）/交互（NEKO）三层 |
| 3 | 人在回路协议 | **Matrix 房间全程同屏**：真人看得到每步、随时插入；敏感操作（发布/删除/支付/生产变更）**必须显式人工审批门**；Human 分 Level 1-3 权限接入 | **HARD STOP 审批门**：规划完成后必须用户批准才进实施；另有 verify-security/quality/change/module 四道质量门 | 无显式审批门；靠单一灵魂原则 + token 鉴权；人工介入依赖沈遥/林楠人工值班 |
| 4 | 多模型/多运行时策略 | 异构 Worker 容器（OpenClaw 确定性 + QwenPaw + Hermes 自治编码），各干最擅长的 | **分阶段角色路由**：analyzer/architect/builder/debugger/reviewer/tester 角色 × frontend/backend 双模型并行；纯 CC 模式降级为 Agent Teams 子代理 | Hermes 决策层内多 provider 切换（DeepSeek/MiniMax 等）；无"异构 agent 并行执行同一任务"的编排 |
| 5 | 任务生命周期 | Task/Team CRD + TeamHarness，声明式 YAML（`agt apply`）；controller reconcile | `.ccg/tasks/{name}/task.json` 持久化状态机：research→ideation→planning→implementation→optimization→final，每阶段带 Gate | BATCH-WORKORDERS 扁平工单列表（2026-08-23 版本已分 3-agent）；无 phase/gate 状态机 |
| 6 | 上下文保持 | Worker **无状态**，状态全在 MinIO 对象存储；session 重置后用 task-history.json + spec/plan/progress 恢复 | 4 个 JS hook 每轮注入 `<ccg-state>` 面包屑；compaction 后 session-start 重注全量上下文；context.jsonl 策展给子代理 | 陆墨 session/记忆管线（RAG + persona）唯一副本；跨分身协作上下文靠会话传递 |
| 7 | 循环/卡死防护 | 无显式机制（靠人看见） | **LOOP DETECTION**：同 phase+nextAction 重复 3 轮 → 注入 BREAK-LOOP 协议（停止→根因→三选项→升级用户） | 无；NEKO 侧有 LRU 去重 + 时效校验，防的是事件风暴不是决策循环 |
| 8 | 凭据/安全隔离 | Higress AI 网关：Worker 只持 consumer token，真凭据留在网关；YOLO 模式不破安全规则 | wrapper 构造"影子 HOME"（只藏 .claude 配置，其余符号链接透传）；headless 审查恒定跳过权限门 | LUMO_PROXY_TOKEN / NEKO_EXEC_TOKEN 双 token + hmac.compare_digest + fail-safe 503；CUA 沙箱 allowlist + AST 预检 + 30s 超时 |
| 9 | 可观测性 | K8s controller + Project Workflow API（LangGraph 对齐视图，`interrupts: ["waiting for human decision"]` 可见）+ Dashboard + AgentLoop 集成 | hook 面包屑 + `ccg status`/`ccg doctor` 健康检查 + live SSE Web UI | NEKO→陆墨 6 类事件（user_input/asr/tts/user_action/error）+ 审计报告；无任务级工作流视图 |
| 10 | 知识/技能注入 | Nacos 技能注册表 + skills.sh（8 万+ 社区技能按需拉取）+ Worker.spec.skills 下发 | **skill-router 关键词路由**：用户消息命中关键词 → 自动注入 10 域 61+ 领域知识文件 | Hermes skills/（已有 200+ 技能）+ 陆墨 RAG 科研库；无"消息关键词→技能自动注入" |
| 11 | 团队/多人工协作 | Team Leader 自组织 + 多真人分级接入；Manager 只管顶层任务下发（解决单点瓶颈） | Agent Teams 子代理并行（同消息 spawn 才是真并行）；纯 CC 模式双 Agent 独立上下文交叉验证 | 沈遥+林楠双人组 = 神经系统（协议/接口/部署/安全兜底）；无双真人权限分级 |
| 12 | 部署形态 | 一条命令 `curl|bash`（嵌入式 controller：Higress+Tuwunel+MinIO+Element）/ Helm K8s | `npx ccg-workflow` 60 秒安装（Node 20+ + Claude Code CLI） | 单机多进程（apiserver :8000 + NEKO 三服务器 48911/48912/48915），Windows 本机 |

---

## 三、关键机制深读

### 3.1 AgentTeams —— 人在回路是"协议"不是"功能"

1. **审批门进任务定义**：use-cases 文档明确"发布/合并/生产变更仍须显式人工批准"，且"定义审批门并禁止未经确认的不可逆操作"——审批不是事后抽查，是任务 spec 的一部分。
2. **角色纪律**：Manager 只编排不干活（"should not use file or command tools to implement work already assigned to a Worker"）——决策与执行物理分离，与三元融合"单一灵魂"同构。
3. **无状态 Worker + 对象存储任务树**：`spec.md / plan.md / progress/YYYY-MM-DD.md / task-history.json` 全部落 MinIO；会话重置 2 天也能恢复任务，Worker 容器可随时替换——协作资产不活在聊天上下文里。
4. **Human CRD 三级权限**：Level 1 等同 Admin 全角色可聊；Level 2 限 Team 内；Level 3 限指定 Worker。真人接入是声明式资源，可审计。
5. **Hermes Worker 已是一等公民**：`hermes/` 目录含 Dockerfile + policy/config 树，Hermes 作为自治编码 Worker 与 OpenClaw/QwenPaw 同棚——证明 Hermes 可被容器化进协作拓扑。

### 3.2 ccg-workflow —— 多模型编排的"状态机 + 门 + 面包屑"

1. **Phase 状态机带 Gate**：每阶段有 Gate 检查（需求评分 ≥7、双模型已返回、用户已审批），状态持久化到 task.json；`workflow-state.js` 每轮注入 `<ccg-state>`（Task/Strategy/Phase/Gate/Next）——模型永不丢上下文，压缩后 session-start 重注。
2. **LOOP DETECTION + BREAK-LOOP 协议**：同 phase+nextAction 重复 3 轮即告警并给出 5 步破环协议（停止→根因→三选项→升级用户→不许重复同样动作）——这是三元融合最缺的"自反性"机制。
3. **双模型并行价值主张**："交叉验证的价值来自独立上下文 + 不同视角，而不是不同厂商"——纯 CC 模式用两个干净上下文的子代理也能拿到同样收益。对三元融合的启示：异构 provider 不是目的，**上下文隔离**才是。
4. **角色提示词 × 模型路由**：analyzer/architect/builder/reviewer 等 8 角色提示词按阶段加载到 frontend/backend 双模型，角色与厂商解耦、可热替换。
5. **subagent-context.js 用 PreToolUse `updatedInput` 改写**：spec 直接注入子代理 prompt（"出生即带 spec"），而非塞 additionalContext——比"上下文传递"更抗编排幻觉。

### 3.3 三元融合现状 —— 强在单一灵魂，弱在协作协议

- **强项**：决策/执行/交互三层职责清晰；单一事实源（NEKO 记忆关闭）；token 双鉴权 + CUA 沙箱收紧；融合五层分类法（MCP/Skill/参考/耦合/基础设施）已有成熟的授粉流水线（本报告即产物）。
- **弱项**：
  - 无任务级状态机：BATCH-WORKORDERS 是扁平工单，无 phase/gate/nextAction，跨分身协作"做到哪了"靠人脑；
  - 无审批门：NEKO CUA 执行端点已就位（M4），但"不可逆操作需人工确认"没有协议层表达；
  - 无循环检测：Hermes→NagaAgent→NEKO 的决策-执行环若卡死，没有 ccg 式 BREAK-LOOP 协议；
  - 无上下文落盘约定：分身间协作资产活在会话里，不像 AgentTeams 有 spec/plan/progress 任务树。

---

## 四、改进建议（针对三元融合，按性价比排序）

**建议 1【高】给工单系统加 phase/gate 状态机 + 面包屑（移植 ccg 核心）**
BATCH-WORKORDERS 改为 `.ccg/tasks/` 同款目录约定：`task.json{status, strategy, currentPhase, gate, nextAction}` + `spec.md` + `plan.md` + `progress/`。每轮协作回复开头带 `<state>` 面包屑；每阶段设 Gate（如"双分身已返回""沈遥已审批"）。落地成本：一个目录规范 + 工单模板改动，不写新引擎。

**建议 2【高】敏感操作审批门进任务定义（移植 AgentTeams）**
M4 已给 NEKO CUA 执行端点，但"发布/删除/生产变更需人工确认"未成协议。落地：scratchpad 工单模板加 `approval_gates: []` 字段；`neko_cua` 工具对不可逆 action（删除/写外部系统）先返回 `PENDING_APPROVAL`，等沈遥/林楠显式批准令牌再执行——复用现有 Bearer token 体系，不加新基建。

**建议 3【中】循环检测 + BREAK-LOOP 协议（移植 ccg workflow-state.js）**
在陆墨 agent 决策循环（agentic_tool_loop）加计数器：同一 tool+意图 3 轮无进展 → 注入破环指令（停止→根因→三选项→升级用户）。NEKO 侧已有 LRU 去重防事件风暴，缺的正是决策层自反性。落地：lumo_event 或 agentic_tool_loop 加约 50 行检查逻辑。

**建议 4【中】协作资产落盘"共享任务树"（移植 AgentTeams MinIO 模式）**
分身（沈遥/林楠）之间约定 `shared/tasks/{id}/` 目录：spec/plan/progress/result 全落盘，会话只留指针。效果 = AgentTeams 的"Worker 可替换"——任何分身掉线，换一个从任务树恢复即可，不丢上下文。

**建议 5【低】skill-router 关键词注入（移植 ccg 路由表）**
Hermes 已有 200+ skills，但按用户消息关键词自动注入领域知识未做。落地：Hermes hook（UserPromptSubmit 同款）或 NagaAgent 前端加一张 keyword→skill 路由表（RAG/安全/材料 等 10 域）。可减少 RAG 检索幻觉、降 token 消耗。

**建议 6【低】可观测性升级：任务级工作流视图**
参考 AgentTeams Project Workflow API 的 LangGraph 对齐视图（nodes/edges/interrupts 可见），给 BATCH-WORKORDERS 加"当前 phase + 阻塞点（waiting for human decision）"清单，供沈遥/林楠巡检。

---

## 五、一句话结论

AgentTeams 教"人怎么进来"（审批门 + 权限分级 + 全程可见），ccg-workflow 教"机怎么不迷路"（状态机 + 面包屑 + 循环检测），三元融合已有"单一灵魂"的正确骨架——缺的是一层薄薄的协作协议：**状态落地、门禁显式、循环可断**。

*—— 沈遥 · 决策要单一，协作要协议，循环要能断 🐾*
