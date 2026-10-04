# K24 保形 UQ 神经算子→频谱预测覆盖

> 来源分组：group4-工具链（第四批）

【SPEC】rf_brain 增加保形 UQ：神经算子不确定性量化保证，与 R56 合并推进。验收=模块 + 测试。
【工单】①读 round3 digest-g7 Conformal UQ 授粉点 ②设计保形校准 ③实现 ④验证。
【提示词】你是不确定性 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g7-2026-08-31.md 中 Conformal UQ（2608.28515）授粉点（神经算子保形不确定性量化保证），为 rf_brain 频谱/信道预测实现保形校准（与 R56 TRACE-CRC 合并推进）。输出 mcpserver/rf_brain/conformal_uq.py + 测试。验收：覆盖率 ≥90% 且区间宽度可控。推 trae/agent-k24 分支。
