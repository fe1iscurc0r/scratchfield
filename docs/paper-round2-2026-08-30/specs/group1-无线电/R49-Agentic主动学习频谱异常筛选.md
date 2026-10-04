# R49 Agentic 主动学习频谱异常筛选

> 来源分组：group1-无线电（第二批）

【SPEC】rf_brain 增加 Agentic 主动学习管线：隔离森林→频谱嵌入向量排序候选，多模态 LLM 评审异常，低 SNR 高效筛选。验收=原型 + 候选筛选效率对比。
【工单】①读 digest-g6-2b Agentic 主动学习授粉点 ②设计隔离森林频谱嵌入 ③实现筛选管线 ④对比全量扫描。
【提示词】你是频谱异常检测 AI。读 digest-g6-2b-2026-08-30.md Agentic 主动学习授粉点（隔离森林排序→LLM agent 迭代评审→共识过滤），为 rf_brain 实现低 SNR 频谱异常候选筛选：隔离森林对频谱嵌入向量排序 → 规则评审 → 输出候选列表供 Agent 深度分析。输出 mcpserver/rf_brain/spectrum_anomaly_agentic.py + 测试。验收：合成异常注入下候选命中率 ≥80%，筛选量较全量扫描降 ≥10×。推 trae/agent-r49 分支。
