# K529 FlowVVTON: Flow-Guided Mask-Free Video Virtual Try-On

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.30450v1
> 落点：工具链
> 核心：FlowVVTON：光流作为训练监督信号替代解析mask/姿态，flow-warped潜在损失多尺度时间一致性，TikTokDress 5.7× VFID-R增益

【SPEC】工具链 增加/评估：FlowVVTON: Flow-Guided Mask-Free Video Virtual Try-On（来源 2608.30450v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.30450 对应条目（语料 arxiv_corpus.jsonl 中 2608.30450v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
