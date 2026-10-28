# 融合候选：LimiNode/agent-memory-cpp

> **优先级 P3+（观察档，不建议立项）** ｜ 采集：2026-10-16 GitHub API 实测 + README 实读 + **仓内能力逐项对照**
> 承接：工单 209 任务三调研卡目录 ｜ **工单 247** 出具（来源 cron `bda7241fa9c3`）
> 与既有卡的关系：本卡与 [tigerless-labs/agent-memory](tigerless-labs-agent-memory.md) 同属「记忆运行时」族，
> 但**量级与成熟度差两个数量级以上**（见 §0 的红线标注）

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `LimiNode/agent-memory-cpp` |
| ★ | **1**（⚠️ **本目录最低**；既有候选区间 1866 ~ 50147） |
| fork | **0** |
| 许可 | **MIT** ✓ |
| 语言 / 体积 | GitHub 归类 **Python** / **166 MB**（169,505 KB） |
| 最近 push | **2026-10-15**（活跃）｜ 创建 2026-06-29 |
| 定位 | "A C++17 library for building memory and retrieval systems for AI agents"（README 首行） |

### ⚠️ 体积构成（实测，非估算）

166 MB 里**源码只占极小部分** —— 大头是**基准产物**：

| 类型 | 文件数 | 体积 |
|---|---|---|
| `.bin` | 5 | **124.71 MB** |
| `.json` | 490 | **78.37 MB**（其中**单个** `frontier-v2.raw.json` = **73 MB**） |
| `.jsonl` | 35 | 23.85 MB |
| `.f32` | 4 | 11.45 MB |
| **`.py`** | 727 | **7.92 MB** |
| **`.cpp` + `.hpp`** | 276 | **3.20 MB** |
| `.md` | 393 | 3.84 MB |

⇒ **不 clone**（与目录既有纪律一致：airi 568 MB 时同样是「用 API 读结构」）。

### 仓库结构（实测）

```
src/agent_memory.hpp + src/agent_memory/     ← C++17 核
external/{hnswlib, libmdbx, mdbx-containers, simdcomp, zstd}   ← 5 个 submodule
guides/                                       ← 72 份 roadmap 文档
storage-bakeoff-v2/{*.raw.json, *.receipt.json}   ← 存储引擎横评（原始数据 + 收据）
finalist-v1/{*.raw.json, *.receipt.json, *.audit.receipt.json}
CMakeLists.txt（111 KB）· AGENTS.md · tests/ · tools/ · artifacts/
```

## 1. 架构一句话

**可嵌入宿主的 C++17 记忆/检索库**（自带 5 个存储/索引 submodule：hnswlib 向量索引、libmdbx 嵌入式 KV、
simdcomp 整数压缩、zstd 压缩），以「canonical 文档 + 稳定块标识 + 不可变修订」为内容模型，
把**存储 / 检索 / 证据**三层分开。README 明确自身是「库与研发项目，不是 LLM、不是成品助手、
不是托管记忆平台、不是 agent 编排框架」。

> ⚠️ README **自认其能力清单是「目标模型」**：「It describes the direction and contracts of the project;
> **it does not mean that every item is implemented today**」⇒ 引用其能力时不能当作现状。

## 2. 记忆数据格式

**本卡未能给出**（如实标注素材边界）：仓库根目录**没有** schema/数据格式文档，
内容模型的定义在 `src/agent_memory.hpp` 与 `guides/architecture.md` 内，
而本卡按目录纪律**不 clone、不读源码**（只读了 README + 目录结构 + 文件体积分布）。
⇒ 「canonical 文档 / 块标识 / 修订历史」的具体编码方式**待源码级复核**（若日后要评估融合）。

## 3. ⭐ 重点问题（工单点名）：能不能并入 214？

**能 —— 本卡就是并入方式**：按本目录既有六节格式出卡 + 更新 `00-汇总.md` 第三梯队，
**不另立目录、不另立 SPEC**（214 的口径是「调研级，不动手；不自动立项」）。

**但与 214 的候选不可同档比较**：本目录既有 9 张卡的 ★ 区间是 **1866 ~ 50147**，
本候选 **★=1 / fork=0** —— 差 3~4 个数量级。因此本卡的建议是**观察档**，
不给 P0/P1/P2 中的任何一档（详见 §6）。

