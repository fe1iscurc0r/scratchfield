# A120 DARTS: Decoder-Aware Representation Tuning via Surgery for Model Merging

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28547v1
> 落点：Agent
> 核心：用熵加权 L1 损失+逐位偏置修正解码器模型的表示漂移，0.1% 参数量提升模型融合质量

【SPEC】Agent 增加/评估：DARTS: Decoder-Aware Representation Tuning via Surgery for Model Merging（来源 2608.28547v1）。
【验收】Agent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28547 对应条目（语料 arxiv_corpus.jsonl 中 2608.28547v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
