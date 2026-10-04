# K476 JITterFlip: Uncovering Fault Attack Surfaces in JIT-Compiled LLM Serving

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.29745v1
> 落点：工具链
> 核心：位翻转攻击 JIT LLM 服务控制面：故障服务决策而非模型计算，跨 CPU-GPU Rowhammer 至 125x 延迟

【SPEC】工具链 增加/评估：JITterFlip: Uncovering Fault Attack Surfaces in JIT-Compiled LLM Serving（来源 2608.29745v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.29745 对应条目（语料 arxiv_corpus.jsonl 中 2608.29745v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
