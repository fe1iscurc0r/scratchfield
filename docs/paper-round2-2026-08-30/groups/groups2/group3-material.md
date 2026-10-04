# 升级项目组 3-2：材料线（M27-M31）

> 生成：2026-08-31 · 实验田维护者 · 第三批（全量一行核心筛选）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可丢给执行 AI

---

# M27 通用分子基础模型迁移

> 来源分组：group2-材料（第三批）

【SPEC】陆墨评估通用分子基础模型迁移：FM 跨任务迁移，承接 M08/M09。验收=评估报告 + 选型建议。
【工单】①读 digest-g1-4 2608.25893 条目 ②对比现有分子势/表征 ③评估迁移 ④选型。
【提示词】你是分子模型 AI。读 digest-g1-4-2026-08-30.md 中 2608.25893（A General-Purpose Molecular Foundation Model Transfers），评估通用分子基础模型对生物质/水凝胶体系的迁移价值：与 M08 DPA4C/M09 UBio-MolFM 对比，出选型建议。输出 docs/mol-fm-transfer-评估.md。验收：含迁移能力矩阵 + 推荐模型 + 落地路径。推 trae/agent-m27 分支。

---

# M28 MM-Spectrum 多模态光谱→结构

> 来源分组：group2-材料（第三批）

【SPEC】陆墨增加多模态光谱→结构推断：红外/质谱/NMR 联合推断分子结构。验收=方案 + 原型。
【工单】①读 digest-g1-4 2608.27286 条目 ②设计多模态融合 ③原型 ④评估。
【提示词】你是光谱分析 AI。读 digest-g1-4-2026-08-30.md 中 2608.27286（MM-Spectrum: Multimodal Multi-spectral Molecular Structure），为陆墨设计多模态光谱→分子结构推断：红外+质谱+NMR 特征融合，推断未知分子结构。输出方案 + 原型（轻量融合网络或特征拼接基线）。验收：合成光谱数据集结构推断准确率 ≥70%。推 trae/agent-m28 分支。

---

# M29 机械反应预测（离散流匹配）

> 来源分组：group2-材料（第三批）

【SPEC】陆墨评估机械反应预测：离散流匹配建模电子空间反应机理，承接 M16 热解动力学。验收=方案 + 原型。
【工单】①读 digest-g1-4 2608.27429 条目 ②分析离散流匹配反应预测 ③设计生物质适配 ④原型。
【提示词】你是反应机理 AI。读 digest-g1-4-2026-08-30.md 中 2608.27429（Mechanistic Reaction Prediction via Discrete Flow Matching：化学反应=电子空间变换），评估其对生物质热解自由基反应的适配，与 M16 流匹配能量衔接。输出方案 + 最小原型（电子转移建模）。验收：合成反应数据集预测准确率 ≥70%，方案含热解适配路径。推 trae/agent-m29 分支。

---

# M30 ML-NMR 化学位移预测

> 来源分组：group2-材料（第三批）

【SPEC】陆墨评估 ML-NMR 化学位移预测：分子固体 NMR 屏蔽快速估计。验收=评估报告。
【工单】①读 digest-g5-2 2608.21313 条目 ②分析 ML-NMR 方法 ③评估应用 ④出报告。
【提示词】你是 NMR AI。读 digest-g5-2-2026-08-30.md 中 2608.21313（Machine-Learned NMR Shieldings in Molecular Solids），评估 ML 化学位移预测对生物质材料表征（固体 NMR）的价值。输出 docs/ml-nmr-评估.md：方法 + 数据需求 + 落地路径。验收：含适用场景 + 3 条落地建议。推 trae/agent-m30 分支。

---

# M31 电解质分子设计

> 来源分组：group2-材料（第三批）

【SPEC】陆墨评估电解质分子设计：锂电电解液电子稳定性平衡。验收=评估报告。
【工单】①读 digest-g5-2 2608.16364 条目 ②分析电解质设计方法 ③评估与生物质相关性 ④出报告。
【提示词】你是电解质 AI。读 digest-g5-2-2026-08-30.md 中 2608.16364（Extracting a nitrile-centered, ether-assisted motif hierarchy for electrolyte design），评估电解质分子设计方法对生物质基电解质/离子传导研究的借鉴。输出 docs/electrolyte-design-评估.md。验收：含方法拆解 + 生物质适配建议。推 trae/agent-m31 分支。

---
