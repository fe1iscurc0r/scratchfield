---
name: sci-material-literature-search
description: 材料/生物质文献检索与综述工作流。帮用户"查一下纤维素水热液化的最新论文""木质素催化氢解的综述""把这个方向的论文整理成卡片"时使用。
version: 1.0.0
author: 陆墨
tags:
  - materials
  - literature
  - papers
  - biomass
enabled: true
---

# 材料文献检索与卡片化

基于本仓 PapersView（文献视图 + 知识卡片）落地。上游授粉：K-Dense-AI/scientific-agent-skills 文献类技能改造。

## 使用流程

1. **检索**：按方向关键词（如「lignin hydrogenolysis 2025」）→ PapersView 检索页。
2. **筛选**：按期刊/年份/引用数粗筛；与本地知识库去重（重复论文跳过）。
3. **卡片化**：核心论文 → 知识卡片（标题/方法/关键数据/可复用点），置信度标注。
4. **归档**：卡片进 index_cards（与 memory_maas insight 类实体对齐）。

## 材料线常用检索面

| 方向 | 关键词组 |
|------|---------|
| 生物质热解 | biomass pyrolysis kinetics product distribution |
| 纤维素转化 | cellulose hydrolysis/hydrothermal conversion |
| 木质素解聚 | lignin depolymerization catalytic hydrogenolysis |
| 材料表征 | FTIR TGA XRD biomass characterization |

## 验证

- 检索→卡片→归档链路可跑通；卡片含「方法+关键数据+可复用点」三要素。
