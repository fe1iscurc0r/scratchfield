# R65 推测探针→SDR 信号分类

> 来源分组：group1-无线电（第四批）

【SPEC】rf_brain 增加推测探针式信号分类：复用感知 pipeline KV 零开销分类。验收=模块 + 测试。
【工单】①读 round3 digest-g1b Speculative Probing 授粉点 ②设计分类附加 ③实现 ④评估。
【提示词】你是信号分类 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g1b-2026-08-31.md 中 Speculative Probing（2608.28099）授粉点，为 rf_brain 实现推测探针式分类：复用 SDR 感知/解码 pipeline 的中间特征做零额外开销信号分类（调制/异常）。输出 mcpserver/rf_brain/speculative_probe.py + 测试。验收：分类准确率 ≥85%，额外开销 ≤5%。推 trae/agent-r65 分支。
