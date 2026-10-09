# 融合候选：topoteretes/cognee

> **优先级 P1（本批第二）** ｜ 采集：2026-10-08 GitHub API 实测 ｜ ⚠️ **已有旧报告，本卡为增量**

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `topoteretes/cognee` |
| ★ | **31581**（工单初勘 31569；已比 W73 评估时的 30K 又涨） |
| 许可 | **Apache-2.0** ✓ |
| 语言 / 体积 | Python / 260 MB |
| 最近 push | 2026-10-07 |
| topics | `agent-memory` / `cognitive-architecture` / `context-engineering` / `ai-memory` |

## 1. 架构一句话（**描述级**）

面向 Agent 的**开源 AI 记忆平台**：把对话/文档转成**知识图谱**，
并提供跨会话持久记忆 + 自托管的图后端（"small models for free" 的取向）。

## 2. ⚠️ 与已有报告的关系（增量声明）

`docs/cognee-图记忆-评估.md`（W73-03，1.6 KB）已做过**图记忆引擎**评估，结论方向为
"实体-关系抽取 → 知识图谱 → 跨会话持久化 + event_protocol"。

**本卡增量**：不再重复"它是什么"，而是**对照我们已落地的 `memory_maas` SPEC** 找**升级弹药** ——
即工单指定的落点（"借其记忆分层/ECL 检索做升级弹药"）。**本卡不替代旧报告，两者互补。**

## 3. 与自家对应模块的差距

| 维度 | cognee | 陆墨现状（`mcpserver/memory_maas` + `event_bus`） |
|---|---|---|
| 存储形态 | 知识图谱（图后端自托管） | SQLite（sessions / index_cards / hs_records / typed_entities）+ **单写者纪律** |
| 检索 | ECL（Extract-Cognify-Load）管道 | 向量 + 图谱**双通道**（graph-memory 对照结论：不替代向量库，走影子模式） |
| 生命周期 | 平台级统一管理 | `memory_maas` 分层（short/long，promote_after）+ `event_bus/memory_lifecycle` |
| 部署 | 自托管服务 | 进程内 sidecar（`get_core()` 单例） |

**差距的本质**：cognee 是**平台**，memory_maas 是**sidecar**。可借的是**管道与分层策略**，不是部署形态。

## 4. 可借用的具体设计（非代码）

1. **ECL 三段式管道**（Extract → Cognify → Load）：我们目前是"写入即落库"，
   中间那层"**cognify**（把原始事件炼成可检索的认知单元）"值得对照 `run_index` / `evidence_loops` 做升级。
2. **记忆分层的触发条件**：cognee 的"何时从短期升长期"策略 vs 我们的
   `promote_after_seconds` 纯时间阈值 —— 可能可借**访问频次/重要度**维度。
3. **图谱与向量的混合检索排序**：与已落地的"影子模式"结论对接，找**融合排序**的具体设计。
4. **event_protocol**：把交互当事件接入 —— 我们已有 `event_bus`，可对标它的**事件 schema**。

## 5. 许可与边界

- **Apache-2.0** → 引码许可无障碍；**不要为了兼容而引入图数据库依赖**（我们是 SQLite sidecar，
  引 Neo4j/Kuzu 会破坏"零新重依赖"的既有约束）。
- **只借设计**（本批统一口径）。

## 6. 融合优先级与下一步

**P1** —— 有旧评估打底、增量明确、且落点（`memory_maas`）已在仓里。
**下一步（若选中）**：开 SPEC 做源码级复核，重点回答：
① ECL 的 cognify 层在我们 SQLite 单写者约束下能否落地？
② 分层升级除了时间阈值还能加什么信号（且不引入新依赖）？
③ 混合检索排序与现有双通道影子模式怎么合流？
