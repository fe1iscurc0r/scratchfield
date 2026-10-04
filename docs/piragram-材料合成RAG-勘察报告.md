# PIRAG 范式勘察 · 材料合成路线 RAG 落地报告（I-01）

> 智能体 INDIA · 陆墨科研线
> 日期：2026-08-28
> 性质：只读勘察 + 对照 + 落地方案（本单不写码，写码见 I-02）
> 结论先行：PIRAG 的「结构化合成知识库（SSKB）+ 物理信息注入」范式可直接授粉到
> `mcpserver/material_science/graphrag` 之上的**旁路** `synth_rag/`，数据不足不影响范式成立；
> 合成路线数据需自建，本线只落地骨架 + 示例数据，真实数据标注「待收集」。

---

## 0. 数据来源与诚实声明

| 项 | 来源 | 状态 |
|----|------|------|
| PIRAG-LM 论文 | arXiv（非 GitHub 仓） | 范式借鉴，不 copy 代码；SSKB 精确字段结构**待核对论文原文** |
| 授粉点（weekly_pollination 第 3 条） | `/home/ubuntu/research/papers/weekly_pollination.md` | 云服路径，本机 Win 环境**不存在**，按工单提示词转述提炼 |
| 现有 graphrag 现状 | `mcpserver/material_science/graphrag/`（本仓实读） | ✅ 已逐文件核对 |
| 合成路线数据 | 自建 | **待收集**，本线仅内置 3–5 条木质素示例（来源留真机） |

**硬约束遵守**：本单只读，不写码；不 copy 论文代码；所有合成路线数据标注「示例 / 待收集」。

---

## 1. PIRAG 范式提炼

PIRAG-LM 的核心是把「13,820 条合成路线」组织成 **SSKB（Structured Synthesis Knowledge Base，
结构化合成知识库）**，并让检索过程受**物理信息（Physics-Informed）**约束，从而避免纯语义检索
返回「化学上不成立」的路线。范式分两层：

### 1.1 SSKB：结构化合成知识库

合成路线不是自由文本，而是结构化实体，字段维度：

| 维度 | 字段 | 说明 |
|------|------|------|
| 产物 | product / target | 目标材料（化学式/名称） |
| 反应物 | reactants[] | 前驱体/试剂/溶剂/催化剂（含用量、角色） |
| 条件 | conditions | 温度、压力、时长、气氛（数值区间而非字符串） |
| 产率 | yield | 区间或点值，量化可比较 |
| 物性 | properties[] | 产物已知物性（分解温度、密度、比表面积等） |
| 溯源 | source / reference | 数据出处（本线要求标注「示例/待收集」） |

### 1.2 物理信息注入：约束检索

SSKB 之上挂「领域校验器」，让检索结果物理成立：

1. **规则约束（Rule constraints）**：反应物必须存在（非空、可识别），条件落在合理区间
   （如温度 > -273.15℃、产率 0–100%）。
2. **可行性过滤（Feasibility filter）**：命中候选先过滤再返回，不成立的路由直接剔除或标 warning。
3. **领域校验器（Domain validator）**：产物的已知物性与声明值一致（如分解温度不超已知上限），
   用**规则表**而非 LLM 判断（可解释、可配置、可复现）。

关键设计取向：**检索（召回）与校验（约束）解耦**——召回靠结构化字段过滤 + 相似度排序，
校验靠独立规则表在召回前后双向兜底。

---

## 2. 现有 graphrag 现状对照

`mcpserver/material_science/graphrag/` 现状（实读）：

| 模块 | 职责 | 关键点 |
|------|------|--------|
| `store.py` | JSON 属性图（节点/边/社区） | 无物理字段，节点是 `doc/section` 粒度的笔记 |
| `importer.py` | vault/academic 语料建图 | 词元共现连边（CJK 二元组 + 英文词） |
| `vector_index.py` | bge-small-zh 向量 + 词元降级 | 语义召回，无领域约束 |
| `query.py` | 图谱路径 + 原文摘录 | 纯语义导航 |
| `graphrag_tools.py` | MCP 工具注册 | import/query/stats |

### 2.1 差距表（现有图谱 → PIRAG SSKB → 物理注入点）

