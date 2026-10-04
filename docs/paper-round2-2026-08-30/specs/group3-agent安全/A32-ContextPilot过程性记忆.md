# A32 ContextPilot 过程性记忆→SDR 指令流

> 来源分组：group3-agent安全（第四批）

【SPEC】NEKO/ESP32 增加过程性记忆：ContextPilot 规划工具+软卸载+关键决策分支采样，低内存感知-决策。验收=方案 + 原型。
【工单】①读 round3 digest-g2a ContextPilot 授粉点 ②设计过程性记忆 ③实现 ④评估。
【提示词】你是记忆系统 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g2a-2026-08-31.md 中 ContextPilot（2608.28476）授粉点（过程性+规则引导记忆比大量经验存储更可靠），为 ESP32 SDR 指令流设计低内存感知-决策：频谱感知结果以结构化上下文注入而非全量历史记忆。输出方案 + 原型。验收：内存占用降 ≥40%，决策质量不降。推 trae/agent-a32 分支。
