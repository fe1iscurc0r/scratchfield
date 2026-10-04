# R06 TACAN 动态频谱接入

> 来源分组：group1-无线电

【SPEC】评估 TACAN（信道 token 注意力+PPO，92.5% 成功率）做频谱避让策略；验收=策略设计文档 + 模拟环境验证方案。
【工单】①读 GX-3b digest②映射到 rf_brain 频谱决策③出方案。
【提示词】你是频谱决策 AI。勘察 TACAN 落地：读 digest-gx-3b-2026-08-30.md 授粉点，设计 rf_brain 动态频谱接入策略（信道 token 注意力替代全信道扫描）。输出 docs/tacan-dsa-勘察.md：状态/动作/奖励定义 + 模拟验证方案。验收：文档含 MDP 定义 + 3 个模拟场景。
