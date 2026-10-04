# K250 Training Communication-Efficient Mixture-of-Experts Language Models with Layer Re-Configuration

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28511v1
> 落点：工具链
> 核心：提出 CE-MoE：解耦 token-mixing 与 channel-mixing 深度，将专家集中在少数路由层，31.5B 规模减少 33.3% GPU 小时数且不损失精度

【SPEC】工具链 增加/评估：Training Communication-Efficient Mixture-of-Experts Language Models with Layer Re-Configuration（来源 2608.28511v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28511 对应条目（语料 arxiv_corpus.jsonl 中 2608.28511v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
