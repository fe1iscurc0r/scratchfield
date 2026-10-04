# A01 Credit Without Ground Truth → Agent 后训练评估修正

> 来源分组：group3-agent安全

【SPEC】识别并修正 Agent 后训练 credit assignment 自欺问题（step-level credit 不区分重要决策）；验收=评估方法论文档+复现实验。
【工单】①读 G1-1 digest②设计 credit 信号审计③复现对比。
【提示词】你是 Agent 训练 AI。审计 Agent credit assignment：读 digest-g1-1-2026-08-30.md，复现"step-level credit 因果上不区分重要决策点"问题，设计执行回放 ground truth 审计。输出 docs/agent-credit-audit-2026-08-30.md。验收：审计方法 + 复现实验设计。
