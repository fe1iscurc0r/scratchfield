# 记忆 MaaS API 调研报告 v1（W-06 · 只读调研先行）

> 调研日期：2026-08-23 · 智能体 B · 硬约束：NEKO 桌宠壳零改动、不碰 NEKO/apiserver
> 主流程、暴露接口前先出本文档。

## 一、现状：五件套是什么、在哪、怎么调

SPEC-03 落地的记忆五件套全部位于 `NEKO/N.E.K.O/memory/`，**纯标准库实现**
（零第三方依赖、零 NEKO 旧栈依赖），`__init__.py` 均不 re-export，需直接
import 子模块（测试惯例：`sys.path.insert(0, <repo>/NEKO/N.E.K.O)`）：

| 模块 | 入口（文件:行） | 公开 API | 存储 |
| --- | --- | --- | --- |
| hybrid_search | `hybrid_search/rrf.py` | `HybridSearchIndex(db_path).search(query, query_vec, limit, k)`（FTS5 关键词路 + fp16 向量路，RRF 融合）；`Record{id,text,vector,meta}` | 独立 SQLite（`hs_fts` FTS5 虚表 + `hs_vecs`） |
| index_cards | `index_cards/store.py` | `IndexCardStore(db_path).build_card(session_id, turns, summarizer=None, confidence=None)` / `cards_for_session` / `search_by_keyword` / `touch(card_id)` 续命 | 独立 SQLite（`index_cards` 表） |
| lineage | `lineage/model.py` | `SessionLineage(db_path).register(session_id, parent_id, branch_label, summary)` / `trace(session_id)→[根..自身]` / `children` / `branches_under(root_id)`；fork 三重守卫（父存在/无环/上下文≤40k字符）抛 `LineageError` | 独立 SQLite（`sessions` 表） |
| lifecycle | `lifecycle/policy.py` | `LifecyclePolicy{half_life_days=14,expire_weight=0.05,decay_weight=0.4,min_confidence_keep=0.25}`；`decay_weight()`/`expire_decision()→keep\|decay\|expire`/`enrich(records)`；`BackgroundWriter(store).submit_session_summary(session_id, turns)` 单写者后台线程 | 无自有库，写注入的 IndexCardStore |
| compaction_v2 | `compaction_v2/branch_summary.py` | `summarize_branches(lineage, root_id, turns_by_session)` / `branch_confidence` / `should_compress` / `measure`（token 节省评测） | 纯计算，读 lineage 不落盘 |

依赖关系：`compaction_v2→{index_cards,lineage}`，`lifecycle→index_cards`，其余独立。

## 二、暴露现状：零暴露、零外部调用方

- 全仓 grep：五件套引用方只有**彼此**与 `tests/test_spec03_phase1.py`（验收测试）。
- `NEKO/N.E.K.O/app/memory_server/`（48912 端口 FastAPI）服务的是**旧记忆栈**
  （FactStore/TimeIndexedMemory/PersonaManager 等），对五件套零引用。
- 根目录 `apiserver/`（陆墨 API，8000 端口）无任何记忆五件套端点，也无 memory_server 代理。

结论：sidecar 化是从 0 到 1 新建 HTTP 面，无兼容包袱，但也无人替我们踩过坑。

## 三、可安全暴露性评估

### 3.1 可直接暴露（读路径，无副作用）

- **lineage 读**：`trace` / `children` / `branches_under`——纯 SELECT，幂等。
- **hybrid_search.search**：只读（FTS5 查询），幂等；query_vec 可选。
- **index_cards 读**：`cards_for_session` / `search_by_keyword`。
- **lifecycle 纯函数**：`decay_weight` / `expire_decision` / `enrich`——无状态计算。

### 3.2 需串行化的写路径（单写者假设）

- `HybridSearchIndex` / `IndexCardStore` / `SessionLineage` 均为**裸 sqlite3 连接**：
  无 WAL、无 busy_timeout、无 threading.Lock（rrf.py:73 / store.py:50 / model.py:35）。
  多进程并发写同一 db 文件会 `database is locked`；`BackgroundWriter` 是刻意
  单写者模型（单 daemon 线程串行 build_card）。
