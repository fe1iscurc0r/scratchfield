# K17 Adaptive Reasoning Budget

> 来源分组：group4-工具链（第三批）

【SPEC】NEKO 增加自适应推理预算：模型自选推理时长（NoThink/Short/Long），省 token 不掉精度。验收=模块 + 测试。
【工单】①读 digest-g1-1 2608.20256 条目 ②设计预算决策 ③实现 ④评估。
【提示词】你是推理优化 AI。读 digest-g1-1-2026-08-30.md 中 2608.20256（Adaptive Reasoning Budget：模型自选推理时长，MATH 上省 41% token 不掉精度），为 NEKO 实现自适应推理预算：按任务复杂度选择 NoThink/Short/Long 推理路径。输出模块 + 测试（简单/复杂任务 token 对比）。验收：简单任务省 token ≥30%，复杂任务精度不降。推 trae/agent-k17 分支。
