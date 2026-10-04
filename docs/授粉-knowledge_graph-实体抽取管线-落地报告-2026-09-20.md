# 授粉 · knowledge_graph 实体抽取管线 — 落地报告（2026-09-20）

> 卷142 交付 | 实验田维护者签
> 上游：rahulnyk/knowledge_graph（4060★ · MIT ✅ gh api 核验 · 2026-08-15 最后推送）
> 落点：`mcpserver/graph_memory_adapter/kg_extract.py` + `prompts/`（与卷139 共享目录，按其工单要求）

## 一、上游调研结论（读的是源码）

上游形态：Jupyter Notebook 为主（`extract_graph.ipynb` 41KB / `ner.ipynb`），
**不是即插即用库**——所以本卷定位"只借 prompt 设计与管线思路"，
可借的核心资产只有两个 Python 文件：

| 上游文件 | 内容 | 借鉴结论 |
|---|---|---|
| `helpers/prompts.py`（3440B） | `extractConcepts()` + `graphPrompt()` 两个 prompt 构造函数 | **核心资产**：两段 prompt 全文已抄进本仓 prompts/ |
| `helpers/df_helpers.py`（2214B） | chunks→concepts→graph 的 DataFrame 管线 + 小写归一 | 管线思路借鉴；**pandas 依赖不借**（本仓走纯 dict，避免为抽取引 pandas） |

**上游两段 prompt 的关键设计**（实测原文）：

1. **`extractConcepts`**：
   - 固定类别词表 `[event, concept, place, object, document, organisation, condition, misc]`
   - 输出带 `importance`（1-5 的相对重要性）——**这是本研究最有价值的字段**：
     它给了下游"该先召回哪条"的排序依据
   - 要求"只抽最重要且**原子化**的概念，必要时拆成更简单的概念"
2. **`graphPrompt`**：
   - **Thought 1/2/3 分步脚手架**（先找术语 → 再找同句/同段配对 → 再定关系词）
   - "Terms that are mentioned in the same sentence or the same paragraph are
     typically related" —— 用共现作为关系候选的启发式
   - 输出 `node_1 / node_2 / edge` 三元组，edge 是"一到两句"的关系描述

**上游的缺陷（本仓修补的点）**：`graphPrompt` **不校验边端点是否在节点清单里**，
也没有去重——同一次抽取里常出现 A→B 的多条重复边和"幽灵节点"边。
本仓补了两道闸（见 §三）。

## 二、源 → 目标映射表

| # | 上游设计 | 本仓落点（实测行号） | 映射方式 |
|---|---|---|---|
| 1 | 固定类别词表 | `prompts/kg-extract-concept.md`（system prompt 逐字保留）+ `kg_extract.py:31` `ALLOWED_CATEGORIES` | 沿用；白名单外的类别**归 misc 不丢弃**（L87 `extract_concepts` 内） |
| 2 | `importance` 字段 | `prompts/kg-extract-concept.md` + `kg_extract.py:87` | 沿用；钳位 1-5（越界取边界值） |
| 3 | Thought 1/2/3 脚手架 | `prompts/kg-extract-relation.md` | 逐字保留三段 Thought |
| 4 | edge 描述性关系词 | `prompts/kg-extract-relation.md` 的关系词建议表（part_of/delegates_to/has_property…9 条） | **本仓扩展**：给出建议词表（非强制），提升跨文档关系词一致性 |
| 5 | 边端点不做校验 | `kg_extract.py:122` `extract_relations()` | **本仓修补①**：端点不在实体清单的边一律丢弃 |
| 6 | 无去重 | 同上 | **本仓修补②**：同一对节点只留一条边（frozenset 去重） |
| 7 | 小写归一（`df_helpers.py`） | `kg_extract.py:173` `normalise_key()` | 扩展：去空白/全角空格/常见标点（中文场景必需） |
| 8 | 无模糊合并 | `kg_extract.py:181` `build_alias_map()` | **本仓扩展**：ASCII 名做 SequenceMatcher ≥0.9 模糊合并；**中文不做模糊**（误合并风险） |
| 9 | （无） | `kg_extract.py:228` `apply_alias_map()` | 本仓扩展：合并后去自环、去重边、描述保留信息更全的那条 |
| 10 | Ollama 本地模型硬编码（`mistral-openorca`） | `kg_extract.py:264` `get_default_llm()` | **改造**：LLM 以 callable 注入 → 测试零 API key 全离线；线上走仓内 LLM 栈 |
| 11 | pandas DataFrame 管线 | 纯 dict/list | 不引 pandas（抽取链路保持零第三方依赖） |

