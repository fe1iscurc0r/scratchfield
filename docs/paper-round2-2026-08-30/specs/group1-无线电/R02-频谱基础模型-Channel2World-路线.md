# R02 频谱基础模型（Channel2World 路线）

> 来源分组：group1-无线电

【SPEC】评估并设计"频谱基础模型"：参考 Channel2World（26000 场景预训练+冻结编码器微调）在射频域落地；验收=勘察报告（可行性/数据源/规模）+ 最小原型设计文档。
【工单】①读 Channel2World 论文 digest（G8-1b）②对比现有 rf_brain 表征③定数据源（SDR 录制/仿真）④出设计文档。
【提示词】你是频谱 AI 架构 AI。勘察"频谱基础模型"可行性：读 /home/ubuntu/research/papers/round2/digests/digest-g8-1b-2026-08-30.md 中 Channel2World 要点，对比 rf_brain 现状，输出设计文档 docs/spectrum-foundation-model-勘察.md：预训练任务选择/数据源/模型规模/微调场景，含 P0 最小原型方案。验收：文档含 3 个候选预训练任务 + 1 个可落地原型。
