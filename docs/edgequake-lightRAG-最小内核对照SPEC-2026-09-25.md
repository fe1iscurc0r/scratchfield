# edgequake × LightRAG — GraphRAG 最小检索内核对照 SPEC（2026-09-25）

> 卷158（KG融合线）· 落盘：砚 · 状态：**仅 SPEC（未写实现代码；Rust 源码只读不编译）**
> 双实现来源：
> - **edgequake**（Rust）：[`raphaelmansuy/edgequake`](https://github.com/raphaelmansuy/edgequake)（**Apache-2.0**，2097★，实测 2026-09-25，非 archived，默认分支 `edgequake-main`）
> - **LightRAG**（Python）：[`HKUDS/LightRAG`](https://github.com/HKUDS/LightRAG)（双层 RAG 原始实现，EMNLP 2025）
> 防重复对照：LightRAG **不重新接入**（本仓 `mod/references/lightrag/` 现仅存架构笔记，见 §6 偏差）；本卷只做**双实现 diff**。
> 依赖链：与卷156 [`GraphRAG-检索路由SPEC`](GraphRAG-检索路由SPEC-2026-09-25.md) 并行，本卷的"最小检索内核"结论配合其路由策略使用。

## 0. 结论先说

两个独立实现（Rust / Python）在**检索语义**上收敛到同一件事，但**工程切法不同**：

| 关注点 | LightRAG（Python） | edgequake（Rust） |
|---|---|---|
| 双层怎么分 | **两套关键词**：`low_level_keywords` 打实体、`high_level_keywords` 打主题 | **两套向量空间**：`embeddings.low_level`（实体）/ `embeddings.high_level`（社区报告） |
| 模式语义 | `mode ∈ {local, global, hybrid, naive, mix}`，按模式决定用哪套关键词 | 同构：`modes/{local,global,hybrid,naive,mix}.rs` |
| 并行策略 | 顺序 + 缓存 | **双 arm 并发 + 超时**（`run_arm_timed`），缓存四路分层 |

**提炼出的「最小检索内核」= 7 件，其中 4 件不可缺、3 件是可选的工程化增益**（§4 给接口签名）。

## 1. 双实现实测事实（源码行号引用）

### 1.1 LightRAG（`lightrag/operate.py`，7126 行）

行号索引（原文出处）：`L4693`、`L4755`、`L4757`、`L4994`、`L5104`、`L5107`、`L5189`、`L5190`

| 位置 | 内容 |
|---|---|
| `operate.py:4693` | `async def kg_query(...)` —— **双层检索的统一入口**（local/global/hybrid/mix 都走它） |
| `operate.py:4755` | `if ll_keywords == [] and query_param.mode in ["local", "hybrid", "mix"]:` → 记 `low_level_keywords is empty` |
| `operate.py:4757` | `if hl_keywords == [] and query_param.mode in ["global", "hybrid", "mix"]:` → 记 `high_level_keywords is empty` |
| `operate.py:4994` | 关键词抽取函数返回 `(high_level_keywords, low_level_keywords)` **两个列表** |
| `operate.py:5104` / `:5107` | 从 LLM payload 里取 `high_level_keywords` / `low_level_keywords` |
| `operate.py:5189` / `:5190` | 组装 prompt 时把两套关键词**分别**注入 |

**读法**：LightRAG 的"双层"是**查询侧的分层**（先把 query 拆成实体词与主题词），
再由模式决定"哪几层参与"；缺层的组合会在 4755/4757 处**告警但不崩**（降级而非失败）。

### 1.2 edgequake（`edgequake/crates/edgequake-query/src/`）

行号索引：`L46`、`L48`、`L53`、`L58`、`L64`、`L237`、`L37-58`

| 位置 | 内容 |
|---|---|
| `engine_impl/modes/local.rs:46` | `&embeddings.low_level` —— **低层检索打的是 low_level 向量空间** |
| `engine_impl/modes/local.rs:53` | `let entity_vectors = filter_by_type(vector_results, VectorType::Entity);` |
| `engine_impl/modes/local.rs:41` | 检索类型固定为 `Some("entity")` |
| `engine_impl/modes/global.rs:48` | `&embeddings.high_level` —— **高层检索打 high_level 向量空间** |
| `engine_impl/modes/global.rs:58` | `if edgequake_storage::community_reports_enabled() {` |
| `engine_impl/modes/global.rs:64` | `crate::community_global::append_community_report_vector_chunks(...)` |
| `engine_impl/modes/global.rs:237` | `crate::community_global::expand_global_context_with_communities(...)` |
| `engine_impl/modes/hybrid.rs:37-39` | `run_arm_timed(plan.run_local, "local", …)` —— 低层作为**一个带超时的 arm** |
| `engine_impl/modes/hybrid.rs:56-58` | `run_arm_timed(plan.run_global, "global", …)` —— 高层作为**另一个 arm**，两者并发 |

**读法**：edgequake 把"双层"落成**两个可独立超时的并发分支**（arm），
并用 `query plan`（`plan.run_local` / `plan.run_global` 开关）决定跑哪些 arm ——
比 LightRAG 的顺序执行多了一层**工程化**：任一 arm 超时/失败不拖死整体。

## 2. 源 → 目标映射表（组件级）

| 组件 | LightRAG（Python） | edgequake（Rust） | 是否进「最小检索内核」 |
|---|---|---|---|
| 查询分解（低/高层关键词） | `operate.py:4994`（返回两列表） | query plan: `plan.run_local` / `plan.run_global` | ✅ **必需** |
| 低层检索（实体） | `kg_query` local 分支（`4755`） | `local.rs:46`/`:53`（Entity 向量） | ✅ **必需** |
| 高层检索（主题/社区） | `kg_query` global 分支（`4757`） | `global.rs:48`/`:64`（社区报告向量） | ✅ **必需** |
| 上下文组装 | `_build_query_context`（注入两套关键词 `5189`） | `context_format.rs` + `chunk_hydration.rs` | ✅ **必需** |
| 模式门控 | `mode in ["local","hybrid","mix"]`（`4755`） | `modes/mod.rs` 分发 + plan 开关 | 可选（本仓按卷156 路由表替代） |
| 并发 + 超时 | 无（顺序） | `hybrid.rs:37-58` `run_arm_timed` | 增益（本仓小规模暂不急） |
| 缓存分层 | KV 缓存（`answer_cache_kv`，`4895`） | 四路：answer / embedding / llm_response / query_result | 增益（先去重再缓存） |
| 引用校验 | 无独立模块 | `citation_verify.rs` | 增益（要可追溯就值得） |

## 3. 结构共鸣（三处）

1. **"分层"放查询侧还是存储侧**：LightRAG 把分层放在**查询**（两套关键词，`operate.py:4994`），
   edgequake 放在**存储**（两套向量空间，`local.rs:46` / `global.rs:48`）。
   ⇒ 本仓若自建，**两者都要有**：关键词分层便宜（纯文本），向量分层贵（要维护两套索引）。
   建议先做关键词分层 + 单一向量空间，等数据规模上来再拆 high_level 索引。
2. **"缺层降级"的处理**：LightRAG 在缺关键词时**告警并继续**（`4755`/`4757`）；
   edgequake 用 **plan 开关**显式表达"这次跑哪几个 arm"。
   ⇒ 我们的路由分发器（卷156 §4 草案）应输出**显式 plan**，而不是靠"缺了就跳过"。
3. **并发 vs 顺序**：同一语义在 Rust 版被拆成**两个并发 arm + 独立超时**（`hybrid.rs:37-58`）。
   ⇒ 这是"最小内核"里**唯一能靠工程手段拿到数量级收益**的地方（延迟 = max(arm) 而非 sum）。

## 4. 「最小检索内核」定义（候选清单 + 接口签名）

> 判据：**去掉它，GraphRAG 就不成立** —— 只保留这 4 件即最小可跑；后 3 件是增益。

```python
# ① 查询分解：一条 query → 两套检索意图
def decompose(query: str, *, mode: str) -> dict:
    """返回 {"low": [...实体/关系词], "high": [...主题/概念词], "mode": mode}
    对应 LightRAG operate.py:4994 的双列表返回。"""

# ② 低层检索：实体/关系向量空间
def retrieve_low(intent: list[str], *, top_k: int) -> list[ContextItem]:
    """打 low_level 向量空间（edgequake local.rs:46），返回实体+关系上下文。"""

# ③ 高层检索：主题/社区摘要向量空间
def retrieve_high(intent: list[str], *, top_k: int) -> list[ContextItem]:
    """打 high_level 向量空间（edgequake global.rs:48），可含社区报告（global.rs:64）。"""

# ④ 上下文组装：去重 + 排序 + 预算裁剪
def assemble(low: list[ContextItem], high: list[ContextItem], *, token_budget: int) -> str:
    """合并两路、去重、按分数/预算裁剪（edgequake context_format.rs 的职责）。"""

# —— 以下为增益层（可选） ——
def run_arms_parallel(arms: list[ArmFn], *, timeout_ms: int) -> list[ContextItem]:
    """并发 arm + 独立超时（edgequake hybrid.rs:37-58 的 run_arm_timed）。"""

def cache_layers() -> dict:      # answer / embedding / llm_response / query_result（edgequake 四路缓存）
    ...

def verify_citations(context: str, sources: list) -> list[dict]:   # citation_verify.rs
    ...
```

**最小数据面**：① 实体 KV（名字→描述/类型）② 关系表（头尾+描述）③ 文档块表 ④ （高层）社区/主题摘要表
⑤ 一个向量索引（若不做双层可先只建一套）。本仓现状：③④ 有（五元组/文档），①② 由 `mcpserver/graph_memory_adapter` 覆盖，
⑤ 见卷157 结论（**缺神经嵌入**）。

## 5. 难度 × 收益

| 项 | 难度 | 收益 | 档位 |
|---|---|---|---|
| ①②③④ 最小内核（查询分解 + 双路检索 + 组装） | 中 | 高（GraphRAG 成立） | **立即授粉** |
| 显式 query plan（对齐卷156 路由分发器） | 低 | 中高（可审计、可回滚） | **立即授粉** |
| 并发 arm + 超时 | 低 | 中（延迟从 sum 降到 max） | **立即授粉**（本仓同步调用改并发即可） |
| 双层向量空间（维护两套索引） | 高 | 中（高层召回靠它，但成本翻倍） | 暂缓（先关键词分层） |
| 四路缓存 | 中 | 中（重复查询省 LLM） | 暂缓（先测命中率） |
| 引用校验 | 中 | 中高（可追溯） | 暂缓（与 ELN 线合并考虑） |

## 6. 偏差、未决项与边界

1. **本仓 LightRAG 源码现状偏差（必须记录）**：工单称"LightRAG 已在仓（from_stored patch 保留）"，
   实测 `mod/references/lightrag/` **只剩 `ARCHITECTURE_NOTES.md`**（含双层检索表与 local/global/hybrid/naive 模式表），
   **Python 源码不在**。本 SPEC 的 LightRAG 侧行号取自**上游 `HKUDS/LightRAG` 的 `lightrag/operate.py`（7126 行）**，
   不是本仓副本 —— 引用时请以"上游版本"口径对待。
2. **本仓实际在用的是什么**：`mcpserver/rf_brain/lightrag_graph.py`（210 行，实体图/邻居/`context_for`/`query_graph`，
   关键函数在 L49/L62/L98/L111/L127/L159/L181）+ `tools/lightrag_graph.py`（91 行）——
   这是**我们自己的轻量实体图**，不是 LightRAG 本体。做内核拆分时应以它为主干，而不是引入 LightRAG。
3. **未编译 Rust、未跑任何实现**：edgequake 结论来自源码阅读（1725 个 `.rs` 中的检索 crate），非运行时实测。
4. **未做机器级 diff**：两版**不同语言**，无法逐行 diff；本文的"对照"是**语义层映射 + 关键位置行号**。
5. 与卷157 的衔接：本内核的 ⑤ 向量索引依赖**神经嵌入**，而卷157 实测本仓只有哈希词袋
   ⇒ **最小内核可以先只上 ①②③④（关键词分层 + 图检索），向量层等嵌入到位再替**。
