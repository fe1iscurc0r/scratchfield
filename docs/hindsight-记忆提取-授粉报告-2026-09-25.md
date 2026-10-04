# hindsight 记忆提取管线 — 调研 + 授粉报告（2026-09-25）

> 卷152（MCP线）· 落盘：砚 · 状态：**SPEC/调研（未写实现代码）**
> 对象：[`vectorize-io/hindsight`](https://github.com/vectorize-io/hindsight)（**MIT**，29418★，gh api 实测 2026-09-25，非 archived，主语言 Python）
> 防重复对照：本仓 **`mcpserver/memory_maas`**（记忆五件套/RRF 混合检索）与 **`mcpserver/graph_memory_adapter`**（卷139 轻量 KG 记忆：抽取管线 + schema.sql）——本卷走**「学习型记忆提取」**角度，不重复 KG 路线。
> 匿名铁律：不写真实姓名。

## 0. 结论先说

hindsight 的记忆管线可归纳成**「抽取 → 归并 → 反思 → 合并/保留」**四段，其中对我们最有价值的是**两处**：

| 最有价值的两处 | 位置（实测行号） | 为什么值得授粉 |
|---|---|---|
| **抽取阶段带结构化 schema + 时间推断** | `retain/fact_extraction.py:4`、`:23`、`:83` | 抽取结果**强类型**（不是自由文本），且"LLM 没给时间就从文本推" |
| **归并阶段用 LLM 做 merge/keep 决策** | `consolidation/consolidator.py:163-167`、`:203`、`:210` | 冲突消解不是"覆盖"，而是**同义合并 / 保留并存**（措辞不同但事实相同 → merge） |

**本仓现状差距**：`memory_maas` 有**检索**（RRF 混合）但**没有抽取/归并**；`graph_memory_adapter` 有**抽取**（`kg_extract.py`）但**没有冲突消解与遗忘策略**。
⇒ 授粉优先级：**先补归并（merge/keep 决策）**，再补结构化抽取 schema。

## 1. hindsight 实测事实（源码行号引用）

### 1.1 抽取（retain/fact_extraction.py，3627 行）

行号索引：`L4`、`L23`、`L40`、`L83`、`L93`

| 位置 | 内容 |
|---|---|
| `fact_extraction.py:4` | 模块定位原文：*"Extracts semantic facts, entities, and temporal information from text."* —— **三样一起抽**（事实/实体/时间） |
| `fact_extraction.py:23` | `from ..structured_output import provider_json_schema, strict_json_schema` —— **强类型结构化输出**（不是让模型自由发挥） |
| `fact_extraction.py:40` | `def _extract_map_entities(entity_obj: dict, ...)` + `:47` "Recursively extract key:field:value entity strings" —— 实体按 **key:field:value** 递归展平 |
| `fact_extraction.py:83` | `def _infer_temporal_date(fact_text: str, event_date: datetime | None) -> str | None` —— **LLM 未给 `occurred_start` 时从文本推断时间** |
| `fact_extraction.py:93` | `fact_lower = fact_text.lower()` —— 归一化后做时间线索匹配 |

**管线组成**（`engine/retain/` 目录实测）：
`fact_extraction.py`（抽取）→ `entity_processing.py`（实体）→ `fact_storage.py` / `chunk_storage.py`（落库）→ `embedding_*.py`（含 **`embedding_coalescer.py`**：嵌入批处理合并）；
另有 `attachment_*`（附件内容）与 `bank_utils.py`（**bank = 记忆库分仓**）。

**触发入口**：`hindsight_api/api/` 层（`http.py`、**`mcp.py`**、`admission.py`、`observability.py`）
—— 即**按请求驱动**（HTTP/MCP 调用进管线），不是无条件的"每轮自动"。
（本卷**未逐行确认**是否存在后台定时触发 —— 见 §5 未决项。）

### 1.2 归并/冲突消解（consolidation/consolidator.py，3763 行）

行号索引：`L69`、`L126`、`L137`、`L163`、`L166`、`L167`、`L175`、`L182`、`L203`、`L210`、`L216`

| 位置 | 内容 |
|---|---|
| `consolidator.py:69` | `async def _gather_or_cancel(coros)` —— 并发聚合（一批候选一起处理） |
| `consolidator.py:126` | `def _norm_obs_text(text)` —— **归一化用于去重比对** |
| `consolidator.py:137` | `def _duplicate_create_target(...)` —— 重复项的处理目标 |
| `consolidator.py:163` | `class _DedupDecision(BaseModel)`；`:166` `action: Literal["merge", "keep"] = "keep"`；`:167` `text: str = ""  # the synthesized merged observation (when action == "merge")` |
| `consolidator.py:175` | `if normalized in {"merge", "keep"}:` —— 决策值**白名单校验**（防模型乱输出） |
| `consolidator.py:203` | prompt 里给的输出样例：`{{"action": "merge", "text": "...", "reason": "..."}}` |
| `consolidator.py:210` | 判定原文：*"If they assert the SAME fact (wording aside), set \"action\" to \"merge\" and provide \"text\": a …"* |
| `consolidator.py:216` | `def _dedup_active(config)` —— **可配置开关**（去重不是无条件开） |

**读法**：冲突消解的口径是 **merge（合成一条） / keep（并存）** 二选一 + 必须给 reason；
"措辞不同但断言同一事实 → merge"，**不是**简单的时间戳覆盖（软删除/遗忘策略见 §1.3）。

### 1.3 存储结构（由 alembic 迁移文件名实录）

| 迁移（部分） | 揭示的结构 |
|---|---|
| `…_add_consolidated_at_to_memory_units.py` / `…_add_consolidation_failed_at_to_memory_units.py` | 主表 `memory_units`，带 **`consolidated_at` / `consolidation_failed_at`**（整合状态可查、失败可重试） |
| `…_add_memory_links_bank_id_index.py` / `…_memory_links_deferrable_fk.py` | `memory_links`（记忆间关系）+ `bank_id`（分仓） |
| `…_observation_history_drop_memory_units_fk.py` | **`observation_history`**（观察的历史版本，FK 解耦） |
| `…_learnings_and_pinned_reflections.py` | **`learnings`** + **`pinned_reflections`**（学到的结论 + 钉住的反思） |
| `…_add_reflect_response_to_reflections.py` | `reflections` 存 `reflect_response` |
| `…_add_gin_index_source_memory_ids.py` | 来源记忆 id 的 **GIN 索引**（多值检索） |

⇒ 存储是**混合**：结构化表（记忆单元/链接/观察历史）+ 向量（`search/` 引擎、`temporal_extraction.py`）——不是纯向量、也不是纯图。

## 2. 对照本仓（差距逐项）

| 能力 | hindsight | 本仓现状（实测） | 差距 |
|---|---|---|---|
| 结构化抽取 schema | `fact_extraction.py:23`（json schema 强约束） | `mcpserver/graph_memory_adapter/kg_extract.py` 有抽取 | 缺**强类型 schema + 时间字段** |
| 时间推断 | `fact_extraction.py:83`（缺时间就从文本推） | 五元组里时间未统一 | **完全缺** |
| 检索 | `engine/search/*` + GIN 索引 | `memory_maas/hybrid_search.py:271 def hybrid_search`（RRF） | 相当（我们已有混合检索） |
| 冲突消解 | `consolidator.py:163-210`（merge/keep + reason） | 无 | **完全缺** |
| 历史版本 | `observation_history` 表 | 无 | **完全缺** |
| 反思/钉住 | `reflect/agent.py` + `pinned_reflections` | 无 | 缺（NEKO 侧有"反思"概念，但不在本仓记忆层） |
| 分仓 | `bank_id`（+ 索引） | 无（单库） | 缺（多角色/多项目时会需要） |
| MCP 面 | `api/mcp.py` | 本仓 `mcpserver/` 已有 MCP 总线 | 相当 |

## 3. 三大件

### 3.1 源 → 目标映射表（hindsight → 本仓 → 授粉方式 → 收益）

| hindsight 组件 | 本仓落点 | 授粉方式 | 收益 |
|---|---|---|---|
| `fact_extraction`（结构化 schema） | `mcpserver/graph_memory_adapter/kg_extract.py` | **改造**：抽取输出改走 json schema（含 `occurred_start`） | 下游不用猜字段 |
| `_infer_temporal_date`（`fact_extraction.py:83`） | 同上（新增小函数） | **照搬思路**：缺时间就推，推不出留空 | 时间线可用 |
| `consolidator` 的 merge/keep（`consolidator.py:163-210`） | `memory_maas/hybrid_search.py` 之上新层 | **旁路**：写前先去重表决，写后落变更表 | 记忆不再自相矛盾 |
| `observation_history` | `memory_maas` 存储侧 | **旁路**新表 | 可回溯"这句话怎么变成这样的" |
| `bank_id` 分仓 | `memory_maas` | 加列 + 索引 | 多角色/多项目隔离 |
| `pinned_reflections` | 本仓 ELN/记忆层 | 参考（本仓无反思概念） | 长期设定不丢 |

### 3.2 结构共鸣（附行号）

1. **"合并而非覆盖"**：`_DedupDecision.action ∈ {merge, keep}`（`consolidator.py:166`）+ 合成文本字段（`:167`）
   ↔ 本仓五元组目前是**追加**（旧的仍在，但无冲突判定）⇒ 引入 merge 后，**同一事实只留一条更准确的**。
2. **"整合状态显式化"**：`consolidated_at` / `consolidation_failed_at`（迁移文件名）
   ↔ 本仓记忆写入没有"整合"这个状态 ⇒ 建议新增 `consolidation_state`，让失败可重试而不是静默丢。
3. **"归一化再比对"**：`_norm_obs_text`（`consolidator.py:126`）
   ↔ 本仓检索侧的归一化散在查询构造里 ⇒ 抽成公共函数，写入与检索共用同一套归一化。

### 3.3 难度 × 收益表

| 项 | 难度 | 收益 | 档位 |
|---|---|---|---|
| merge/keep 去重表决（写前） | 中 | **高**（记忆一致性） | **立即授粉** |
| 归一化公共函数（写入/检索共用） | 低 | 中 | **立即授粉** |
| 结构化抽取 schema + `occurred_start` | 中 | 高（下游稳定） | **立即授粉** |
| 时间推断（缺则推、推不出留空） | 低 | 中 | **立即授粉** |
| `observation_history` 版本表 | 中 | 中（可解释性） | 暂缓（先有 merge 再谈历史） |
| 分仓 `bank_id` | 低 | 中（多角色场景才有感） | 暂缓 |
| 反思 / 钉住（`pinned_reflections`） | 高 | 中 | 参考（需先有"反思"概念） |

## 4. 与本仓其他工单的衔接

- **卷154（companion durable execution）**：记忆写入的**幂等与变更留痕**与其 `memory_mutations` 思路同源 —— 两卷合并落地可共用一张变更表。
- **卷151 的图谱**：本卷补"提取→归并"，卷151 的 ActGov/LeaseGuard 管"谁能写"；三者拼成记忆写入的完整闸门。

## 5. 未决项与边界

1. **克隆失败改 API 阅读**：hindsight 仓 758MB（4875 文件），本机 `git clone` 未完成 ⇒ 本报告的结论来自 **GitHub Contents/Tree API 读取的关键文件**（行号对应 `main` 分支当时状态），**未跑任何代码**。
2. **触发时机未完全确认**：入口在 `api/`（`http.py`/`mcp.py`）可确认；是否存在后台/定时触发**未逐行证实**，报告中已按"按请求驱动"表述。
3. **`engine/reflect/`（反思）只看了文件名未读实现**（`agent.py`/`delta_ops.py`/`models.py`）—— 本卷重点是"提取+归并"，反思线留待后续。
4. **许可**：MIT（实测），可参考/可引码；但本卷**不引码**（只出方案）。
5. **未做**：任何适配器骨架；授粉方式均为"方案"，落地需另开实现卷。
