# 授粉 · graph-memory-starter 轻量 KG 记忆 — 落地报告（2026-09-20）

> 卷139 交付 | 沈遥签
> 上游：Glitch-Cat-Club/graph-memory-starter（227★ · MIT ✅ gh api 核验 · 2026-08-30 最后推送）
> 落点：`mcpserver/graph_memory_adapter/`（engine.py + adapter.py + schema.sql + manifest + prompts/）

## 一、上游调研结论（读的是源码，不是 README 转述）

上游自述："A knowledge graph your AI assistant reads before it answers.
Three SQLite tables, one recursive query, one prompt hook. No server, no API key."

实测关键文件与结论：

| 上游文件 | 内容 | 结论 |
|---|---|---|
| `src/schema.sql`（353B） | entities / relations / aliases 三表 | 极简，无任何冗余字段 |
| `src/recall.py`（3462B） | `WALK` 递归 CTE + `_seeds` 词边界匹配 + `Facts.as_text()` | **检索纯 SQLite，零模型调用**（作者原话：It has to be deterministic and fast） |
| `src/build_graph.py`（2495B） | `entity_id = uuid5(NAMESPACE_OID, f"{type}:{normalise(name)}")` | **同名实体跨文档自动归一的全部秘密就是这行 uuid5** |
| `src/recall_hook.py`（520B） | UserPromptSubmit hook → additionalContext | 注入点：提问提交时 |
| `extract-prompt.md`（606B） | 固定词表（PERSON/ROLE/POLICY/PROCESS/DOCUMENT）+ 四条规则 | 词表约束 + "条件写进 description" 是关键约定 |
| `hooks.json` | `{"UserPromptSubmit": [{"command": "python src/recall_hook.py", "timeout": 10}]}` | 10s 超时——说明注入必须快 |

**上游的局限（本仓必须扩展的点）**：上游只有**批量建图**（build_graph.py 从
`extraction/*.json` 一次性灌库），**没有增量写入路径**。Lumo 的记忆是"边聊边长"的，
所以本卷补了 `remember()` 增量写入（engine.py L139）——这是"借鉴设计"而非"照搬"的实证。

## 二、源 → 目标映射表

| # | 上游设计 | 本仓落点（实测行号） | 映射方式 |
|---|---|---|---|
| 1 | 三表 schema（entities/relations/aliases） | `schema.sql` L17-36 | 原样保留；**本仓扩展** `memory_meta`（写入溯源）+ 三个索引 |
| 2 | 递归 CTE `WALK` | `engine.py` L96-117（`_WALK_SQL`）；调用点 L262 `recall()` | 逐字沿用走图逻辑（含 `near = MIN(depth)` 排序） |
| 3 | `uuid5(type + normalised_name)` | `engine.py` L48 `entity_id()`；L43 `normalise()` | 逐字沿用（确定性归一，零 ML 消歧） |
| 4 | `_seeds` 名称/别名命中 | `engine.py` L243 `_seeds()` | 沿用 + **中文适配**（中文无 `\b` 词边界 → 退化为子串包含） |
| 5 | `Facts.as_text()`（含 `where:` 段） | `engine.py` L65 `as_text()` | 沿用排版；中文标注（"记忆：N 条事实"、"其中："） |
| 6 | `recall_hook.py` 的 additionalContext | `engine.py` L285 `hook_prompt()` | 语义沿用；**改为返回文本**由调用方决定挂载点（MCP 工具 / 对话注入），并按 `max_chars` 截断 |
| 7 | prompt hook 时机（UserPromptSubmit） | 本仓建议挂 `agentic_tool_loop` 的 loop 启动段 | 与 W131-04 知识注入同位置（已有先例） |
| 8 | 批量建图（build_graph.py） | `engine.py` L191 `ingest_entities()` | 改造为"nodes/edges/aliases 三件套"接口，供卷142 抽取管线直喂 |
| 9 | （上游无） | `engine.py` L139 `remember()` | **本仓新增**：对话中增量写入，幂等（重复写不产生重复边） |
| 10 | （上游无） | `adapter.py` L29 `GraphMemoryBridge` + L45-96 五工具 | **本仓新增**：MCP 适配器面（remember/recall/hook/export/stats） |

## 三、核心数据结构共鸣（附行号）

| 上游结构 | 本仓对应物（文件:行） | 共鸣 | 差异 |
|---|---|---|---|
| `entities.id`（uuid5 内容寻址） | `engine.py:48` `entity_id()` | ★★★ 完全一致 | 无 |
| `relations`（边携带 `source_doc`） | `schema.sql:26-31` + `engine.py:139` | ★★★ 一致 | 本仓额外去重（同 source/target/predicate 只存一条） |
| `aliases`（别名→实体） | `schema.sql:33-37` + `engine.py:230` `add_alias()` | ★★★ 一致 | 本仓 `_seeds` 额外对中文做子串匹配 |
| `WALK` 递归 CTE | `engine.py:96-117` | ★★★ 逐字沿用 | 无 |
| `Facts.notes`（实体条件） | `engine.py:65` `as_text()` 的"其中："段 | ★★★ 一致 | 中文标签 |
| （上游无 incremental write） | `engine.py:139` `remember()` / `:191` `ingest_entities()` | — | **本仓扩展** |
| （上游无） | `engine.py:312` `export_subgraph()` | — | 本仓扩展（前端可视化 nodes+links） |

