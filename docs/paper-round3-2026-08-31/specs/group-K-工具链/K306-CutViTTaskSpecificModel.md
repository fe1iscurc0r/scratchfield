# K306 Cut-ViT: Task-Specific Model Pruning via Gram Anchoring Subspace Consistency

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28205v1
> 落点：工具链
> 核心：Cut-ViT Task-Specific Pruning via Gram Subspace DINOv3 子空间 Gram 锚定对齐+谱熵适应，单 A100 一分钟完成多稀疏度剪枝，六个任务九数据集 SOTA 通用视觉/VLM

【SPEC】工具链 增加/评估：Cut-ViT: Task-Specific Model Pruning via Gram Anchoring Subspace Consistency（来源 2608.28205v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28205 对应条目（语料 arxiv_corpus.jsonl 中 2608.28205v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
