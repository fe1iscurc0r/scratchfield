# xerj 索引 schema 勘察（工单223 任务一）

> 日期：2026-10-09 ｜ 方法：浅 clone `github_haul/xerj/`（Apache-2.0，★3402，Rust，116MB）只读分析。
> 源码依据：`engine/crates/xerj-autoindex/src/catalog.rs`（schema 原文）+ `docs/ARCHITECTURE.md` + sync.rs/watch.rs。

## 0. 一句话定性

**xerj 是一个 Rust 写的 ES 兼容搜索引擎**（不是库，是**独立服务**），主打"零配置 autoindex 任意目录
+ BM25/kNN 混合检索 + agent 工作流"——体量 68.5k 行 Rust（仅 autoindex crate），是**整套基础设施**而非可嵌入组件。

## 1. 三段 pipeline（数据摄入 → 索引构建 → 查询计划）

### ① 数据摄入（autoindex crate）

- **walk.rs**（1175 行）：目录遍历 → 格式探测（detect/ 下 e2e/cratecite 等 20+ 格式识别器）→ 去重（`file_key` 内容哈希：**byte-identical 文件只索引一次**，别名路径进 `duplicate_files`）；
- **watch.rs**（1284 行）：`notify` 文件系统监听 + **debounce**（`max_hold = max(5s, 2×debounce)` 下限防"永不索引"bug——源码注释明示这是踩过的坑）→ 增量重扫；
- **sync.rs/sync_executor.rs**（7273 行）：**事务式同步**——`SyncPlan` 带 `operation_hash` 校验、逐操作状态机（`record_operation_state`/`all_operations_committed`）、提交时 digest 验证。**断点可恢复**（manifest 记录每个操作 committed 与否）。

### ② 索引构建（catalog schema 原文，catalog.rs:86-168）

catalog 索引的 44 字段（关键组）：

| 组 | 字段 | 类型 |
|---|---|---|
| 数据集身份 | `doc_kind`/`slug`/`index_name`/`prefix`（corpus 作用域）| keyword |
| 规模 | `record_count`/`junk_records`/`bytes`/`file_count`/`formats` | long/keyword |
| 时间 | `time_field`/`time_min`/`time_max`（strict_date_optional_time\|\|epoch_millis） | date |
| 文件级 | `file_key`（内容哈希）/`path`/`format`/`status`/`duplicate_of`/`records` | keyword |
| 运行元数据 | `run_id`/`started`/`summary_generated_at` | keyword/date |
| 数据关联 | `corr_kind`/`a_dataset`↔`b_dataset`/`pearson_r`/`overlap`/`containment` | 混合 |

**增量更新机制**：三层——文件 mtime+内容哈希（skip 未变）→ watch debounce 事件驱动 → sync 事务操作粒度回放。

### ③ 查询计划

ES JSON → `xerj-query`（AST→planner→rewriter→executor）；检索 = **BM25（xerj-fts）+ HNSW kNN（xerj-vector）混合**，filtered 用精确重扫；默认 embedder 是 **lexical feature-hash 384 维**（离线零依赖，神经 embedder opt-in）。

## 2. 与现有 LightRAG / FTS5 轻量路线对照表

| 维度 | xerj | LightRAG（已融合） | FTS5 轻量路线（NEKO facts 等） |
|---|---|---|---|
| 形态 | **独立服务**（HTTP :9200 ES 协议） | Python 库（嵌入 apiserver） | SQLite 内嵌 |
| 语言/依赖 | Rust 单二进制（116MB 源码） | Python + 向量库 | 零依赖（SQLite 自带） |
| 检索 | BM25+HNSW 混合+rerank | 图+向量混合 | 纯词法 |
| 零配置索引 | ⭐ autoindex（格式探测/去重/事务同步） | 需手动喂文档 | 手动建表 |
| 增量 | watch+事务操作级 | 文档级 | 行级 |
| 部署成本 | 高（新服务进程） | 中 | 零 |

**各自强项/盲区**：xerj 强在**零配置摄入与事务式增量**（我们最缺的"文档自动进索引"）；弱在**重**（新基础设施）。
LightRAG 强在图检索；弱在摄入要手动。FTS5 强在零依赖；弱在无语义。

## 3. ⭐ 授粉判定：**参考级**（不融合、不部署）

**理由**：
1. **体量错配**：68.5k 行 Rust 独立服务 vs 本仓"零新重依赖"纪律（memory_maas 同款红线）；引入 = 新基础设施进程；
2. **可借的三样设计**（这是"参考级"的价值所在）：
   - **catalog schema 的字段组划分**（身份/规模/时间/文件级/运行元数据/关联）——我们 ingest→知识库的 schema 设计直接抄表结构；
   - **file_key 内容哈希去重 + duplicate_of 别名**——工单217 的 `/api/eda/ingest` 幂等（内容 hash）正是这个思路，可补"别名路径"语义；
   - **sync 事务操作粒度 + operation_hash 校验**——event_store 的 W119 断点恢复可对齐这个模式；
3. ES 协议兼容是它的 adoption 桥，对我们无增益（无 ES 客户端存量）。

**若未来要融合**（触发条件）：当"自动索引整个 repo/文档树"成为刚需且 FTS5 质量不够时，重评——届时作为
sidecar 服务部署（同 NEKO 边界），不嵌入主仓。
