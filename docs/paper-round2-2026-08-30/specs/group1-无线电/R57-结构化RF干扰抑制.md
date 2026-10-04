# R57 结构化 RF 干扰抑制

> 来源分组：group1-无线电（第三批）

【SPEC】rf_brain 结构化干扰抑制升级：AI 干扰抑制综述落地，承接 R03 滤波链。验收=模块 + 对比测试。
【工单】①读 digest-g1-4 2608.24974 条目 ②梳理干扰抑制方法 ③实现结构化抑制 ④对比。
【提示词】你是干扰抑制 AI。读 digest-g1-4-2026-08-30.md 中 2608.24974（Clearing the Underbrush: AI-Enhanced RF Interference Suppression），为 rf_brain 实现结构化干扰抑制：将窄带/脉冲/宽带干扰按结构分类抑制，与 R03 RFI 缓解模块衔接。输出 mcpserver/rf_brain/structured_interference.py + 测试。验收：合成多类干扰场景抑制后信号保真度较 R03 提升 ≥15%。推 trae/agent-r57 分支。
