# graph-memory-starter 对照报告 —— 「嵌入式数据库替代向量库」路线评估

> 工单202 任务三落地（GitHub 扫货 10-05 日报 Top1）· 2026-10-06 · **只读源码对照，不改任何在线路径**
> 上游：`Glitch-Cat-Club/graph-memory-starter`（**★234 MIT**，create 2026-08-16 / push 2026-08-30，已于本次 API 实核）
> 对照件：`adoresever/graph-memory`（**★637 MIT**，push 2026-10-01，DSH 插件形态）
> 分工声明：hindsight（★45945 MIT，报告 2026-09-25）管**提取**；本件评估**存储/查询**层。

## 0. 结论摘要

**判定：不替代向量库；建议以「图谱层 + 向量层」双通道形态融合，且先走影子模式。**

理由一句话：starter 的纯图路线（零向量、零模型调用）解决的是**词表封闭、实体可枚举、多跳链式**的
查询；NEKO 会话记忆的真实负载里**模糊语义召回（"之前聊过类似的"）仍是主流量**，正是向量层不可让渡的部分。
两者不是替代关系，是**同一条检索链上的两段**——adoresever 的生产形态（query-first 向量排序 + FTS 兜底 +
图节点导航到源 Q/A）已经给出了这个融合的正确形状。

**与现有设计的关系**：本仓 `docs/memory_maas-design-spec.md`（2026-08-29）早已提出
"跨 session 记忆融合应从向量拼接升级为实体图谱遍历"——本报告为该设计补上**可运行的最小实现参照**
（starter）与**生产级插件参照**（adoresever）。

## 1. 源码解剖

### 1.1 starter：最小教学标本（54 文件，一天可读完）

**核心就是三张表**（`src/schema.sql`，全文 353B）：

```sql
CREATE TABLE entities  (id TEXT PRIMARY KEY,   -- uuid5(type + normalised name)
                        name TEXT, type TEXT, description TEXT, source_doc TEXT);
CREATE TABLE relations (source_id TEXT, target_id TEXT, predicate TEXT, source_doc TEXT);
CREATE TABLE aliases   (entity_id TEXT, alias TEXT);
```

| 机制 | 实现（file） | 关键设计点 |
|---|---|---|
| **建图** | `src/build_graph.py:14-17` | `uuid5(NAMESPACE_OID, f"{type}:{normalise(name)}")` **内容寻址**——同名实体跨文档自动合并，"No ML, no lookup"；两遍扫描（先节点后边），**端点解析不到的边跳过并打印**（不猜） |
| **召回** | `src/recall.py:16-33` | `WITH RECURSIVE walk` **双向**遍历（`ON w.entity_id IN (r.source_id, r.target_id)`），hops 默认 3；只取 walk 内两端都在的边，按最小深度 `near` 排序 top_k=8 |
| **种子** | `src/recall.py:56-64` | 问题文本中命中实体 name/alias 者（正则 `\b` 词边界）——**纯确定性，零模型调用** |
| **注入** | `src/recall_hook.py` | Claude Code UserPromptSubmit hook → `additionalContext`（三元素铺成文本 + `where:` 段带实体 description） |
| **提取** | `digest/session_end.py` 等 | 会话结束蒸馏成 note；**只保留用户的话+回复，工具调用/结果/文件转储/thinking 在模型读到之前就被丢弃（code 保证，非配置）** |
| **A/B 对照** | `corpus-before/`(12 非结构化) vs `corpus/`(8 建模) | 同一问题集在两套语料上的表现对照——**方法学可借鉴** |

**建模约束（写死）**：封闭词表——实体 PERSON/ROLE/POLICY/PROCESS/DOCUMENT；
关系 approved_by/held_by/delegates_to/part_of/references。
**失败语义**：词表外 → `"no memory matches"`（README 测试用例第 5 条明确要求**大声失败、绝不猜**）。

**它还自带 RAG 对照路线**（`rag/`）：fastembed + bge-small-en-v1.5（本地 67MB 384 维），
缺 fastembed 时**降级为关键词检索并明说**。README 的取舍建议原文：
> "Start with rag/. Move up when your questions chain facts across documents and you are willing to model for it."

**它自己的边界**（对 NEKO 场景最关键）：关系是**固定词表**，超出即失败；需**先做显式建模**，
不适合"完全自由、快速变化的笔记库"。

### 1.2 adoresever/graph-memory：生产级 DSH 插件（128 文件）

| 维度 | 事实（PRODUCT.md / dist/src 结构） |
|---|---|
| 宿主 | DeepSeek Harness（主）/ OpenClaw（兼容） |
| 存储 | 本地 SQLite：**图 + message provenance + revisions + vectors**（四合一） |
| 检索 | **query-first 向量排序 + FTS 兜底**；图节点导航到**精确源 Q/A** |
| 上下文接管 | 保留最近 N 轮（可配置）；**移除已完成 reasoning/tool traces**，但保留宿主不可变事件日志 |
| 提取 | 只抽 **用户问题 + 最终可见答案**，严格结构化契约；**19/20 成功，无效输出隔离（fail closed）** |
| 注入 | **自动召回**，前台模型请求前完成（agent 不需要调记忆工具） |
| 图算力 | pagerank / community / maintenance（`dist/src/graph/*`）——但原则明写 **"检索相关性优先于图中心性"** |
| 验证 | 20 文件 123 测试；`benchmarks/dsh-context-takeover/` 可复现 20 轮编码场景 |

**它的原则清单本身就是给 NEKO 的验收口径**：
上下文必须有界 / 压缩不得破坏可检索源证据 / **坏提取 fail closed，前台会话 fail open** / 指标必须可复现且口径明确。

