# 工单 247 完工报告 · LimiNode/agent-memory-cpp 调研（并入 214 目录 · **不立项**）

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `ea1c0258ea20`（工单245 合并点）
> 工单来源：`TRAE_WORKORDER_PROMPT_AGENT_247.md`（`cron_to_workorder` 自动草稿 **28 行** → 工单244k 晋升）
> 上游：**[LimiNode/agent-memory-cpp](https://github.com/LimiNode/agent-memory-cpp)**（MIT，★ **1** / fork **0**，C++17）
> 交付：**3 个文件（2 新增 + 1 修改）、0 个既有文件改动**（详见 §0）

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增 | `docs/fusion-candidates-2026-10/LimiNode-agent-memory-cpp.md`（调研卡，六节格式）<br>`tests/test_memory_evidence_rule.py`（守卫闸门，**7 用例**）<br>`reports/workorder247_liminode_2026-10-16.md`（本报告） |
| 修改 | `docs/fusion-candidates-2026-10/00-汇总.md`（**纯追加**"第三梯队"一节，diff 无删改） |
| 立项结论 | **不立项**（观察档 P3+），三条理由每条带实测 |
| 测试 | `pytest tests/test_memory_evidence_rule.py` ⇒ **7 passed**；`ruff` 全绿 |

## §1 · 工单 §4 的填实（草稿三项全空，由本单定义并在此记录）

| §4 项 | 本单结论 |
|---|---|
| **PoC 边界与验收标准** | **边界**：本单是**调研级**（照 214 目录口径：调研不动手、不自动立项）。**素材边界**：只读 GitHub API 元数据 + 目录结构 + 文件体积分布 + README 实读 —— **不 clone、不读源码**（仓库 166 MB，与目录既有纪律一致）。**验收**：① 出卡符合目录既有**六节格式**（对齐 214）；② `00-汇总.md` 追加第三梯队；③ 结论里的「能力已覆盖」**逐项带文件证据且在 main 上可访问**；④ 上游三条可借主张逐条给出仓内实指与处置。 |
| **与现有模块的耦合点** | **工单 §1 的「把 toolkit 能力接入 agent 线」在能力层面无事可做** —— 上游自述 5 项能力，仓内 **5/5 已有实现**（`rag/rag_service.py` + `chunk_splitter`/`document_parser`、`mcpserver/memory_maas/hybrid_search.py`、`mcpserver/graph_memory_adapter/kg_extract.py`、`rag/vault_indexer.py`、`rag/embedding_engine.py` + `apiserver/local_embedder.py`）。**8 个被引路径全部实测 200 OK**。与本目录既有 9 张卡：不可同档比较（★ 区间 1866~50147 vs 本候选 **1**，差 3~4 个数量级）⇒ 单独列"第三梯队"。 |
| **是否与已发工单重复** | **不重复**（`LimiNode` 在根目录 50 个工单里零命中，仅本单自身的草稿 `research/workorder_drafts/auto_2026-10-14/WO-247-*.md` 命中）。与 **214** 的关系不是重复而是**归属**：本卡并入 214 的调研卡目录（这是 214 的口径），不另立目录、不另立 SPEC。 |

## §2 · 设计决策

### 2.1 为什么"能并入 214"却是**观察档**
214 的候选要能进 P0/P1/P2，隐含前提是**同量级可比**。本候选 ★=1 / fork=0，而目录既有 9 张卡
是 1866~50147 —— 差 3~4 个数量级。把它塞进同一个 P 档位排序，等于让**一个没人用的库**和
**上万星的项目**争同一个名额 ⇒ 单独列第三梯队，只作观察。

### 2.2 结论是「不立项」，但**唯一增量照样落地**
卡片 §5 逐条查了上游三条工程主张：
① **"retrieval frequency does not become proof of truth"** —— 仓内**已实现**（`confidence` 是
`_RANK_CONFIDENCE[source_rank]` 的纯函数、`access_count` 不参与置信/排序），**但只写在注释里、没有闸门**；
② canonical 内容 + 稳定块标识 + 不可变修订 —— 仓内同源但**粒度更粗**（观测/文件级哈希 vs 块级身份），
属**独立改造方向**；
③ "Measure behavior"（可复算证据）—— 同宗，仓内执行得更严（245/246 的"真跑证据 + 逐位一致"）。

⇒ **①是唯一"已实现但无守卫"的**，因此把注释升级成闸门（`tests/test_memory_evidence_rule.py`），
两道：
- **静态守卫**：`access_count` 在整个 `mcpserver/` 里**只允许出现在白名单的只读展示路径**
  （当前 = `core.py` 两处）；一旦被接进置信/排序表达式即红。
- **动态守卫**：`confidence` 必须是 `source_rank` 的纯函数，且 provenance 同时带 `origin_rank` 可对账。

> 这一条正是"调研也能产出增量"的样子：**不立项 ≠ 什么都不做**。

## §3 · 边界（如实标注，不粉饰）

| 项 | 说明 |
|---|---|
| 未读源码 | 本卡**不 clone、不读源码**；内容模型的具体编码方式**未给出**（§2 明确标注为素材边界），若日后评估"块级身份"须先做**源码级复核** |
| 上游能力清单的性质 | README **自认**其能力清单是"目标模型"（"it does not mean that every item is implemented today"）⇒ 本卡引用时**只当作方向**，不当现状 |
| 体积构成是实测量 | 166 MB 里源码仅 ~11 MB（`.py` 7.92 + `.cpp/.hpp` 3.20），大头是基准产物（`.bin` 124.71 MB / `.json` 78.37 MB，其中单个 `frontier-v2.raw.json` = 73 MB） |
| 许可 | **MIT** ✓（理论可引码），但本单未引任何代码 |

## §4 · 复现

```bash
python -m pytest tests/test_memory_evidence_rule.py -q     # 7 passed
ruff check tests/test_memory_evidence_rule.py

# 元数据（★/fork/许可/体积）：
#   GET https://api.github.com/repos/LimiNode/agent-memory-cpp
# 被引 8 个仓内路径的存在性：GET /contents/<path>?ref=main ⇒ 全 200
```

产物：`docs/fusion-candidates-2026-10/LimiNode-agent-memory-cpp.md`（卡）、
`docs/fusion-candidates-2026-10/00-汇总.md`（第三梯队追加）、`tests/test_memory_evidence_rule.py`（闸门）
