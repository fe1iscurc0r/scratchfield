# K311 Token-Budget Distillation: Transferring Full-Token Semantics to Compressed Video Vision-Language Models

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28138v1
> 落点：工具链
> 核心：固定 token 预算蒸馏（TBD），压缩学生模型保留 97% 精度（R=10%），LoRA 微调+双路径师生 KL 散度+答案区域蒸馏 视频生成/理解

【SPEC】工具链 增加/评估：Token-Budget Distillation: Transferring Full-Token Semantics to Compressed Video Vision-Language Models（来源 2608.28138v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28138 对应条目（语料 arxiv_corpus.jsonl 中 2608.28138v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
