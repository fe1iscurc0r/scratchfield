# A107 What Missing AI Post-Training

> 来源分组：第七批（round2 存量全量扩编）
> 来源论文：2608.19072
> 落点：AAgent
> 核心：Agent困于初始策略的局部调整，无法自发重估策略本身（经验/guidance/compute均不足）

【SPEC】AAgent 增加/评估：What Missing AI Post-Training（来源 2608.19072）。
【验收】AAgent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round2 digest 中 2608.19072 对应条目（语料 arxiv_corpus.jsonl 中 2608.19072）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
