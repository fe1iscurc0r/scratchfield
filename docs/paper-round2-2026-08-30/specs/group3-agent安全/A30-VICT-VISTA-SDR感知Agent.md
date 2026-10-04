# A30 VICT 信用追溯+VISTA 反向适配→SDR 感知 Agent

> 来源分组：group3-agent安全（第四批）

【SPEC】rf_brain/IC-705 设计 SDR 感知 Agent 决策闭环：VICT 验证器信用追溯+VISTA 反向 teacher 适配。验收=方案 + 原型。
【工单】①读 round3 digest-g1a VICT/VISTA 授粉点 ②设计信用追溯 ③原型 ④评估。
【提示词】你是感知 Agent AI。读 /home/ubuntu/research/papers/round3/digests/digest-g1a-2026-08-31.md 中 VICT（2608.28128）+VISTA（2608.28306）授粉点，为 SDR 感知 Agent 设计决策闭环：验证器（信号协议格式/解调成功）信用追溯映射到决策步骤 + teacher 反向修正。输出方案 + 原型（信号检测→下一步动作）。验收：合成场景决策正确率 ≥75%，含信用分配可视化。推 trae/agent-a30 分支。
