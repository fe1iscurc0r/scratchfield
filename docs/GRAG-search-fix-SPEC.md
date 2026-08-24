# GRAG 搜索修复 SPEC — 预处理方向

> 目标: 修复 GRAG 搜索失效 + 数据质量 + 为算力优势铺路
> 背景: GRAG 继承自 NagaAgent summer_memory，跑在天选7pro，有图形化界面（MindView）但搜索有问题
> 代码现状: 已读 extractor_ds_tri.py / rag_query_tri.py / graph.py 三个核心文件
> 生成: 2026-08-13

---

## 一、根因（代码级证据，非猜测）

### 致命 bug：搜索数据源错位

`graph.py` 的 `query_graph_by_keywords()`（L199-228）：

```python
def query_graph_by_keywords(keywords):
    graph = get_graph()
    if graph is None:
        return []   # ← 没连上 Neo4j 直接返回空
    ...
    query = "MATCH (e1:Entity)-[r]->(e2:Entity) WHERE ... CONTAINS $kw ..."
    rows = graph.run(query, kw=kw).data()  # ← 只查 Neo4j
```

而 `store_triples()`（L152-173）是**双写**：既写 `triples.json`（文件）又写 Neo4j。

**结论：数据存进文件，搜索却只问 Neo4j。** 当天选7pro 上 Neo4j 未启动/未配置时：
- 数据正常写入 `triples.json`
- 但搜索永远返回空（`graph is None → return []`）

这就是"搜索有问题"的真相——**不是搜不到，是搜索和存储的数据源分离了**。文件模式的数据（`load_triples()` 已实现）根本没被查询路径使用。

### 次级问题：关键词匹配无归一化

`rag_query_tri.py` 的 `query_knowledge()` 先让 LLM 提关键词，再喂给 `query_graph_by_keywords` 做 `CONTAINS` 模糊匹配。但：
- 代词（"我/你/它"）会被提成关键词 → 匹配到八爪鱼节点
- 实体变体（`《Winter Game》` vs `winter game`）匹配不到同一节点
- 百科数据（"苹果公司发布iPhone"）混入个人记忆

### 数据质量（skill 已诊断 5 类）

代词泛滥、空值三元组、实体消歧缺失、百科混入、triples/quintuples 双系统错位。详见 `naga-agent-bridge` skill 的 `grag-extraction-quality.md`。

---

## 二、预处理方向（三个优先级）

### P0：搜索数据源统一（真正让搜索"能工作"）

1. **`query_graph_by_keywords` 加文件模式 fallback**
   ```python
   graph = get_graph()
   if graph is None:
       # 回退文件模式：查 triples.json
       triples = load_triples()
       return [t for t in triples if any(kw in t[0] or kw in t[2] or kw in t[1] for kw in keywords)]
   ```
   `load_triples()` 已存在，就差接线。这是最小改动、最大收益的修复。

2. **关键词匹配升级**：CONTAINS 模糊匹配 → 精确匹配优先 + 模糊 fallback，消除"同义变体搜不到"。

3. **提取 prompt 替换**：`extractor_ds_tri.py` 的 prompt 换成 skill 里已写好的改进版（禁代词、禁空值、禁百科、要求具体名词+确定事实）。

### P1：数据质量治理

4. **实体消歧**：引入 `rdflib`/`neosemantics`（本轮已扫进 knowledge/ 归档）做本体约束，统一实体命名。
5. **清洗存量数据**：用 skill 里的过滤脚本清洗 `triples.json`（去代词/空值/自环）。
6. **双系统合并决策**：triples（3-field，radio_brain 桥用）vs quintuples（5-field，MindView 可视化用）——决定合并成一套，还是保留两套但统一数据源。

### P2：算力优势（后置，别本末倒置）

7. **混合检索**：`rupurt/sift`（BM25 + 向量 + 重排）替换纯 CONTAINS。
8. **语义网层**：`rdflib` 给图谱加本体 schema，做确定性关系查询。

---

## 三、为什么这个顺序

```
P0 搜索能工作 → P1 数据干净 → P2 算力优势
```

当前 GRAG 的"快速读取"都没做好（搜索因 Neo4j/文件错位直接失效），谈"算力优势"是空中楼阁。**先让搜索返回正确结果，再让数据变干净，最后才谈算力**。

---

## 四、依赖的已扫项目（本轮 knowledge/ 20 包）

| 优先级 | 用到的项目 | 用途 |
|--------|-----------|------|
| P1 | rdflib / neosemantics | 实体消歧 + 本体约束 |
| P2 | rupurt/sift | 混合检索 |
| P2 | rdflib | 语义网 schema |

其余 15 包（graphrag/LightRAG/Obsidian 生态等）为对照参考或后续扩展，不阻塞本次修复。

---

## 五、交付物清单

- [ ] `graph.py`：`query_graph_by_keywords` 加文件 fallback
- [ ] `rag_query_tri.py`：关键词匹配升级（精确优先）
- [ ] `extractor_ds_tri.py`：换改进版 prompt
- [ ] 数据清洗脚本（清洗存量 triples.json）
- [ ] （P2 可选）sift 混合检索接入

## 六、验收标准

1. 不连 Neo4j 时，搜索 `triples.json` 里的实体能返回正确三元组
2. 搜索"那首歌"不会返回一堆"我/你/它"节点
3. 同名实体变体（大小写/书名号）能命中同一节点
4. 提取不再产生空值/代词三元组

---

## 元记录

- 关联: naga-agent-bridge skill（grag-integration.md / grag-extraction-quality.md）
- 已扫项目: github_haul/knowledge/（20 包，本轮非 LLM 拓广扫货）
- 前置: 天选7pro 可操作后执行（当前离线，仅定方向）
