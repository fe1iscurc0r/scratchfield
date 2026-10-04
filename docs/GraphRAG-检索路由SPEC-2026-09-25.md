# GraphRAG 检索路由 SPEC（2026-09-25）——查询形态 → 检索方案的裁决尺

> 卷156（KG融合线 P0 前置）· 落盘：砚 · 状态：**SPEC（未写实现代码）**
> 裁决尺来源：GraphRAG-Bench（arXiv:2506.05690v3，ICLR'26；仓 `GraphRAG-Bench/GraphRAG-Benchmark`，498★ MIT，2026-09-25 gh api 实测）
> 下游：卷157（纯向量对照实验）的**实验维度由本文件的路由决策表确定**

## 0. 一句话结论

**GraphRAG 不是普适升级**：简单事实类查询上它常**不如**纯向量 RAG（还会引入噪声与 2.3× 延迟），
但在**需要跨实体串联的复杂推理/摘要/生成**上明显更强。所以我们要的不是"换掉向量库"，
而是**一个按查询形态分发的旁路路由**。

## 1. 胜率矩阵（查询形态 × 检索方案）

下表每个格子都绑定 benchmark 出处；`—` 表示该 benchmark **未显式覆盖**该形态（见 §5 未决项）。

| 查询形态 | 纯向量 RAG | 图检索（GraphRAG） | 混合（RRF 融合） | 依据（benchmark 结论） |
|---|---|---|---|---|
| **单点事实**（"X 在哪/是什么"） | ✅ **胜** | ❌ 更差 | 不必要 | Obs.1：「basic RAG is comparable to or outperforms GraphRAG in simple fact retrieval」；Obs.4：RAG 简单问题 Evidence Recall **83.2%**；Table 2：RAG(w/rerank) Fact Retrieval ACC **60.92** vs MS-GraphRAG **49.29** |
| **多跳/复杂推理**（跨文档串联） | ⚠️ 弱 | ✅ **胜** | ✅ 可用 | Obs.2：「GraphRAG models show a clear advantage in complex reasoning」；Obs.5：HippoRAG Evidence Recall **87.9–90.9%**（L2–3）；Table 2：HippoRAG2 Complex Reasoning ACC **53.38** vs RAG **42.93** |
| **全文摘要**（碎片信息合成） | ⚠️ 弱 | ✅ **胜** | ✅ 可用 | Obs.2 把 Contextual Summarize 明确列入 GraphRAG 优势；该级用 Evidence Coverage 指标 |
| **创造性生成**（需跨知识综合） | ⚠️ 覆盖广但忠实度低 | ✅ 忠实度高 | ⚠️ 按需 | Obs.3：RAPTOR faithfulness **70.9%**（最高），但 RAG coverage 更广（40.0%）；Obs.6：Global-GraphRAG Evidence Recall **83.1%** vs RAG Context Relevance **78.8%** —— **权衡而非碾压** |
| **时序敏感**（要"最新"、实时更新） | ✅ **胜**（且必须走向量） | ❌ 明显更差 | —— | 论文引述外部研究：GraphRAG「**13.4% lower accuracy** on Natural Questions」，且时序类问题准确率再降 **16.6%** —— 图索引的**构建时点**天然滞后 |
| **聚合类**（"共有多少/全部列出"） | 需实测 | 需实测 | —— | benchmark 的 L1–L4 未单独设"聚合"档；**必须用本仓自建小基准实测**（见 §5.1） |

**成本维度（同样要进决策）**：GraphRAG 的 prompt 膨胀显著 —— Obs.8/9：MS-GraphRAG(global) 单次 prompt 可达 **4×10⁴ tokens**，
LightRAG ≈10⁴，HippoRAG2 ≈10³（相对紧凑）；外部研究给的总体延迟代价是 **2.3×**。
⇒ 图检索要有**准入条件**（形态判断 + 预算判断），不能默认开着。

## 2. 本仓现有检索入口（实测，非推测）

| 入口 | 实现 | 归属 | 现状 |
|---|---|---|---|
| `POST /rag/query`（`apiserver/routes/rag.py:138`） | `rag_service.query(query, top_k, tags, min_score, rerank)` | **向量** | 已支持 rerank/阈值；是当前主检索 |
| `GET /memory/quintuples/search`（`extensions.py:2613`） | 关键词逐词过滤（远程优先，回落本地 `summer_memory`） | **图（弱）** | 仅关键词，无图遍历（无 hop 扩展） |
| `GET /memory/quintuples` / `GET /memory/graph/summary` | 分页枚举 + 度数/类型聚合 | **图（读）** | 卷151 补齐，供可视化与 hub 识别 |
| `mcpserver/memory_maas/hybrid_search.py` + `core.py:221` | **已有 RRF 混合检索**（`memory.hybrid_search.rrf`） | **混合** | 已有实现，但**未与 `/rag/query` 打通**（两套入口） |
| `POST /rag/ingest`、`GET /rag/documents`、`/rag/vault/status` | 入库与库状态 | 向量 | 图构建**无对应入口**（这是缺口） |

