# R155 GeBDA: Building Damage Assessment as Text-Based Sequence Prediction

> 来源分组：第八批（round3 新论文 2026-08-27/28）
> 来源论文：2608.28567v1
> 落点：无线电
> 核心：GeBDA Building Damage Assessment as Text-Based 将建筑损伤评估建模为自回归序列生成（边界框+损伤标签），用 Gemma 模型仅凭双时相卫星图实现端到端损伤制图 通用视觉/VLM

【SPEC】无线电 增加/评估：GeBDA: Building Damage Assessment as Text-Based Sequence Prediction（来源 2608.28567v1）。
【验收】无线电 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round3 digest 中 2608.28567 对应条目（语料 arxiv_corpus.jsonl 中 2608.28567v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
