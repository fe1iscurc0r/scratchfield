# S23 CamoDocs RAG 投毒防御

> 来源分组：group3-agent安全（第四批）

【SPEC】NEKO 评估 CamoDocs RAG 投毒攻击面并设计防御：伪装文档+分散 token 扩散嵌入。验收=分析 + 防御方案。
【工单】①读 round3 digest-g3 CamoDocs 授粉点 ②分析攻击机制 ③设计防御 ④出方案。
【提示词】你是 RAG 安全 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g3-2026-08-31.md 中 CamoDocs（2608.28389）授粉点（伪装文档+分散 token 扩散嵌入避开查询包含检测，GPT-5.4-mini ASR 61.8%），为 NEKO RAG 设计投毒防御。输出 docs/camodocs-rag-defense-方案.md：攻击机制拆解 + ≥3 条防御。验收：含防御层设计 + 检测指标。推 trae/agent-s23 分支。
