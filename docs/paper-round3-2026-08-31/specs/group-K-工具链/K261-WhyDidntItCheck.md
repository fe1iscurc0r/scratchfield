# K261 Why Didn't It Check? Unsupported Final Claims and Their Repair in Two Tool-Equipped Language Models

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.27768v1
> 落点：工具链
> 核心：精确测量工具赋能 LLM 做出无证据最终声称的发生率（Qwen3-32B: 33/512），并证明自动检查规则仅需添加 21 次证据调用即可修复全部 10 个错误声称且零损伤正确案例

【SPEC】工具链 增加/评估：Why Didn't It Check? Unsupported Final Claims and Their Repair in Two Tool-Equipped Language Models（来源 2608.27768v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.27768 对应条目（语料 arxiv_corpus.jsonl 中 2608.27768v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
