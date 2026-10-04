# A22 UC-PSRO 通信退化鲁棒性

> 来源分组：group3-agent安全（第二批）

【SPEC】NEKO 多 Agent 增加通信退化课程训练：通信 dropout 下协作鲁棒性（35%→62% 参考）。验收=方案 + 原型。
【工单】①读 digest-g2-4 UC-PSRO 授粉点 ②设计通信退化课程 ③原型 ④评估。
【提示词】你是多 Agent 协作 AI。读 digest-g2-4-2026-08-30.md UC-PSRO 授粉点（通信 dropout 课程下任务完成率 35%→62%），为 NEKO 多 Agent 设计通信退化鲁棒训练：通信带宽/丢包渐进退化课程，Agent 学习降级协作策略。输出方案 + 最小原型（消息丢包模拟）。验收：丢包 50% 时任务成功率较无课程提升 ≥20%。推 trae/agent-a22 分支。
