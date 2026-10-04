# W68-06 neo4j 图记忆（create-context-graph / agent-memory）评估

> 上游：neo4j-labs/create-context-graph（Apache-2.0，716★，Python）+ neo4j-labs/agent-memory（Apache-2.0，519★）
> 落点：docs/neo4j-graph-memory-评估.md · 勘察/评估

## 1. 项目定位

- **agent-memory**：Neo4j 图记忆库，多轮对话 + 自动实体抽取，把对话/上下文建成图（实体-关系）。
- **create-context-graph**：交互式 CLI 脚手架，选领域 + 选 agent 框架，秒级生成带图记忆的全栈应用（FastAPI 后端 + Next.js/Chakra 前端 + 图可视化）。

## 2. 架构拆解

- **记忆后端**：`agent-memory` v0.4，自动实体抽取 + 多轮对话；可 hosted（NAMS）或自托管 Neo4j（bolt）。
- **LLM 注入**：LiteLLM 多 provider（Anthropic/OpenAI/Bedrock/Vertex/Ollama/Groq…），`MEMORY_LLM` / `MEMORY_EMBEDDING` 环境变量。
- **脚手架**：`uvx create-context-graph` / `npx` 向导，生成 FastAPI + Next.js + 图 schema 可视化 + 实时 tool 调用可视化。

## 3. 与本仓对照

| 维度 | neo4j 图记忆 | 本仓 |
|---|---|---|
| 记忆表示 | 图（实体-关系） | memory_maas 实体图谱 + summer_memory 五元组 |
| 推理 | 图推理 | 五元组/实体图谱 |

**图记忆 vs 五元组对比表**：

| 能力 | 图记忆（neo4j） | 五元组（summer_memory） |
|---|---|---|
| 关系表达 | 任意多跳实体-关系 | 固定五元组（主体/谓词/客体/…） |
| 多跳推理 | 图查询/遍历强 | 弱（需自拼） |
| 部署 | 需 Neo4j 或 hosted NAMS | 轻量内嵌 |
| 实体抽取 | 自动 | 需规则/模型 |

## 4. 可落地借鉴点（≥3）

1. **「图记忆库 + 脚手架」分离**：agent-memory 是核心库，create-context-graph 是秒级脚手架——我们可借鉴「先有记忆库，再用脚手架降低接入成本」的分层。
2. **LiteLLM 多 provider 注入**：用环境变量切换 LLM/embedding provider，可复用到 memory_maas 的模型层。
3. **图 schema 可视化 + 实时 tool 调用可视化**：前端把图推理过程可视化，可作为我们记忆面板的参考。

## 5. 许可裁定 + 结论

- **许可**：Apache-2.0 → 可借鉴代码。
- **结论**：**参考为主**。图记忆的多跳推理比五元组强，但需 Neo4j（重）；我们不重复造轮子，可借鉴「图 schema + 实体抽取 + LiteLLM 注入」设计，在现有 memory_maas 实体图谱上增强，而非迁入 Neo4j 依赖。
