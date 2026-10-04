# K125 VIG-Sampler

> 来源分组：第七批（round2 存量全量扩编）
> 来源论文：26580v1
> 落点：AAgent,K工具链
> 核心：扩散MLLM视觉注意力引导采样器，优先图像注意力高token，Captioning平均+19.3 CIDEr

【SPEC】AAgent,K工具链 增加/评估：VIG-Sampler（来源 26580v1）。
【验收】AAgent,K工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round2 digest 中 26580v1 对应条目（语料 arxiv_corpus.jsonl 中 26580v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
