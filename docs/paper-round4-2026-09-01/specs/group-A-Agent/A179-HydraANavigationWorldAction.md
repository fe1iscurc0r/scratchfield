# A179 Hydra: A Navigation World Action Model with Discrete Latent Planning and Continuous Flow-Matching Execution

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.28995v1
> 落点：Agent
> 核心：**Hydra: A Navigation World Action Model with Discrete Latent Planning and Continuous Flow-Matching Execution** 直接解决世界模型无法实时控制的代表性错配难题——把规划器的采样与评估都搬进统一离散隐流形，彻底消除"每个候选解码回像素空间"的实时性瓶颈。这是世界模型从"想象未来"走向"真机实时控制"的关键架构突破，对机器人/无人车/无人机自主决策都有直接迁移价值。

【SPEC】Agent 增加/评估：Hydra: A Navigation World Action Model with Discrete Latent Planning and Continuous Flow-Matching Execution（来源 2608.28995v1）。
【验收】Agent 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.28995 对应条目（语料 arxiv_corpus.jsonl 中 2608.28995v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
