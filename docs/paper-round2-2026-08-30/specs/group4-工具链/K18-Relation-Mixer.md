# K18 Relation Mixer

> 来源分组：group4-工具链（第三批）

【SPEC】推理工具链评估 Relation Mixer：关系优先 token 混合替代 MHA，吞吐 4×。验收=评估报告 + 原型。
【工单】①读 digest-g1-1 2608.20172 条目 ②分析 Relation Mixer ③原型 ④评估。
【提示词】你是注意力优化 AI。读 digest-g1-1-2026-08-30.md 中 2608.20172（Relation Mixer：关系优先 token 混合替代 MHA，等效质量下吞吐量提升 4 倍），评估其对本地 LLM 推理吞吐的改进价值。输出方案 + 最小原型（关系混合层替代注意力头）。验收：含吞吐对比 + 质量评估。推 trae/agent-k18 分支。
