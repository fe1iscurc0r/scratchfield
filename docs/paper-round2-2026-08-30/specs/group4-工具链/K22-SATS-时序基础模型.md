# K22 SATS 时序基础模型

> 来源分组：group4-工具链（第三批）

【SPEC】rf_brain 评估 SATS 时序基础模型：多尺度 patch token，频谱时序效率 +65.6%。验收=评估报告。
【工单】①读 digest-g1-1 2608.20005 条目 ②分析多尺度 patch ③评估频谱适配 ④出报告。
【提示词】你是时序模型 AI。读 digest-g1-1-2026-08-30.md 中 2608.20005（SATS Time Series：多尺度 patch token 对齐+混合掩码，时序基础模型效率提升 65.6%），评估多尺度 patch token 方法对 rf_brain 频谱时序建模（事件/信道状态序列）的效率改进。输出 docs/sats-timeseries-评估.md：方法 + 频谱适配 + 落地建议。验收：含效率对比 + 3 条落地建议。推 trae/agent-k22 分支。