## 4. 与 memory_maas + SPEC-05 的差距

**不是"差距"，而是"逐项已覆盖"** —— 上游 README 描述的 5 项能力，**仓内 5/5 已有实现**：

| 上游自述能力 | 仓内对应实现 | 证据（文件） |
|---|---|---|
| RAG | RAG 服务（解析/分块/检索） | `rag/rag_service.py`、`rag/chunk_splitter.py`、`rag/document_parser.py` |
| **hybrid BM25/vector search** | **两路混合检索 + BM25 打分** | `mcpserver/memory_maas/hybrid_search.py`（`_bm25_score` / `bm25_route` / `semantic_route` / `entity_route`） |
| knowledge graphs | 知识图谱抽取适配 | `mcpserver/graph_memory_adapter/kg_extract.py` |
| **Markdown ingestion** | **Obsidian vault 式 Markdown 增量索引** | `rag/vault_indexer.py`（内容哈希状态、原子写入、线程安全） |
| pluggable embeddings | 可插拔嵌入引擎 | `rag/embedding_engine.py`、`apiserver/local_embedder.py` |

⇒ **没有需要"接进来"的能力缺口**。工单 §1 的「把 toolkit 能力接入 agent 线」
在**能力层面无事可做**（这是本单最重要的结论，证据在上表）。

## 5. 可借用的具体设计（非代码）

上游 README 里有三条**值得学的工程主张**。逐条查仓内实指后：

| # | 上游主张 | 仓内现状 | 结论 |
|---|---|---|---|
| 1 | **"retrieval frequency does not become proof of truth"**（检索频次不得当作真值证据） | `entities.py`：`confidence = _RANK_CONFIDENCE[source_rank]` —— **confidence 是来源分级的纯函数**；`access_count` 只在 `core.py` 读出、**不参与任何置信/排序** | 原则**已实现**，但**只写在注释里、没有闸门** ⇒ **本单补了一道守卫测试**（见 §6） |
| 2 | canonical 内容 + **稳定块标识** + 不可变修订 + 确定性物化 | `capture.py::compute_observation_content_hash` + `find_by_observation_hash`（内容哈希去重前置查询） | **同源但粒度更粗**（我们做**文件/观测级**哈希，上游做**块级**身份 + 修订历史）⇒ 若要更细粒度，**可借"块级身份"这一条**，但那是独立改造，不是本候选的独有价值 |
| 3 | **"Measure behavior"**：可复算证据、replayable evidence、failure-oriented fixtures | `reports/*.json` 的产物入库纪律；工单245/246 的「真跑证据 + 逐位一致」判据 | **同宗**，仓内已执行得更严 |

⇒ **可借的三条里，两条已在仓内实现、一条是独立改造方向**；
**本候选没有"只有它有"的设计**。

## 6. 结论与许可边界

**建议：不立项（观察档）**，理由三条，每条有实测支撑：

1. **能力无缺口**：上游 5 项自述能力，仓内 5/5 已覆盖（§4 表，逐项带文件证据）；
2. **设计无独有**：三条可借主张里两条已实现、一条属独立改造（§5 表）；
3. **成本收益倒挂**：★=1 / fork=0（与本目录最低候选差 3~4 个数量级）＋ 166 MB 体积
   ＋ 需 CMake/C++17 工具链 ＋ **5 个 submodule**（hnswlib/libmdbx/simdcomp/zstd）
   —— 为「已被覆盖的能力」引入这样一条依赖链不划算。

**唯一增量已落地**：把 §5 条 1 那条原则（「检索频次 ≠ 真值」）**从注释升级为闸门** ——
`tests/test_memory_evidence_rule.py`：
- 静态守卫：`access_count` 在整个 `mcpserver/` 里**只允许出现在只读展示路径**（当前 = `core.py` 两处），
  一旦有人把它接进置信/排序表达式即红；
- 动态守卫：`confidence` 必须是 `source_rank` 的**纯函数**，且 provenance 必须同时带 `origin_rank` 可对账。

**许可边界**：**MIT** ✓（理论可引码）。但本卡**未读源码、未 clone**；
素材 = GitHub API 元数据 + 目录结构 + 文件体积分布 + README 实读。
若日后要评估 §5 条 2（块级身份），须先做**源码级复核**（那时才 clone 或按路径取文件）。
