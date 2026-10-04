# S138 Revisiting Continuous Noise Sampling for Multi-Party Differential Privacy

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.27766v1
> 落点：安全
> 核心：多方 DP 噪声采样 发现 sample-and-scale 连续噪声采样被缩放操作限制在稀疏值集导致近 100% 攻击成功率，离散逐位采样 4-612x 加速且安全

【SPEC】安全 增加/评估：Revisiting Continuous Noise Sampling for Multi-Party Differential Privacy（来源 2608.27766v1）。
【验收】安全 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.27766 对应条目（语料 arxiv_corpus.jsonl 中 2608.27766v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