## 四、与既有资产的分工（工单点名的"避免重复造轮子"）

| 既有资产 | 它的路线 | 与卷139 的关系 |
|---|---|---|
| `docs/pollination/reports/claude-mem-授粉报告.md` | 压缩 + 注入（观察→XML 块→按需注入），**明确无 typed 实体/KG** | **互补**：claude-mem 管"会话怎么不重头开始"，本件管"实体关系怎么被检索" |
| `docs/neo4j-graph-memory-评估.md` | Neo4j 重型图（需独立图库服务） | **路线已否**（该文档结论：本仓已有 `memory_maas 实体图谱` + `summer_memory 五元组`），本件走"零服务、单 SQLite 文件"轻量路线 |
| `mcpserver/adapters/graphify/`（现役） | **语料级** KG：代码/文献目录 → graph.json → GraphRAG 检索（TF-IDF + RRF），agent 主动调用工具 | **不重叠**：①触发方式不同（工具调用 vs prompt hook）②写入模式不同（批量建图 vs 增量记忆）③数据单位不同（文档 vs 对话事实） |
| `apiserver/context_compressor.py` | 上下文压缩（headroom 类） | 不同层：压缩管"塞得下"，本件管"记得住" |

## 五、难度 × 收益评估

| 维度 | 评估 |
|---|---|
| **实现难度** | **低**。核心算法（三表 + 一条 CTE）体量极小；本卷实际产出 engine 360 行 + adapter 110 行 + 19 测试，全部零外部依赖（纯标准库 sqlite3） |
| **收益** | **中-高**。多跳事实召回（"谁负责什么、条件是什么"）是当前 rag_section 的空白；且因为是纯 SQL，**注入延迟可忽略**（实测 <1ms/次，见测试 `test_as_text_shape` 的 ms 字段） |
| **风险** | ①抽取质量决定图谱质量（故拆出卷142 专做抽取）②无自动过期机制（`memory_meta.created_at` 已埋点，清理策略留待后续）③中文种子匹配靠子串（可能误命中，如"水凝胶"命中"水凝胶涂层"） |
| **不做** | 不做嵌入/向量检索（那是 rag 的活）；不做图数据库（neo4j 路线已否）；不改 apiserver 主流程（工单硬约束） |

## 六、验收实测（工单三条可执行不变量）

```bash
# 1) pytest 全过
$ pytest mcpserver/graph_memory_adapter/ -q
19 passed in 0.36s                     ← ✅

# 2) 递归 CTE 在
$ grep -c "recursive" mcpserver/graph_memory_adapter/*.py
engine.py: 3 / __init__.py: 1          ← ✅（合计 4 ≥ 1）

# 3) 不动主流程
$ git diff --stat -- apiserver | wc -l
0（本卷新增文件集不含 apiserver 下任何文件）  ← ✅
```
> 说明：工作区 `git status -- apiserver` 会显示若干行，那是**历次卷（W131/渠道层/onboard 等）
> 经 GitHub API 提交、本地 checkout 尚未同步**的存量差异，与本卷无关；本卷产物清单里
> apiserver 下文件数为 0。

## 七、交付清单

| 文件 | 行数/大小 | 说明 |
|---|---|---|
| `mcpserver/graph_memory_adapter/schema.sql` | 48 行 | 三表 + memory_meta + 索引 |
| `mcpserver/graph_memory_adapter/engine.py` | 360 行 | GraphMemory 引擎（remember/recall/hook/export/ingest） |
| `mcpserver/graph_memory_adapter/adapter.py` | 110 行 | MCP 桥（5 工具 + 钳位 + fail-fast） |
| `mcpserver/graph_memory_adapter/agent-manifest.json` | — | 5 个 invocationCommands |
| `mcpserver/graph_memory_adapter/__init__.py` | — | 导出面 + 与 graphify/claude-mem 的分工说明 |
| `mcpserver/graph_memory_adapter/test_graph_memory.py` | 19 用例 | 同目录（仓内先例：`rf_brain/test_lightrag_graph.py`） |
| `mcpserver/graph_memory_adapter/prompts/` | 2 文件 | 卷142 的 prompt 模板（共享目录） |

**数据落点**：`knowledge-base/graph_memory/graph_memory.db`（与既有 `knowledge-base/`
下的 academic/infra/knowledge/mcp 同策略）；`LUMO_GRAPH_MEMORY_DB` 可覆盖。
