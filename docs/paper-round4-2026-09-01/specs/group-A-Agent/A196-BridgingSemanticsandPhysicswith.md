# A196 Bridging Semantics and Physics with Constrained LLMs for Safe and Trustworthy Robotic Manipulation

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.29379v1
> 落点：Agent
> 核心：**Bridging Semantics and Physics with Constrained LLMs** 把 LLM 语言动作缺口收敛为"类型化契约"：MCP schema 验证拒绝非法命令+MoveIt 物理核查 verify-then-act。这是 Agent 技术栈与安全执行完美结合的工程范本，对任何想让 LLM 驱动真实执行器的系统（含嵌入式/无线电管控）都有直接落地价值。

【SPEC】Agent 增加/评估：Bridging Semantics and Physics with Constrained LLMs for Safe and Trustworthy Robotic Manipulation（来源 2608.29379v1）。
【验收】Agent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.29379 对应条目（语料 arxiv_corpus.jsonl 中 2608.29379v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
