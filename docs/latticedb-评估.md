# W69-03 latticedb 评估（单文件知识图数据库）

> 上游：jeffhajewski/latticedb · MIT · ~638★ · 2025-12 · Zig（原生 liblattice）+ Python/TS/Java 绑定 · 活跃
> 定位：嵌入式单文件属性图数据库，图遍历 + HNSW 向量 + BM25 全文三合一
> 结论：**值得试点**——作为记忆 sidecar 的轻量替代候选（MIT 可融合）

## 1. 架构拆解（clone 实测 README）

- **单文件**：整个库就是一个可移植文件，无 server、无配置、embedded 单写者模型。
- **一个查询层**：图遍历（Cypher 风格）+ HNSW 向量相似（`<=>` 算子）+ BM25 全文（`@@` 算子）在同一查询语言里。
- **一个事件日志**：持久命名流 + 图 changefeed，与图写入共享同一 WAL/事务路径。
- **性能**：0.13 µs 节点查找，1M 向量 0.83 ms 向量检索（100% recall）。
- **语言绑定**：核心 Zig 原生库 `liblattice`，pip / npm / maven 绑定。

示例查询（图 + 向量 + 全文三合一）：
```cypher
MATCH (chunk:Chunk)-[:PART_OF]->(doc)-[:AUTHORED_BY]->(author)
WHERE chunk.embedding <=> $q < 0.3 AND doc.content @@ "neural networks"
RETURN doc.title, chunk.text, author.name
```

## 2. 与 cozo / 记忆五元组的对比

| 维度 | latticedb | cozo sidecar | memory_maas 五元组 |
|------|-----------|--------------|--------------------|
| 存储形态 | 单文件嵌入式 | 嵌入式 Datalog | 图谱（Neo4j 惰性） |
| 查询语言 | Cypher 风格 | Datalog | 五元组查询 |
| 向量检索 | 原生 HNSW | 需外部向量 | 依赖外部 |
| 全文检索 | 原生 BM25 | 无/弱 | 无 |
| 图+向量+全文 | **三者原生合一** | 分开 | 分开 |
| 许可 | MIT | Apache/商业 | 本仓 |

latticedb 的独特卖点：**图 + 向量 + 全文在一个引擎、一个查询层、一个文件里**，无需像本仓现在那样拼接多个后端。

## 3. 可落地借鉴点（≥3）

1. **三合一的查询范式**：一个查询里同时做图遍历 + 向量近邻 + 全文过滤（`<=>`/`@@`），是「记忆检索」理想形态，可借鉴为本仓记忆检索的目标 API。
2. **单文件 + WAL 持久化**：整个库一个文件 + 命名流 + changefeed，适合「轻量 sidecar + 事件驱动记忆」。
3. **多语言绑定方式**：Zig 核心 + pip/npm/maven 绑定，与本仓「Python 主流程 + 底层原生」同构，可参考其打包方式。

## 4. 许可裁定与结论

- **许可**：MIT，**可融合**。
- **结论**：**值得试点**。作为记忆 sidecar（替代 cozo + 外部向量/全文拼接）有吸引力：图+向量+全文三合一 + 单文件 + MIT。落地路径：pip 装 latticedb，用其 Python 绑定在 NEKO 记忆层做小规模 PoC，验证图 RAG 检索质量与性能后再决定是否替换现有 sidecar。
