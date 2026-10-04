# K649 Stride-k Subsampling: Train-Free Audio Token Reduction for Whisper

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.30927v1
> 落点：工具链
> 核心：Whisper免训练token降采样（stride-2）省75%音频token/58%FLOP/时延降27%，WER几乎无损

【SPEC】工具链 增加/评估：Stride-k Subsampling: Train-Free Audio Token Reduction for Whisper（来源 2608.30927v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.30927 对应条目（语料 arxiv_corpus.jsonl 中 2608.30927v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
