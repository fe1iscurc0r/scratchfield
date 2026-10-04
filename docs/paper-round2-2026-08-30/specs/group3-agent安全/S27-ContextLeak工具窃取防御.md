# S27 ContextLeak 恶意工具上下文窃取防御

> 来源分组：group3-agent安全（第四批）

【SPEC】NEKO 评估 ContextLeak 攻击面并设计防御：恶意工具窃取 Agent 上下文。验收=分析 + 防御方案。
【工单】①读新论文 2608.27800 ②分析窃取机制 ③设计防御 ④出方案。
【提示词】你是工具安全 AI。读语料 /home/ubuntu/research/papers/arxiv_corpus.jsonl 中 2608.27800（ContextLeak: Exfiltrating LLM Agent Context via Malicious Tools），分析恶意工具窃取 Agent 上下文的机制，为 NEKO 设计防御（工具沙箱/上下文最小化/出口监控）。输出 docs/contextleak-defense-方案.md。验收：含攻击链拆解 + ≥3 条防御。推 trae/agent-s27 分支。