## 2. 与 NEKO 记忆层现状对照

**现状**（据 `docs/Memory-MaaS-Research-v1.md` + `memory_maas-design-spec.md`）：
SPEC-03 五件套（`NEKO/N.E.K.O/memory/`，**纯标准库**：hybrid_search / index_cards / lineage /
lifecycle / compaction_v2）已落地，但记忆是 **blob 级**——卡片是整段文本 + 向量，**无实体类型、无关系、
无显式生命周期元数据**；`memory_maas` 设计稿已提出实体图谱方向但仍是设计稿。

| 维度 | NEKO 现状（SPEC-03 + memory_maas 设计） | starter | adoresever | 研判 |
|---|---|---|---|---|
| 存储 | SQLite（stdlib） | SQLite 三表 | SQLite 图+向量+溯源+revisions | **同栈零冲突**——加表即可，不引依赖 |
| 身份 | 卡片 id（blob） | uuid5(type+name) 内容寻址 | 图节点 + 源消息 id | starter 方案可直接借用，成本最低 |
| 检索 | 向量混合（hybrid_search） | 正则种子 + 递归 CTE（零向量） | 向量优先 + FTS 兜底 + 图导航 | **adoresever 形态 = NEKO 应走的路** |
| 抽取 | 无实体抽取 | LLM 按固定 prompt 抽 nodes/edges/aliases | LLM 抽 Q/A 契约 + 隔离坏输出 | 提取交 hindsight（已有分工），图只管存查 |
| 注入 | 卡片压缩注入 | prompt hook 注入 | 自动召回（前台请求前） | 与现有 compaction_v2 注入路径同构 |
| 失败语义 | 未明确 | **词表外大声失败** | **fail closed 提取 / fail open 会话** | **必须照抄**：这是可信度红线 |
| 宿主侵入 | — | Claude Code hook | DSH/OpenClaw 插件 | NEKO 铁律：**只动包装层** |

## 3. 核心问题：「嵌入式数据库替代向量库」能不能成立？

把命题拆成三问，逐条给判据：

1. **确定性需求**（"谁批准了那笔退款"这类需要精确、可解释、可审计的链式回溯）
   → **纯图完胜**：零模型调用、零向量、毫秒级、路径可打印（starter `recall.py` 的 `near` 深度排序）。
   NEKO 场景对应：决策归属、任务交接链（"上次那个 handoff 是谁给的"）。
2. **模糊语义需求**（"我们之前聊过的那个类似问题"）
   → **向量不可替代**：图种子依赖字面/别名命中，措辞一变即失联（starter 自己的 RAG 路线就是为此存在）。
   这是 NEKO 会话记忆的**主流量**，也是"替代"一词不成立的根本原因。
3. **开放域 vs 封闭词表**
   → starter 的固定词表在 NEKO 开放对话下命中率会很低（它的第 5 条测试用例正是演示"词表外必须无匹配"）。
   NEKO 若走图路线，**词表必须可演进**——这正是 adoresever 用"LLM 抽取 + 契约 + 隔离"解决的问题。

**结论**：所谓"替代"只在第 1 类查询上成立；正确形态是**双通道**——
向量通道保召回（模糊、开放域），图通道保精度（链式、可解释），
**检索相关性优先于图中心性**（adoresever 原则，直接采纳）。

## 4. 与 hindsight 的分工（已授粉件的边界）

| 件 | 职责 | 边界 |
|---|---|---|
| hindsight（★45945，2026-09-25 授粉） | **提取**：从会话中抽取事实/教训（"提取器"） | 不负责存储形态与查询路径 |
| graph-memory-starter（本件，★234） | **存储/查询**：三表 + 递归 CTE + 注入钩子（最小范式） | 不做提取（依赖外部 extraction/*.json） |
| adoresever/graph-memory（★637） | **完整插件**：提取+存储+检索+上下文接管（端到端形态） | 宿主绑定 DSH/OpenClaw，需移植 |

→ 三者不重叠，**hindsight 抽取的产物正好可以喂给图存储层**（starter 的 `extraction/*.json` 就是那个接口形状）。

## 5. 建议（本轮不做在线改动）

**不融合进在线路径；建议立一个影子模式试点（P1，独立工单）**：

1. **落点**：`mcpserver/` 或 `apiserver/` 侧新增独立模块（**不动 `NEKO/N.E.K.O/memory/` 上游**，守铁律），
   读 NEKO 已有会话数据（只读），用 starter 的三表 schema 建一份**影子图**。
2. **评估**：拿 NEKO 真实历史会话，构造两类问题集（多跳链式 / 模糊语义），
   分别测「纯图」「现有向量」「双通道」的命中与耗时——**用数字决定是否接入**，不靠感觉。
3. **词表策略**：起步用 starter 的封闭词表 + 失败大声报；若命中率不足，上 adoresever 式
   LLM 抽取 + 契约 + 坏输出隔离（fail closed）。
4. **验收口径照抄 adoresever 原则**：上下文有界 / 压缩不毁源证据 / 检索相关性优先 / 指标可复现。

## 6. 未决项

1. NEKO 会话数据的**可读性与脱敏边界**未验证（影子建图前须确认数据获取路径合法合规）。
2. 词表演进机制（自动扩展 vs 人工维护）未定——决定引入 adoresever 式抽取的必要性。
3. 影子试点的算力/时间预算未估（图构建是一次性批处理，召回是每轮 hook，成本模型待实测）。
4. starter 是**示例项目**（create→push 仅 14 天，无 issue/发布），工程化程度低——
   **只借设计与 schema，不直接依赖其代码**。
