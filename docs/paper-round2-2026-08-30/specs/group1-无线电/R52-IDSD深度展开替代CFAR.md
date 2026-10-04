# R52 IDSD 深度展开替代 CFAR

> 来源分组：group1-无线电（第二批）

【SPEC】rf_brain 增加深度展开信号分解：IDSD 无窄带假设自适应分量迭代提取，替代固定阈值 CFAR；Nesterov 加速。验收=模块 + 对比测试。
【工单】①读 digest-g8-3b IDSD 授粉点 ②设计深度展开结构 ③实现 ④与 CFAR 对比。
【提示词】你是信号分解 AI。读 digest-g8-3b-2026-08-30.md IDSD 授粉点（无窄带假设+自适应分量迭代提取替代固定阈值 CFAR），为 rf_brain 实现深度展开信号分解：迭代软阈值展开网络分离信号/干扰分量，Nesterov 加速收敛。输出 mcpserver/rf_brain/deep_unfold_decompose.py + 测试。验收：合成干扰场景分量分离精度较 CFAR 提升 ≥20%，ESP32 毫秒级窗口可行（参数量 <100K）。推 trae/agent-r52 分支。
