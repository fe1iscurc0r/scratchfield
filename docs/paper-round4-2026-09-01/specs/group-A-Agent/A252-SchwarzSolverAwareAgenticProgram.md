# A252 Schwarz: Solver-Aware Agentic Program Verification

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.30803v1
> 落点：Agent
> 核心：**Schwarz: Solver-Aware Agentic Program Verification** 把"LLM 生成的规约交给 SMT 求解器证明失败"这一真实痛点拆成义务局部、可检查、可修复的闭环，工程上直接解决 agent 验证的可信度天花板。SV-COMP 2026 上 91.5% vs CPAchecker 60.1%，对任何做自动代码/固件验证、RTL 证明、协议校验的人都可借鉴。

【SPEC】Agent 增加/评估：Schwarz: Solver-Aware Agentic Program Verification（来源 2608.30803v1）。
【验收】Agent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.30803 对应条目（语料 arxiv_corpus.jsonl 中 2608.30803v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