| # | 维度 | graphrag 现状 | PIRAG SSKB 目标 | 差距 | 物理信息注入点 |
|---|------|--------------|----------------|------|----------------|
| G1 | 实体粒度 | doc/section（笔记段） | 路线级实体（反应物/产物/条件/产率/物性） | 无结构化路线实体 | 引入 `routes` 表 |
| G2 | 条件表达 | 自由文本 | 数值区间（温度/压力/时长/气氛） | 无法按数值过滤 | 条件拆字段，支持范围查询 |
| G3 | 物性关联 | 无 | 产物物性显式存储 | 检索不校验物性 | `properties` 表 + 一致性校验 |
| G4 | 产率 | 无 | 结构化产率 | 无法按产率排序/比较 | `yield` 字段 |
| G5 | 可行性 | 无任何校验 | 规则表校验器 | 检索结果可能物理不成立 | `validator.py` 规则表 |
| G6 | 溯源 | 笔记 source | 数据来源强制标注 | 示例/真实数据混不可知 | `source` + `is_example` 字段 |
| G7 | 存储 | JSON 图（内存+文件） | SQLite 关系表 | 无结构化查询语言 | `synth_rag` 用 sqlite3 |

---

## 3. 落地方案（I-02 施工图）

### 3.1 目录：`mcpserver/material_science/synth_rag/`（旁路，独立）

```
synth_rag/
├── __init__.py        # 包导出
├── schema.py          # SQLite 表结构 + 路线实体 dataclass
├── store.py           # RouteStore：add_route / update_route / get_route / list_routes
├── retrieve.py        # search：按产物/反应物/条件过滤 + 相似度排序（无向量 DB）
├── validator.py       # validate：规则表物理校验器（反应物存在/条件范围/产率/物性一致）
├── cli.py             # add / search / validate / seed 子命令
└── example_data.py    # 3–5 条木质素示例路线（is_example=1，来源标注待收集）
```

### 3.2 SSKB schema（SQLite，纯标准库）

```
routes(id, name, product, method, yield_min, yield_max, source, is_example, description)
reactants(id, route_id→routes, name, amount, unit, role)
conditions(id, route_id→routes, temp_min_c, temp_max_c, pressure_bar, time_h, atmosphere)
properties(id, route_id→routes, name, value, unit)
```

### 3.3 物理校验器设计（规则表，非 LLM）

| 规则 id | 校验内容 | 严重级 |
|---------|----------|--------|
| reactant_present | 至少 1 个反应物且名称非空 | error |
| product_present | 产物名称非空 | error |
| yield_range | 产率 ∈ [0, 100] | error |
| condition_range | 温度 ∈ [-273.15, 3000] 且 min≤max；压力 ≥0；时长 >0 | error |
| property_consistency | 产物物性落在已知范围表内（可扩展） | warning |

规则**可配置**：`validate(route, rules=None)`，`rules` 可禁用/覆盖单条规则与参数。

### 3.4 检索增强点

- 召回：`search(product=, reactant=, condition=)` 字段过滤 + 轻量相似度打分（子串/词元重合，不引向量 DB）。
- 约束：检索结果可叠加 `validate()`，不成立路由标 `issues` 而非直接消失（可解释）。

### 3.5 数据路线（诚实标注）

- 内置示例：3–5 条木质素路线，`is_example=1`，`source="示例数据·待真机采集"`。
- 真实数据：留真机（天选7 陆墨环境）导入，本线不伪造。

---

## 4. 验收 grep 项（I-02 执行后自检）

```bash
# 1) 测试全过（≥6 用例）
python -m pytest mcpserver/material_science/tests/test_synth_rag.py -q

# 2) 关键函数非空
grep -n "def add_route\|def validate" \
  mcpserver/material_science/synth_rag/store.py \
  mcpserver/material_science/synth_rag/validator.py

# 3) CLI 可 search 内置示例
python -m mcpserver.material_science.synth_rag.cli seed
python -m mcpserver.material_science.synth_rag.cli search --product 木质素
```

---

## 5. 真机验证点（留用户实测，云服 mock 全绿即交付）

1. 天选7 陆墨环境：导入真实木质素合成路线（来源填真实论文/实验记录）后，
   跑 `cli search --product 木质素 --reactant KOH` + `cli validate` 各一次问答。
2. 核对 SSKB 字段与 PIRAG 论文原文的精确对齐（arXiv 原文在云服 weekly_pollination 侧）。
3. 若需接入 MCP agent，再补 `register_synthrag_tools`（本线为旁路，暂不注册，避免碰 graphrag 主流程）。