- **对策（sidecar 设计前提）**：sidecar 是数据目录的**唯一写进程**；进程内用一把
  `threading.RLock` 串行化全部读写（操作皆毫秒级，锁粒度可接受）；卡片写入走
  `BackgroundWriter.submit_session_summary`（保持 SPEC-03 "提交方零等待"设计），
  写完把卡片文本同步进 HybridSearchIndex（把五件套组合成"写入即可检索"闭环）。

### 3.3 本期不暴露

- `compaction_v2`：分支摘要需 `turns_by_session` 全量输入，是批处理语义，不适合
  同步 HTTP；列为 MaaS v2 候选（POST /memory/compaction/branch_summary）。
- `BackgroundWriter` 的并发参数、`_embeddings` 稠密向量路：依赖面大，暂不引。

### 3.4 旧栈隔离硬约束

`tests/test_spec03_phase1.py::test_bypass_no_import_of_legacy_paths` 逐文件断言
五件套源码不 import `memory.facts` / `app.memory_server` 等旧路径——我们不改五件套
任何文件（NEKO 桌宠壳零改动 ✅），sidecar 只做 `sys.path` 注入 + import，
不触发该守卫（其只读五件套自身源码）。

## 四、MaaS 端点设计（v1 落地清单）

独立 sidecar 进程（**不改 apiserver 一行**）：`uvicorn mcpserver.memory_maas.app:app`，
host 127.0.0.1，端口 `MEMORY_MAAS_PORT`（默认 **48919**，接 NEKO 段位 48911-48918 之后），
数据目录 `MEMORY_MAAS_DATA_DIR`（默认 `<repo>/memory_maas_data/`，gitignore）。

| 端点 | 方法 | 语义 | 映射 |
| --- | --- | --- | --- |
| `/health` `/status` | GET | 存活/统计 | — |
| `/memory/search` | POST | 混合检索（关键词+可选向量），命中附带**会话血统** | `HybridSearchIndex.search` + `trace` |
| `/memory/cards` | POST | 写索引卡（后台写入+检索索引同步） | `BackgroundWriter.submit_session_summary` |
| `/memory/cards/{session_id}` | GET | 查会话卡片 | `cards_for_session` |
| `/memory/cards/search` | GET | 关键词查卡 | `search_by_keyword` |
| `/memory/cards/{card_id}/touch` | POST | 访问续命 | `touch` |
| `/memory/lineage/register` | POST | 登记会话（fork 守卫，冲突→409） | `register` |
| `/memory/lineage/trace/{session_id}` | GET | **会话血统链** | `trace` |
| `/memory/lineage/branches/{root_id}` | GET | 分支树 | `branches_under` |
| `/memory/lifecycle/report` | GET | 衰减/过期决策报告 | `enrich` + 全量卡片 |

错误映射：`LineageError`→409（血统冲突）；参数缺失→422；未知异常→500。
安全：仅绑 127.0.0.1，不鉴权（本机 sidecar，与 memory_server 48912 同水位）。

## 五、MCP 工具注册（memory_search）

`mcpserver/memory_maas/agent-manifest.json`（agentType=mcp，entryPoint→
`MemoryMaasBridge`）——走 `scan_and_register_mcp_agents` 注册，**不碰
`mcpserver/adapters/__init__.py`**（该文件当前有其他智能体未提交改动，避免纠缠）。

工具面：`memory_search`（检索+血统，先试 HTTP sidecar，不通则进程内直连降级）、
`memory_lineage`、`memory_write`、`memory_status`。sidecar URL 可用
`MEMORY_MAAS_URL` 覆盖（默认 `http://127.0.0.1:48919`）。

## 六、验收口径（对应工单）

1. "全系统任一模块调记忆 API 成功返回会话血统"：
   - HTTP 路径：TestClient 起侧车 app，register 三级血统 → GET `/memory/lineage/trace/{sid}`
     返回 `["root","child","grandchild"]` 链；
   - MCP 路径：`unified_call("memory_maas", {tool_name:"memory_search",...})`
     返回带 lineage 的检索结果（进程内降级路径同样成立，不依赖端口占用）。
2. pytest 相关全过：`tests/test_memory_maas.py`（core/HTTP/bridge/注册四层）+
   回归 `tests/test_spec03_phase1.py`（证明五件套源码零改动）。
