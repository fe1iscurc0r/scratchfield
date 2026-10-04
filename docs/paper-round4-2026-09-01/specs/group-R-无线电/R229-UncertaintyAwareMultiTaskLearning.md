# R229 Uncertainty-Aware Multi-Task Learning for Joint Modulation Recognition and SINR Estimation

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.28865v1
> 落点：无线电
> 核心：**Uncertainty-Aware Multi-Task Learning for Joint Modulation Recognition and SINR Estimation** 直接可迁移到自研 SDR/无线电接收链：用36个确定无标签统计量压缩I/Q窗口、任务特定adapter共享表示，并首创"选择式推理"（分类熵+回归方差联合不确定度）。调制识别+SINR联合估计正是认知无线电/智能接收机的核心，方法轻量、与硬件无关，对 ESP32/SDR 实机部署有即插即用价值。

【SPEC】无线电 增加/评估：Uncertainty-Aware Multi-Task Learning for Joint Modulation Recognition and SINR Estimation（来源 2608.28865v1）。
【验收】无线电 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.28865 对应条目（语料 arxiv_corpus.jsonl 中 2608.28865v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
