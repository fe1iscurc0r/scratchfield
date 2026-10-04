# K259 SEPO: Evidence-Grounded Prompt Optimization via Structural Editing

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28067v1
> 落点：工具链
> 核心：提出 SEPO：以编辑效果溯源反馈驱动结构化提示优化，每次编辑作用于 typed prompt schema 的稳定单元并记录其修复/破坏样本，在 14 任务上将 prompt 缩短 5 倍且 token 消耗减少 29%

【SPEC】工具链 增加/评估：SEPO: Evidence-Grounded Prompt Optimization via Structural Editing（来源 2608.28067v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28067 对应条目（语料 arxiv_corpus.jsonl 中 2608.28067v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
