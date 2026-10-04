# 升级项目组 3-3：Agent/安全线（A28-A29/S17-S22）

> 生成：2026-08-31 · 实验田维护者 · 第三批（全量一行核心筛选）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可丢给执行 AI

---

# A28 Memory Is Communication

> 来源分组：group3-agent安全（第三批）

【SPEC】NEKO 记忆系统评估记忆-信号边界框架：有界 Agent 信息预算最优分配。验收=评估报告 + 原型。
【工单】①读 digest-g1-1 2608.17053 条目 ②分析记忆-信号边界 ③设计信息预算分配 ④原型。
【提示词】你是记忆系统 AI。读 digest-g1-1-2026-08-30.md 中 2608.17053（Memory Is Communication：记忆-信号边界框架，有界 Agent 信息预算最优分配），评估对 NEKO 记忆系统的价值：信息预算在记忆/通信间分配。输出方案 + 最小原型（预算分配模拟）。验收：协作任务模拟下信息预算分配提升任务成功率 ≥10%。推 trae/agent-a28 分支。

---

# A29 StateMem 状态追踪记忆

> 来源分组：group3-agent安全（第三批）

【SPEC】NEKO 增加状态追踪记忆：当前状态准确率提升 1.6-1.8×。验收=模块 + 测试。
【工单】①读 digest-g1-1 2608.19652 条目 ②设计状态追踪 ③实现 ④评估。
【提示词】你是状态记忆 AI。读 digest-g1-1-2026-08-30.md 中 2608.19652（StateMem Agent Tracking：状态追踪记忆系统基准，StateMem 当前状态准确率提升 1.6-1.8×），为 NEKO 实现状态追踪记忆：显式维护任务/环境状态，支持状态查询与回溯。输出模块 + 测试（多步任务状态准确率对比）。验收：状态准确率较基线提升 ≥50%。推 trae/agent-a29 分支。

---

# S17 Wrong-Physics 后门

> 来源分组：group3-agent安全（第三批）

【SPEC】安全评测增加 Wrong-Physics 后门：神经 PDE 算子错误物理后门，标签一致检测不出。验收=基准 + 检测方案。
【工单】①读 digest-g1-2 2608.20439 条目 ②复现后门 ③设计检测 ④出基准。
【提示词】你是 AI4Science 安全 AI。读 digest-g1-2-2026-08-30.md 中 2608.20439v1（Wrong-Physics Backdoor：神经 PDE 算子错误物理后门，标签一致性不足以检测），为 rf_brain/陆墨的物理模型建立后门基准：构造错误物理后门样本 + 检测方法（物理一致性校验）。输出 docs/wrong-physics-backdoor-基准.md + 检测原型。验收：含后门构造 + ≥2 种检测方法。推 trae/agent-s17 分支。

---

# S18 LVQMark 时序水印

> 来源分组：group3-agent安全（第三批）

【SPEC】rf_brain 增加时序水印：频谱/传感数据鲁棒水印，编辑攻击下稳定检测。验收=模块 + 测试。
【工单】①读 digest-g1-1 2608.19727 条目 ②设计时序水印 ③实现 ④鲁棒性测试。
【提示词】你是数据水印 AI。读 digest-g1-1-2026-08-30.md 中 2608.19727（LVQMark Time Series Watermark：局部 token 化生成模型+鲁棒重编码，时序水印编辑攻击下稳定检测），为 rf_brain 频谱数据实现鲁棒水印：嵌入不可见水印 + 编辑/截断攻击下可检测。输出 mcpserver/rf_brain/ts_watermark.py + 测试。验收：编辑攻击后水印检出率 ≥80%，对数据质量影响 ≤5%。推 trae/agent-s18 分支。

---

# S19 Groundhog MoE 位翻转

> 来源分组：group3-agent安全（第三批）

【SPEC】安全评测增加 MoE 可用性攻击面：翻转 4 个专家比特输出膨胀 5912%。验收=攻击面分析报告。
【工单】①读 digest-g2-4 2608.25276 条目 ②分析位翻转攻击 ③出攻击面报告。
【提示词】你是 MoE 安全 AI。读 digest-g2-4-2026-08-30.md 中 2608.25276（Groundhog Bit-Flip Attack：翻转 MoE 路由层不到 4 个专家比特使输出膨胀 5912%），分析 MoE 路由层位翻转攻击对本地部署 LLM/NEKO 的威胁面。输出 docs/moe-bitflip-攻击面.md：攻击原理 + 防御建议。验收：含攻击链拆解 + ≥3 条防御。推 trae/agent-s19 分支。

---

# S20 Semantic Overlays 提示注入防御

> 来源分组：group3-agent安全（第三批）

【SPEC】NEKO 增加 Semantic Overlays 提示注入防御：token 标注层缓解注入。验收=方案 + 原型。
【工单】①读 digest-g1-3 2608.23873 条目 ②设计标注层 ③原型 ④评估。
【提示词】你是注入防御 AI。读 digest-g1-3-2026-08-30.md 中 2608.23873v1（Semantic Overlays: Mitigating Prompt Injection with Annotated Tokens），为 NEKO 实现 token 标注层防御：输入 token 标注来源/信任级别，注入内容降权。输出方案 + 原型（标注过滤管线）。验收：注入攻击成功率下降 ≥50%，正常指令通过率 ≥95%。推 trae/agent-s20 分支。

---

# S21 Trace Integrity 数据 Agent 审计

> 来源分组：group3-agent安全（第三批）

【SPEC】Agent 审计增加 Trace Integrity：答案准确≠可靠，LLM 数据 Agent 审计。验收=评估报告。
【工单】①读 digest-g1-4 2608.26036 条目 ②分析审计需求 ③设计审计框架 ④出报告。
【提示词】你是数据审计 AI。读 digest-g1-4-2026-08-30.md 中 2608.26036（Trace Integrity for LLM Data Agents: A Vision for Auditing），为 NEKO 数据 Agent 设计审计框架：追踪数据来源/转换/使用痕迹，评估可靠性。输出 docs/agent-trace-integrity-方案.md。验收：含审计事件模型 + 追踪流程。推 trae/agent-s21 分支。

---

# S22 Capacity Overflow MoE 后门

> 来源分组：group3-agent安全（第三批）

【SPEC】安全评测增加批量依赖后门分析：小批量审计安全/大批量激活 87%。验收=分析报告。
【工单】①读 digest-g2-4 2608.25371 条目 ②分析批量依赖后门 ③出报告。
【提示词】你是供应链安全 AI。读 digest-g2-4-2026-08-30.md 中 2608.25371v1（Capacity Overflow Vision MoE Backdoor：批量依赖执行特性构成供应链后门攻击面，小批量审计安全/大批量激活，76-87% 激活成功率），分析批量依赖后门对模型供应链审计的启示。输出 docs/capacity-overflow-backdoor-分析.md。验收：含攻击机制 + 审计建议。推 trae/agent-s22 分支。

---
