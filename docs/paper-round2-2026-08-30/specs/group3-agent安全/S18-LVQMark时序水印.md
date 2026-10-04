# S18 LVQMark 时序水印

> 来源分组：group3-agent安全（第三批）

【SPEC】rf_brain 增加时序水印：频谱/传感数据鲁棒水印，编辑攻击下稳定检测。验收=模块 + 测试。
【工单】①读 digest-g1-1 2608.19727 条目 ②设计时序水印 ③实现 ④鲁棒性测试。
【提示词】你是数据水印 AI。读 digest-g1-1-2026-08-30.md 中 2608.19727（LVQMark Time Series Watermark：局部 token 化生成模型+鲁棒重编码，时序水印编辑攻击下稳定检测），为 rf_brain 频谱数据实现鲁棒水印：嵌入不可见水印 + 编辑/截断攻击下可检测。输出 mcpserver/rf_brain/ts_watermark.py + 测试。验收：编辑攻击后水印检出率 ≥80%，对数据质量影响 ≤5%。推 trae/agent-s18 分支。
