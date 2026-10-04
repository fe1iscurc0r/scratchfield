# 升级项目组 3-4：工具链线（K17-K22）

> 生成：2026-08-31 · 实验田维护者 · 第三批（全量一行核心筛选）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可丢给执行 AI

---

# K17 Adaptive Reasoning Budget

> 来源分组：group4-工具链（第三批）

【SPEC】NEKO 增加自适应推理预算：模型自选推理时长（NoThink/Short/Long），省 token 不掉精度。验收=模块 + 测试。
【工单】①读 digest-g1-1 2608.20256 条目 ②设计预算决策 ③实现 ④评估。
【提示词】你是推理优化 AI。读 digest-g1-1-2026-08-30.md 中 2608.20256（Adaptive Reasoning Budget：模型自选推理时长，MATH 上省 41% token 不掉精度），为 NEKO 实现自适应推理预算：按任务复杂度选择 NoThink/Short/Long 推理路径。输出模块 + 测试（简单/复杂任务 token 对比）。验收：简单任务省 token ≥30%，复杂任务精度不降。推 trae/agent-k17 分支。

---

# K18 Relation Mixer

> 来源分组：group4-工具链（第三批）

【SPEC】推理工具链评估 Relation Mixer：关系优先 token 混合替代 MHA，吞吐 4×。验收=评估报告 + 原型。
【工单】①读 digest-g1-1 2608.20172 条目 ②分析 Relation Mixer ③原型 ④评估。
【提示词】你是注意力优化 AI。读 digest-g1-1-2026-08-30.md 中 2608.20172（Relation Mixer：关系优先 token 混合替代 MHA，等效质量下吞吐量提升 4 倍），评估其对本地 LLM 推理吞吐的改进价值。输出方案 + 最小原型（关系混合层替代注意力头）。验收：含吞吐对比 + 质量评估。推 trae/agent-k18 分支。

---

# K19 Bern2Edge Bernstein 多项式网络

> 来源分组：group4-工具链（第三批）

【SPEC】ESP32 端侧评估 Bernstein 多项式网络：边缘部署友好逼近。验收=评估报告 + 原型。
【工单】①读 digest-g1-2 2608.20497 条目 ②分析 Bernstein 网络 ③ESP32 可行性 ④原型。
【提示词】你是边缘部署 AI。读 digest-g1-2-2026-08-30.md 中 2608.20497v1（Bern2Edge: Bernstein 多项式网络边缘部署），评估 Bernstein 多项式网络对 ESP32-S3 端侧推理的适用性：与现有 OTA-ELM 对比。输出 docs/bern2edge-评估.md + 最小原型。验收：含参数量/精度/部署预算对比。推 trae/agent-k19 分支。

---

# K20 Agent Lightning 解聚式框架

> 来源分组：group4-工具链（第三批）

【SPEC】评估 Agent Lightning 解聚式框架：3.5K 行复现 SWE-bench 41.8→56.4%。验收=评估报告。
【工单】①读 digest-g1-1 2608.17528 条目 ②分析框架架构 ③评估自建价值 ④出报告。
【提示词】你是 Agent 框架 AI。读 digest-g1-1-2026-08-30.md 中 2608.17528（Agent Lightning v1.0：解聚式 Agent 框架+RL 后训练，3.5K 行代码复现，SWE-bench 41.8→56.4%），评估其架构对 NEKO/自有 Agent 栈的借鉴价值。输出 docs/agent-lightning-评估.md：架构拆解 + 可复用组件。验收：含 3 个可借鉴组件设计。推 trae/agent-k20 分支。

---

# K21 Geometry-Constrained KAN

> 来源分组：group4-工具链（第三批）

【SPEC】ESP32/工具链评估几何约束 KAN：可解释+端侧可行。验收=评估报告 + 原型。
【工单】①读 digest-g1-4 2608.25807 条目 ②分析几何约束 KAN ③ESP32 可行性 ④原型。
【提示词】你是 KAN AI。读 digest-g1-4-2026-08-30.md 中 2608.25807（Geometry-Constrained Kolmogorov-Arnold Networks），评估几何约束 KAN 对 ESP32 端侧可解释推理的适用性（与 OTA-ELM/Bern2Edge 对比）。输出 docs/geo-kan-评估.md + 最小原型。验收：含参数/精度对比 + 可解释性示例。推 trae/agent-k21 分支。

---

# K22 SATS 时序基础模型

> 来源分组：group4-工具链（第三批）

【SPEC】rf_brain 评估 SATS 时序基础模型：多尺度 patch token，频谱时序效率 +65.6%。验收=评估报告。
【工单】①读 digest-g1-1 2608.20005 条目 ②分析多尺度 patch ③评估频谱适配 ④出报告。
【提示词】你是时序模型 AI。读 digest-g1-1-2026-08-30.md 中 2608.20005（SATS Time Series：多尺度 patch token 对齐+混合掩码，时序基础模型效率提升 65.6%），评估多尺度 patch token 方法对 rf_brain 频谱时序建模（事件/信道状态序列）的效率改进。输出 docs/sats-timeseries-评估.md：方法 + 频谱适配 + 落地建议。验收：含效率对比 + 3 条落地建议。推 trae/agent-k22 分支。

---
