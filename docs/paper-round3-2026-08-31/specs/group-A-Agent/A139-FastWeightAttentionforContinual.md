# A139 Fast Weight Attention for Continual Learning

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.27763v1
> 落点：Agent
> 核心：推导快权重的读后写语义最优更新（Falcon-1/2/3 及其内积变体），在变长数字加法等任务上展示优于标准 SSM 的长度外推，统一了时间对齐、可塑性、遗忘与有限复习的建模框架

【SPEC】Agent 增加/评估：Fast Weight Attention for Continual Learning（来源 2608.27763v1）。
【验收】Agent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.27763 对应条目（语料 arxiv_corpus.jsonl 中 2608.27763v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
