# SPEC-02: Lumo 科研助手规模化

> 版本 v1 | 2026-08-22 | 委托：外部 agent（类 Trae）
> 定位：用户专业（生物质能源材料）科研资产，长期沉淀

## 背景

Lumo（陆墨）已有：科研 skills 186 个、material_science 模块、matchat 桥、
graphify 知识图谱（已装 Hermes）、duckdb（已评估）。
本 SPEC 目标：把散件组装成"材料科研分析工作台"。

## 目标

1. academic 16 融合（545M 中转库 → Lumo 可消费）
2. graphify GraphRAG 检索闭环（图谱 + bge-small-zh 向量）
3. duckdb 材料数据分析工作台
4. 科研写作管线（nature-skills 已交 → 串成完整流程）

## 阶段拆解

### Phase 1: academic 16 融合（基础，优先）
- 任务 1.1: 16 项目逐一读文档，提取"模型弹药"（算法/API/数据格式）
- 任务 1.2: 按学术包标准出 DATASET.md / BENCHMARK.md / MODEL_INTERFACE.md
- 任务 1.3: 接入 material_science 模块（matchat_bridge 旁）
- 验收: 16 项全部有 MODEL_INTERFACE.md，Lumo 可调用 ≥5 项

### Phase 2: graphify GraphRAG
- 任务 2.1: 图谱导入脚本（scratchpad-knowledge → 图）
- 任务 2.2: bge-small-zh 向量检索接图谱节点
- 任务 2.3: 查询 API（社区导航 + 语义检索融合）
- 验收: "找 XX 材料的制备方法" 5 秒内返回图谱路径 + 原文

### Phase 3: duckdb 分析工作台
- 任务 3.1: CSV/Excel 导入模板
- 任务 3.2: 常用分析查询库（BOM/实验对比/趋势）
- 任务 3.3: 自动化报表输出（Markdown）
- 验收: 一份实验 CSV → 3 个标准分析 → 报告，全程 <1 分钟

### Phase 4: 科研写作管线
- 任务 4.1: 文献综述 → 实验设计 → 数据分析 → 论文写作 串流程
- 任务 4.2: 引用管理（bibtex）
- 任务 4.3: nature 风格输出模板
- 验收: 从选题到初稿的完整 demo

## 硬约束

- 不破坏现有 RAG 检索链路（SQLite + bge-small-zh 保持）
- academic 融合走独立分支（主仓已分叉，cherry-pick）
- 许可白名单：16 项全是 MIT/BSD/Apache（已核）

## 远期规划（Phase 5+）

- 5.1: 材料知识问答（GraphRAG + LLM）
- 5.2: 实验数据自动归档（手机拍照 → 表格 → 库）
- 5.3: 文献推荐（基于图谱社区）
- 5.4: 与 MatChat/材料数据库双向桥
- 5.5: 毕业论文辅助管线（大四可用）

## 目录结构（预期）

```
scratchpad/
├── research/         # Lumo 研究数据（天选7 已有）
├── academic/         # 16 项目模型弹药（MODEL_INTERFACE.md 索引）
├── mcpserver/material_science/
│   ├── academic_bridge/   # 16 项目调用接口
│   ├── graphrag/          # 图谱检索
│   └── duckdb_workbench/  # 分析工作台
└── skills/           # 科研写作管线 skills
```