## 三、核心数据结构共鸣（附行号）

| 上游结构 | 本仓对应物（文件:行） | 共鸣 | 差异 |
|---|---|---|---|
| `{"entity","importance","category"}` | `kg_extract.py:87` 返回结构（+`aliases`） | ★★★ | 本仓加 `aliases`（与卷139 别名表直通） |
| `{"node_1","node_2","edge"}` | `kg_extract.py:122` 输出（+端点校验/去重） | ★★★ | 本仓加两道闸 |
| `{"chunk_id": ...}` metadata | `source_doc` 字段（透传到卷139 的 relations.source_doc） | ★★ | 上游记 chunk 号；本仓记文档标识（回答时作 citation） |
| `df_helpers` 的链式转换 | `kg_extract.py:153` `extract_triples()` 一步到位 | ★★ | 本仓返回**可直接喂 `GraphMemory.ingest_entities()`** 的形状 |
| （无） | `kg_extract.py:181` `build_alias_map()` | — | 本仓扩展（上游靠 DataFrame 去重，无语义归一） |

## 四、与卷139 的分工（工单明确要求）

```
文本 ──[卷142: kg_extract]──→ {nodes, edges, aliases} ──[卷139: ingest_entities]──→ SQLite 三表
                                                              ↓
                                       提问 ──[卷139: recall 递归CTE]──→ 多跳事实 ──→ 注入
```
- **卷139 出「存储与查询层」**（schema + CTE + 增量写）
- **卷142 出「抽取层」**（prompt 模板 + 抽取 + 归一化）
- 先跑 139（schema 定了抽取输出格式才定），再跑 142 —— 与工单指定的顺序一致 ✅

**联通验证**（`test_kg_extract.py::TestPipelineIntegration`）：
抽取 → 归一 → `ingest_entities` → `recall` 多跳召回 → 别名也能命中，**端到端跑通**。

## 五、难度 × 收益评估

| 维度 | 评估 |
|---|---|
| **实现难度** | 低-中。prompt 是现成资产（照抄+增强），代码是纯字符串/JSON 处理，无重依赖 |
| **收益** | 高（相对成本）。它是卷139 图谱的**唯一入口**——没有它，图谱只能手工 remember 一条条写 |
| **风险** | ①**抽取质量取决于 LLM**（小模型对固定词表的遵循度不稳）②中文实体边界识别弱（无 NER，只靠 prompt 约束）③幻觉（prompt 已含"只抽文中明确陈述"约束，但无法完全消除） |
| **不做** | 不做真 NER 模型（引模型 = 引重依赖，违背轻量定位）；不引 pandas；不硬编码模型（可注入） |

**缓解措施（已落地）**：
- prompt 里加 **few-shot 示例**（各 2 例）提升格式稳定性 —— 本仓相对上游的增强
- JSON 解析容忍围栏/前后废话（`kg_extract.py:59` `_extract_json_array`）
- 失败显式抛 `ExtractError`（不静默返回空图）

## 六、验收实测（工单两条可执行不变量）

```bash
# 1) prompt 模板齐（含 few-shot）
$ grep -c "few-shot\|prompt" mcpserver/graph_memory_adapter/prompts/*.md
kg-extract-concept.md: 6 / kg-extract-relation.md: 5    ← ✅（合计 11 ≥ 1）

# 2) pytest 全过（含抽取测试）
$ pytest mcpserver/graph_memory_adapter/ -q
36 passed in 0.31s    ← ✅（139 的 19 + 142 的 17）
```

## 七、交付清单

| 文件 | 说明 |
|---|---|
| `mcpserver/graph_memory_adapter/prompts/kg-extract-concept.md` | 概念抽取 prompt（词表 + importance + **2 个 few-shot 示例**） |
| `mcpserver/graph_memory_adapter/prompts/kg-extract-relation.md` | 关系抽取 prompt（Thought 1/2/3 + 关系词建议表 + **2 个 few-shot 示例**） |
| `mcpserver/graph_memory_adapter/kg_extract.py` | 抽取/解析/归一/别名映射（5 个公开函数） |
| `mcpserver/graph_memory_adapter/test_kg_extract.py` | 17 用例（prompt 加载/JSON 容忍/抽取/归一/端到端联通） |

**约束遵守**：✅ 只借 prompt 设计与管线思路，未复制 Notebook 代码
✅ 不申请新 key（`get_default_llm()` 复用仓内 LLM 栈；测试注入假 LLM 全离线）
✅ 依赖关系遵守（存储层先行）
