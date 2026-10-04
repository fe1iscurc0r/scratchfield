# graphify · Lumo 知识图谱接入评估

> 2026-08-29 · 沈遥线完成（原待办"graphify clone 评估"）· 来源：Graphify-Labs/graphify（Apache-2.0，23.5K★，YC S26，v0.9.51）
> clone 在 github_haul/graphify；本地 Hermes skill 已装 v0.9.48（/graphify 命令）
> 关联：SPEC-05 2.4（与记忆图谱互补不重叠）、Batch-1B 授粉（Lumo 知识图谱管线最高价值）

## 一句话

graphify 把任意文件夹（代码/文档/PDF/图片/视频）变成**可查询的知识图谱**：代码走 tree-sitter AST 全本地确定性解析（零 LLM 零成本），docs/论文走模型语义化；输出 graph.json + graph.html + GRAPH_REPORT.md；自带 MCP serve（stdio/HTTP）、watch 增量重建、Leiden 社区检测、god nodes、path/explain 查询。**它不是向量索引，是真图遍历**——问"谁用了 X、A 到 B 怎么连"。

## 关键能力（评估依据）

| 能力 | 说明 | 对我们的价值 |
|------|------|-------------|
| 代码免费全本地 | tree-sitter AST，不碰 LLM | scratchpad 代码库图谱零成本 |
| 边带信任标签 | EXTRACTED（源码显式）/ INFERRED（推导） | 可审计，符合"诚实标注"惯例 |
| 71.5x token 缩减 | benchmark 数据 | agent 查图代替读文件，省 token |
| MCP serve | serve.py stdio/HTTP | **直接挂 mcpserver，agent 可 query/path/explain** |
| watch 增量 | 目录变化自动重建（debounce 3s） | 授粉流水线"增量自动跑"偏好同构 |
| 社区检测 + god nodes | Leiden 聚类 + 关键节点 | 知识库结构体检 |
| 22 语言 tree-sitter | Python/TS/Go/Rust/Java 等 | scratchpad 多栈全覆盖 |

## 对 Lumo 的接入评估

### 接入面（可行）

1. **文档图谱**：对 `scratchpad/docs/` + `research/papers/digests/` 跑 `/graphify --obsidian` → 材料科研知识库图谱（SPEC-19 的 docs 也能纳入）
2. **MCP 挂载**：`serve.py` 起 MCP stdio server → 注册进 mcpserver（manifest.json）→ Hermes/Lumo agent 用 `graphify query/path/explain` 直接查图，替代 grep
3. **代码体检**：对 `apiserver/` + `summer_memory/` 跑一次 → god nodes/import cycles → 集成地狱（SPEC-04）体检报告
4. **与授粉配合**：GRAPH_REPORT.md 的 surprising connections = 免费授粉点发现器

### 不重叠（SPEC-05 2.4 确认）

- summer_memory = 会话记忆五元组（动态，Neo4j/quintuples.json）——graphify 是**静态语料**图谱，两者互补：记忆图谱回答"用户说过什么"，graphify 回答"代码/文档里有什么、怎么连"
- memory_maas typed 实体图谱（P1）面向记忆实体关系——graphify 面向文件/概念，不冲突

### 注意/限制

- **论文语料不能直接喂**：arxiv_corpus.jsonl 是 JSONL，需按 digest 文本文件喂（digests/ 目录已具备）
- docs/ 有 100+ 篇 md，首跑 LLM 语义 pass 会花 token → 建议先 `--mode code` 或先跑代码目录，docs 分批
- 本地 skill 0.9.48 vs 上游 0.9.51：可 `graphify update` 升级
- 许可 Apache-2.0 可吞（AGPL 主仓兼容）✅
- 平台已支持 Hermes（description 列了）✅

## 落地建议（优先级）

- **P0**：`/graphify apiserver/` 首跑 → 集成地狱体检（god nodes/import cycles），产出接入基线
- **P0**：serve.py MCP 挂载进 mcpserver → Lumo agent 获得 graphify query 能力
- **P1**：`/graphify scratchpad/docs/ --obsidian --update` → 材料科研文档图谱，cron 增量（watch.py）
- **P1**：GRAPH_REPORT.md 的 surprising connections 并入授粉流水线（每轮跑图看跨域连接）
- 升级本地 skill 到 0.9.51（graphify update）
