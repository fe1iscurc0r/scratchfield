# K704 PaperGym: Rubric-Centered Evolution for Research-Plan Generation

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.31119v1
> 落点：工具链
> 核心：**PaperGym: Rubric-Centered Evolution for Research-Plan Generation** 将论文 rubric 转化为 RL 训练环境：问题来自研究目标+背景，标准来自方法+实验，criterion leakage 仅 3.7%（竞品 11.9-34.1%）。Qwen3-8B 经 PaperGym 训练后在 ResearchQA 达 73.48，超越参数量大得多的 Kimi K2.6。是 AI Scientist 自动化 planning 的工程化突破。

【SPEC】工具链 增加/评估：PaperGym: Rubric-Centered Evolution for Research-Plan Generation（来源 2608.31119v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.31119 对应条目（语料 arxiv_corpus.jsonl 中 2608.31119v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
