# GitLab knowledge-graph 评估（W71-03）

> 上游：gitlab-org/rust/knowledge-graph（70★）+ gitlab-org/orbit/knowledge-graph（57★，Rust）｜ <https://gitlab.com/gitlab-org/rust/knowledge-graph>
> 许可：MIT（GitLab 官方 Rust 库，可借鉴代码）

## 1. 项目定位

GitLab 官方——把**代码 + issue + MR + CI** 建成一张图，供 AI agent 导航软件生命周期：从「某段代码」
追溯到「相关 issue/变更/CI 失败」的上下文图。

## 2. 架构拆解

- **图构建范围**：代码符号、issue/MR 关系、CI 流水线状态，异构实体统一建模为图节点/边。
- **Rust 实现**：高性能图存储 + 增量更新（代码变更时图局部刷新）。
- **面向 AI agent 导航**：图作为 agent 的检索/上下文入口，替代全量文本检索。

## 3. 与本仓对照（验收项：对比表）

| 维度 | GitLab KG | graphify | codebase-memory-mcp |
|---|---|---|---|
| 实体范围 | 代码+issue+MR+CI | 代码结构 | 代码记忆/符号 |
| 生命周期 | 全（含 issue/CI） | 仅代码 | 代码级 |
| 语言/实现 | Rust | — | TS/Python |
| 增量更新 | 是 | 部分 | 部分 |

**结论**：GitLab KG 的独特价值在「软件生命周期上下文」（代码 ↔ issue ↔ CI 联动），比纯代码图更完整。

## 4. 可落地借鉴点（≥3）

1. **把 issue/CI 纳入代码图**：本仓 graphify/codebase-memory 目前偏代码结构，借鉴 GitLab KG 把
   工单（BATCH/SPEC/工单）与代码/分支关联成图，让 agent 能「从工单跳到相关代码提交」。
2. **增量图更新**：代码变更时局部刷新图（而非全量重建），降低 memory_maas 的图维护成本。
3. **「图即检索入口」的 agent 导航范式**：用生命周期图替代全量文本检索，提升 RAG/agent 的上下文命中。

## 5. 许可裁定

MIT——**可借鉴代码/设计**；但本仓目标是「工单→代码」图，GitLab KG 的 issue/CI 模型需映射到本仓
工单/分支体系，属设计借鉴为主。

## 6. 结论

可借鉴（高价值）。建议：把「工单/分支/代码」三类实体建图，作为 Hermes/Trae 多 agent 的共享上下文层。
