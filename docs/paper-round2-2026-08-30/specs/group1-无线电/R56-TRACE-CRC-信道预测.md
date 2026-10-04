# R56 TRACE-CRC 信道预测

> 来源分组：group1-无线电（第三批）

【SPEC】rf_brain 信道预测加 trajectory-adaptive conformal risk control：给 R08 谱约束预测补覆盖率保证。验收=模块 + 覆盖率测试。
【工单】①读 digest-g1-4 2608.27124 条目 ②设计 conformal 校准 ③实现 ④覆盖率验证。
【提示词】你是信道预测 AI。读 digest-g1-4-2026-08-30.md 中 2608.27124（TRACE-CRC：Trajectory-Adaptive Conformal Risk Control for CSI），为 rf_brain 的谱约束信道预测（R08）增加 conformal risk control：轨迹自适应校准，输出带覆盖保证的 CSI 预测区间。输出 mcpserver/rf_brain/conformal_channel_pred.py + 测试。验收：合成信道数据覆盖率达标的预测区间，覆盖率 ≥90% 且区间宽度可控。推 trae/agent-r56 分支。
