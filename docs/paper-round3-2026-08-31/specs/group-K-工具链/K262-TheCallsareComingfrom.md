# K262 The Calls are Coming from Inside the Model: Investigating Probe-based Detection of Tool-Calling Errors in LLMs

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.27750v1
> 落点：工具链
> 核心：用线性探针从 LLM 隐藏状态检测工具调用错误，跨 18 个工具调用 LLM 验证有效性，发现模型规模、探测层位、后训练类型是关键影响因素，且探针可泛化到新型错误类型

【SPEC】工具链 增加/评估：The Calls are Coming from Inside the Model: Investigating Probe-based Detection of Tool-Calling Errors in LLMs（来源 2608.27750v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.27750 对应条目（语料 arxiv_corpus.jsonl 中 2608.27750v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
