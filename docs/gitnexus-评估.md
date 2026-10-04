# W69-02 GitNexus 评估（代码情报引擎）

> 上游：abhigyanpatwari/GitNexus（Akon Labs）· 46859★ · 2025-08 · TypeScript · 活跃
> 定位：把代码库索引成知识图（依赖/调用链/簇/执行流），经 MCP 工具暴露给 AI Agent
> **许可裁定：PolyForm Noncommercial 1.0.0（非开源，仅非商业源可用）——只参考设计，不融合代码，且不可商用**
> 结论：**不接入，仅参考设计**（许可阻断 + 与本仓 graphify/repowiki 能力重叠）

## 1. 架构拆解（clone 实测 ARCHITECTURE.md）

Monorepo：CLI/MCP（`gitnexus/`）+ 浏览器 UI（`gitnexus-web/`）+ 共享类型（`gitnexus-shared/`）。

```
摄取 analyze.ts → runFullAnalysis → 19 阶段 DAG → 内存 KnowledgeGraph → LadybugDB 图（.gitnexus/）
持久化 repo-manager.ts + lbug-adapter.ts（图加载/查询/embedding 批）
查询层（三接口同一后端）：
  MCP(stdio) → LocalBackend → tools.ts/resources.ts
  HTTP 桥 → serve.ts → Express（api.ts/mcp-http.ts）→ Web UI
  CLI 直连 → gitnexus query|context|impact|cypher
```

MCP 工具：`query`(BM25+向量混合)、`cypher`、`context`(调用/被调用)、`impact`(爆炸半径)、
`detect_changes`、`rename`、`api_impact`、`trace`、`route_map`、`tool_map`、`shape_check`、
`explain`(污点)、`pdg_query`(CDG/REACHING_DEF)、`group_list/sync`(多仓库契约桥)。

> 注意：工单写「零服务器」，实测其有 CLI/MCP 本地方案，也有 `serve.ts`+Docker 的 server/web 模式——非纯零服务器，是「本地优先 + 可选 server」。

## 2. 与本仓对照

| 维度 | GitNexus | 本仓 graphify / repowiki / codebase-memory-mcp |
|------|----------|-----------------------------------------------|
| 代码索引 | 19 阶段 DAG → 图 | graphify 已做图化索引 |
| 查询 | MCP 工具族（query/impact/trace/pdg） | codebase-memory-mcp 记忆侧 |
| 多仓库 | group 契约桥（跨仓库 trace） | 相对薄弱 |

能力上 GitNexus 的 `impact`/`trace`/`pdg_query`（控制/数据依赖）比本仓现有代码索引更深，但许可阻断直接复用。

## 3. 可落地借鉴点（≥3）

1. **「影响面/爆炸半径」工具设计**：`impact` 给出上游/下游 + 风险摘要，是本仓代码检索可补的「改动影响」能力。
2. **PDG（程序依赖图）查询**：`pdg_query` 分 CDG（控制）/REACHING_DEF（数据流）两模式，是比「符号索引」更深的可借鉴点。
3. **多仓库 Contract Bridge**：group 模式下跨仓库 `trace`/`impact` 的契约桥，可借鉴到本仓多模块仓库的跨仓依赖追踪。
4. **陈旧度检测**：`staleness.ts` 比对索引 lastCommit vs HEAD，提示索引过期——简单实用。

## 4. 许可裁定与结论

- **许可**：PolyForm Noncommercial 1.0.0（README 徽章与 LICENSE 实测）——**非开源**，仅允许非商业使用。
  > 工单标注「NOASSERTION」不准确，实测为 PolyForm Noncommercial。
  > **与 AGPL 不兼容**：即使本仓是 AGPL-3.0，也**吞不了** PolyForm NC——它的「仅非商业」限制
  > 与 AGPL 的再分发权冲突（AGPL 允许商用再分发，PolyForm NC 禁止），两者无法组合。
- **结论**：**不接入、只参考设计**。许可（非商用限制）阻断代码复用，与本仓 AGPL 也无法融合；且能力与本仓 graphify/repowiki 重叠。借鉴其 `impact`/`pdg_query`/契约桥的**设计**即可。
