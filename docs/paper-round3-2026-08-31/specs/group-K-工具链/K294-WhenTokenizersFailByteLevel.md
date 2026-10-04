# K294 When Tokenizers Fail: Byte-Level Chunking for Zero-Shot Transfer to Low-Resource Languages

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.27658v1
> 落点：工具链
> 核心：When Tokenizers Fail Byte-Level Chunking 提出分层字节网络框架，通过 chunk 对齐损失将字节块投影到冻结子词模型子空间，低资源语言 POS 提升 13.3% NLP/LLM

【SPEC】工具链 增加/评估：When Tokenizers Fail: Byte-Level Chunking for Zero-Shot Transfer to Low-Resource Languages（来源 2608.27658v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.27658 对应条目（语料 arxiv_corpus.jsonl 中 2608.27658v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