**缺口三条**：① 没有"按查询形态选路"的分发器；② 图侧没有多跳遍历（只有关键词过滤）；
③ 混合检索已实现却未接入主检索路径。

## 3. 路由决策表（本 SPEC 的交付核心）

| 判定条件（按序短路） | 路由到 | 附加参数 | 依据 |
|---|---|---|---|
| 1. 含时间限定词（最新/今天/截至…）或命中"时序敏感"特征 | **纯向量**（+ 时间过滤） | `rerank=True` | §1 时序行：图索引滞后，准确率降幅最大 |
| 2. 单实体、无连接词、命中率高的短查询（L1 形态） | **纯向量** | `top_k` 小、`rerank=False`（省延迟） | Obs.1/4 + Table 2 |
| 3. 含 ≥2 个实体且存在关系词（"如何/为何/与…的关系"）→ L2 | **图检索（需多跳）** | `hops=2`；预算上限见 §4 | Obs.2/5 |
| 4. 要求"综合/总结/综述" → L3 | **图检索** + 覆盖率指标 | `coverage_hint` | Obs.2；L3 用 Evidence Coverage |
| 5. 开放式生成（假设/改写/创作） → L4 | **图检索（保忠实）**，必要时并入向量以补覆盖 | `faithfulness_first=True` | Obs.3/Obs.6（权衡） |
| 6. 聚合/计数类 | **先图枚举后本地聚合**，并记录待实测标记 | — | §5.1：benchmark 未覆盖，需实测 |
| 7. 判定不确定 | **向量打底 + 图补充**（混合 RRF） | RRF 融合权重要记录 | 已有 `hybrid_search` 可复用 |

> 设计原则：**默认向量、图按需**（fail-safe 走向量），且每次路由**必须落一条决策日志**（形态判定 + 依据 + 预算），
> 否则事后无法归因"是路由错了还是检索错了"。

## 4. 分发器接口草案（旁路，不改现有管道）

```python
# 建议落点：apiserver/routes/retrieval_router.py（新文件，旁路）
class RouteDecision(BaseModel):
    query: str
    form: Literal["fact", "multi_hop", "summarize", "creative", "aggregate", "time_sensitive", "unknown"]
    backend: Literal["vector", "graph", "hybrid"]
    params: dict            # top_k / hops / budget_tokens / rerank / time_filter
    reasons: list[str]      # 绑定的依据，如 ["Obs.1", "L1-shape"]（可审计）
    budget: dict            # {"max_prompt_tokens": 4000, "max_latency_ms": 3000}

@router.post("/retrieval/route")
async def route(req: RouteRequest) -> RouteDecision:   # 只给决策，不执行检索
    ...

@router.post("/retrieval/execute")
async def execute(req: RouteRequest) -> RouteResult:   # 按决策调用既有 /rag/query 或图侧
    ...
```

**旁路约束**（照工单要求，最小改动）：
- 不修改 `/rag/query` 与 `/memory/*` 的现有语义；分发器只做"选择 + 调用 + 记录"
- `form` 判定先用**规则**（关键词/实体计数/疑问词表），不上模型 —— 规则可审计、可回滚
- 每次返回都带 `reasons`，便于对账"该走图的走了向量吗"

## 5. 未决项与偏差（先写清楚，别让下游踩）

1. **聚合类无 benchmark 依据**：GraphRAG-Bench 的 L1–L4 未单设"聚合/计数"档 ⇒ 本 SPEC 把它标为"需自建小基准"，
   不自造结论。**卷157 的对照实验维度应包含聚合类**（这是本卷给下游的唯一硬约束）。
2. **原文附录 B「Takeaway Findings」未取到**：arXiv HTML 页面该节被截断，本文的准则由正文 Obs.1–9 归纳，
   **未经附录 B 逐条核对** —— 引用时请以 Obs./Table 编号为准。
3. **语料差异**：benchmark 语料是「NCCN 医学指南（高结构化）+ 古腾堡小说（松散叙事）」，与 lumo 的
   「代码库 + 科研记忆（五元组）+ 文献库」不同 ⇒ 胜率方向可借，**具体数值不可直接搬**。
4. **本仓无检索质量评测基线**：Evidence Recall / Context Relevance 等指标本仓**尚未实现**，
   因此"路由是否更优"目前无法在本地量化 —— 这也是卷157 的价值（先有尺子，再谈优化）。
5. **图侧多跳缺失**：`/memory/quintuples/search` 只有关键词过滤，L2 路由需要先补 hop 遍历（不在本卷范围）。

> 现状：**仅决策文档，未写实现**。`/retrieval/route` 是接口草案，落地归后续卷。
