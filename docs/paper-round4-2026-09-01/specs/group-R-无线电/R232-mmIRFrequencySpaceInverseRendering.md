# R232 mmIR: Frequency-Space Inverse Rendering for 3D Millimeter-Wave Radar ADC Synthesis

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.28913v1
> 落点：无线电
> 核心：**mmIR: Frequency-Space Inverse Rendering for 3D Millimeter-Wave Radar ADC Synthesis** 雷达物理可微分逆渲染——用 LiDAR 网格作为几何骨架，通过端到端自动微分优化 ITU 物理材质、天线方向图和多跳传播相位相干 MIMO 模型，将粗分辨率 commodity radar 合成高分辨率 3D ADC 信号（相关度 0.914）。这是将"多跳物理建模"引入可学习合成管道的里程碑，对无线电/SDR 链路级仿真和 ESP32 端侧感知融合有直接参考价值。

【SPEC】无线电 增加/评估：mmIR: Frequency-Space Inverse Rendering for 3D Millimeter-Wave Radar ADC Synthesis（来源 2608.28913v1）。
【验收】无线电 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.28913 对应条目（语料 arxiv_corpus.jsonl 中 2608.28913v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
