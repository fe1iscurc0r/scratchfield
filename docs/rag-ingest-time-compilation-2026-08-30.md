# A08 RAG Ingest-Time 编译（摊销成本）

> 任务：A08 RAG ingest-time 编译
> 来源：digest-g1-2-2026-08-30.md · 核心论文 2608.20845《RAG Deserves an Index: Why Ingest-Time Compilation Beats Query-Time Interpretation》
> 日期：2026-08-30

---

## 一、问题陈述

传统 chunk RAG 是**query-time 解释**：每次查询都把相关 chunk 取出来、现场重新"解释/理解"一遍。对于**固定语料、重复读取**的场景，这是重复劳动。论文（2608.20845）搬用了数据库领域五十年前就有的解法——**ingest-time 编译（写入时语义编译）**：

- 编译 claims 在 **32 个预算 × 模型单元**上全部优于基于 chunk 的 RAG；
- 且**缩放 33.7 倍便宜**。

物理原理：固定语料上重复读取的成本应该被**摊销到 ingest 阶段一次性编译**，而不是每次查询重新计算。

## 二、核心思想：ingest-time 语义编译

- **Ingest 阶段（一次）**：把语料编译成结构化、可复用的语义索引——不只是向量/倒排，而是**把事实/声明/关系预先抽取并编译成"claim 对象"**，附带溯源与置信度。
- **Query 阶段（每次）**：直接检索已编译的 claim，做**组合/推理**，而不是重新"理解原始文本"。

对比：

| | chunk RAG（query-time 解释） | ingest-time 编译 |
|---|---|---|
| 语料理解时机 | 每次查询现场做 | ingest 一次性做 |
| 重复读取成本 | 线性累加 | 摊销为一次 |
| 检索单元 | 原始 chunk | 预编译 claim（事实/声明） |
| 成本缩放 | 随查询数线性 | 33.7× 便宜 |

## 三、原型设计

```python
# 1) Ingest：一次性编译语料 → 结构化 claim 索引
def compile_corpus(docs) -> ClaimIndex:
    idx = ClaimIndex()
    for d in docs:
        claims = extract_claims(d)      # 抽取事实/声明/关系（LLM 或规则）
        for c in claims:
            idx.add(claim=c, source=d.id, confidence=c.conf)
    return idx

# 2) Query：检索预编译 claim + 组合推理，不再重解释原文
def query(idx, q):
    claims = idx.retrieve(q)            # 检索已编译 claim
    return compose(claims, q)           # 组合/推理产出答案

# 3) 增量更新：语料变更时只重编译受影响段落
def ingest_delta(idx, changed_docs):
    for d in changed_docs:
        idx.evict(d.id); idx.add_all(extract_claims(d))
```

## 四、32 预算单元对比表（模板）

按论文口径，在 32 个（预算 × 模型）组合上对比 chunk RAG 与 ingest-time 编译：

| 预算单元 | chunk RAG | ingest-time 编译 | 胜负 |
|---|---|---|---|
| 预算 B1 × 模型 M1 | — | — | 编译胜 |
| …（共 32 单元） | — | — | 编译全胜 |
| **成本缩放** | 1× | **33.7× 便宜** | — |

**验收指标**：编译 claims 检索在全部预算单元上 ≥ chunk RAG，且重复查询场景下成本显著下降（摊销效应随查询数放大）。

## 五、适用边界（何时用/何时不用）

- **适用**：固定/低频变更语料 + 高频重复查询（知识库、法规库、内部文档、产品手册）。
- **不适用**：每次查询都是全新语料、或语料高频变化且无增量编译能力时，编译摊销收益被抵消。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| ingest-time 编译原型 | §三 `compile_corpus`/`query` 骨架 |
| 32 预算单元对比表 | §四 模板 |
| 与 chunk RAG 对比 | §二 对比表 + §四 |
| 文档 | `docs/rag-ingest-time-compilation-2026-08-30.md` |
