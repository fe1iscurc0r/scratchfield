# S19 Groundhog MoE 位翻转

> 来源分组：group3-agent安全（第三批）

【SPEC】安全评测增加 MoE 可用性攻击面：翻转 4 个专家比特输出膨胀 5912%。验收=攻击面分析报告。
【工单】①读 digest-g2-4 2608.25276 条目 ②分析位翻转攻击 ③出攻击面报告。
【提示词】你是 MoE 安全 AI。读 digest-g2-4-2026-08-30.md 中 2608.25276（Groundhog Bit-Flip Attack：翻转 MoE 路由层不到 4 个专家比特使输出膨胀 5912%），分析 MoE 路由层位翻转攻击对本地部署 LLM/NEKO 的威胁面。输出 docs/moe-bitflip-攻击面.md：攻击原理 + 防御建议。验收：含攻击链拆解 + ≥3 条防御。推 trae/agent-s19 分支。
