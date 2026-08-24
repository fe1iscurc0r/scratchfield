# guide_engine/ + rag/ + system/ 只读代码审查报告

**审查范围**：`d:\my git\scratchpad\` 下 guide_engine/、rag/、system/ 三个目录全部已提交代码

---

## 🔴 Critical（必须修复）

### C1. RAG 检索分数体系与 min_score 阈值量纲完全不匹配，本地 RAG 检索永远返回空结果

**位置**：`rag/rag_service.py` L178-180（默认 `min_score=0.6`）、L229（过滤逻辑）、L310-338（`_rrf_fuse`）

**问题**：`_rrf_fuse` 明确丢弃原始 cosine/BM25 分数，改为从 0 累加 RRF 分数 `1/(60+rank+1)`：

- 单路命中最高分 ≈ `1/61 ≈ 0.0164`，双路命中最高分 ≈ `0.0328`
- 即使经过 rerank（`score = original*0.7 + coverage*0.3`），理论上限也只有 ≈ 0.323

但所有真实调用方的阈值都远高于此：
- `query()` 自身默认 `min_score=0.6`
- `apiserver/routes/rag.py` L44：`min_score: float = Field(0.6, ge=0.0, le=1.0)`
- `apiserver/routes/lumo_proxy.py` L174：`min_score=0.5`

L229 的 `r.get('score', 0) >= min_score` 过滤会**清空所有结果**。

**旁证**：仓库内唯一能通过的调用是 `tests/test_rag_pipeline.py` L119/L159/L176，它们全部刻意传 `min_score=0.0` 并注释"关闭分数过滤"——这恰好证明默认阈值下无法命中。

**即本地 RAG 知识库功能在生产路径上整体失效。**

**修复建议**（二选一）：
- **推荐**：在 `_rrf_fuse` 后将 RRF 分数归一化到 0~1（如除以单文档可达最大分 `2/(k_const+1)`），或改用原始 cosine 分数做阈值过滤、RRF 仅用于排序
- 或者将 min_score 语义改为"排名/覆盖率"并同步下调所有调用方默认值（0.6/0.5 → 接近 0），但这会让阈值失去过滤意义

---

## 🟠 High（应当修复）

### H1. 嵌入失败时静默写入固定种子随机向量，"fail-fast" 修复形同虚设

**位置**：`rag/rag_service.py` L105-110 与 `rag/embedding_engine.py` L141-145、L180-182、L192-200

**问题**：`rag_service.ingest_document` 注释声称「HIGH-2 修复：嵌入失败不注入随机向量……改为 fail-fast」，并检查 `if embeddings is None`。但 `EmbeddingEngine.encode()` **从不因失败返回 None**：

- 模型加载失败 → `return self._random_embedding(texts)`（L141-145）
- 编码异常 → `except Exception: return self._random_embedding(texts)`（L180-182）
- 仅当 texts 为空才返回 None

更糟的是 `_random_embedding` 用 `np.random.seed(42)` 固定种子（L195），所有失败文本都会得到确定性但无意义的向量并被静默入库，检索"看起来正常"但结果完全随机——正是注释里声称已修复的问题。

此外 `_random_embedding` 输出 384 维，而 `bge-small-zh-v1.5` 实际输出 512 维，模型恢复后旧数据会因维度不符被 vecdb_client 的 `valid_mask`（L361-367）静默排除，造成数据"隐形丢失"。（`get_embedding_dim()` L206-208 返回 384 同样是错的，好在仓库内无调用方，属潜伏问题。）

**修复建议**：`encode()` 在模型未加载/编码异常时返回 None（把随机降级改为显式开关，如 `allow_fallback` 参数），让上层 fail-fast 真正生效；同时把 `get_embedding_dim` 改为读取 `self._model.config.hidden_size`。

### H2. prompt_manager 的 game_id 存在用户可控路径穿越

**位置**：`guide_engine/prompt_manager.py` L38-50（`_load_from_file`）

**问题**：候选路径构造为 `self.prompt_dir / f"{game_id}.yaml"`，而 game_id 来自外部请求（`GuideRequest.game_id` → `guide_service.ask` → `get_prompt_config`）。`normalize_game_id` 只做小写化和别名映射，未知值原样透传——攻击者可传 `../../任意路径` 读取 prompt_dir 之外的 .yaml 文件。影响有限（仅读取、要求 `yaml.safe_load` 解析成功且结果为 dict），但这确实是用户输入直达文件系统路径。

**修复建议**：

```python
import re
if not re.fullmatch(r"[a-z0-9_\-]+", game_id):
    raise ValueError(f"非法 game_id: {game_id}")
```

或解析后用 `resolved.resolve().is_relative_to(self.prompt_dir)` 校验路径边界。

---

## 🟡 Medium（建议修复）

### M1. config.py 的 JSON 回退解析按 # 剥离注释，会破坏含 # 的字符串值

**位置**：`system/config.py` L1524-1537（json5 解析失败后的 fallback）

**问题**：fallback 逐行执行 `line = line.split("#")[0].rstrip()`，会切断含 # 的合法字符串值（如颜色 `"primary": "#4A90D9"`、带 fragment 的 URL），导致二次 `json.loads` 失败，整个配置文件加载失败并静默回退默认配置——用户会以为"配置没生效"。而 `system/config_manager.py` 的 `_load_config_file` 明确注释「不做任何注释剥离，避免破坏字符串值」，两处策略不一致。

**修复建议**：删除该 fallback 的 # 剥离逻辑，json5 解析失败即视为文件损坏并记录明确错误；或仅在引号外状态机中剥离注释。

### M2. appearance.py 的 CSS 清洗正则与默认值自相矛盾，保存默认 shadow 会产生非法 CSS

**位置**：`system/appearance.py` L23-24（`_CSS_INJECT_RE`）与 L247-260（`set_dialog_style`）、L73（默认 shadow）

**问题**：`_CSS_INJECT_RE = r'[;{}()<>\n]'` 明确禁止 `(` 和 `)`，但 shadow 默认值 `"0 2px 8px rgba(0,0,0,0.08)"` 含有括号。用户保存该默认值时，`generate_css_variables()` 会先被清洗再去写入，产生非法 CSS，且写入的 CSS 与用户界面所见不一致。

**修复建议**：对 shadow 字段单独使用白名单校验（如 `^[0-9a-z .,%()\-]+$`），或从 `_CSS_INJECT_RE` 移除 `()` 并改用更严格的整体白名单。

### M3. guide_service 未处理 force_query_mode 非法值，会导致 500

**位置**：`guide_engine/guide_service.py` L101-102

**问题**：`mode = QueryMode(request.force_query_mode)`，用户传入不在枚举内的字符串会抛 ValueError，未被捕获，直接变成 500 内部错误而非 400 类客户端错误。

**修复建议**：

```python
try:
    mode = QueryMode(request.force_query_mode)
except ValueError:
    # 返回明确的参数错误（400），或忽略该字段走自动路由
```

### M4. RAG 入库两段提交非原子，失败会留下孤儿数据

**位置**：`rag/rag_service.py` L129-157（insert_document 与 insert_chunks 各自 commit）、L295-308（`_save_document_copy`）

**问题**：文档元数据与分块数据分两次独立提交，insert_chunks 失败时 documents 表残留孤儿行；`_save_document_copy` 更早落盘的文件副本也不会清理。重复入库同一 doc_id 时还可能产生半新半旧的混合数据。

**修复建议**：将两个插入合并为单个事务（在 VecDBClient 内一次性 execute 后统一 commit），失败时 rollback；insert_chunks 失败后补偿删除 document 行与副本文件。

### M5. sqlite 单连接跨线程共享，存在并发 ProgrammingError/数据竞争风险

**位置**：`rag/vecdb_client.py` L54（`sqlite3.connect(db_path, check_same_thread=False)`）

**问题**：RAGService 为双检锁单例，VecDBClient 内单一连接被 FastAPI 路由通过线程池并发调用（`apiserver/routes/rag.py`、`lumo_proxy.py` 的 `run_in_executor`）。sqlite3 连接对象非线程安全，并发 execute 可能抛 `ProgrammingError: SQLite objects created in a thread...` 或交错事务导致 `cannot commit - no transaction is active`。

**修复建议**：为连接加 `threading.Lock` 串行化（最简），或改用连接池/`threading.local` 每线程一连接。

---

## 🟢 Low（可选改进）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `guide_engine/guide_service.py` L594 | `return llm_response.content` 可能为 None，触发 pydantic ValidationError。修复：`return llm_response.content or ""`。 |
| L2 | `guide_engine/models.py` L102-109 | 全局配置/token 缓存无锁且永不过期。NagaModel 网关 access_token 首次获取后永久缓存，token 过期后不会刷新。修复：记录获取时间并设置 TTL，失败时清缓存重试。 |
| L3 | `system/config.py` L222-223 等多处 | 多处配置文件写入非原子（普通 `open("w")`），崩溃/断电可能损坏配置。对比之下 config_manager 已正确使用 `mkstemp + os.replace`，标准已存在但未统一。修复：封装 `atomic_json_write(path, data)` 并替换。 |
| L4 | `rag/vecdb_client.py` L74 附近 | `journal_mode=MEMORY` 在断电/进程崩溃时可能丢失最近事务。知识库数据可从源文档重建，影响可控，仅记录备查。如需更强持久性改回 WAL。 |

---

## ✅ 已核查确认无问题项（摘要）

| 审查点 | 结论 |
|--------|------|
| `guide_engine/neo4j_service.py` | 所有 Cypher 均参数化，label 有白名单校验 → 无注入风险 |
| `system/cors_config.py` | LOCAL_ORIGIN_REGEX 首尾锚定正确，无绕过空间 |
| `system/config.py` 密码哈希 | PBKDF2-HMAC-SHA256 + 600k 迭代 + `hmac.compare_digest`，合格 |
| `system/live2d_assets.py` | 上传路径校验 + 原子索引写入 + 失败清理，**三个目录中安全实践最好的文件** |
| `apiserver/routes/rag.py` | 路由层防护完善——问题出在下游分数量纲（C1） |
| `system/logging_setup.py`、`health_check.py`、`character_bundle.py`、`llm_params.py`、`parsing/` | 未发现实质问题 |
| `skill_manager.load_resource`（L256） | 虽无路径边界校验，但全仓库无任何调用方（死代码），不可达 |
| 集成点 | guide_engine 不被 apiserver 引用，实际调用方为 mcpserver/agentserver，接口契约一致 |

---

## 模块质量结论

- **rag/**：架构清晰但存在一个致命的分数量纲设计缺陷（C1）使整个检索链路在生产路径上恒返回空结果，加上嵌入失败的静默降级（H1），**功能可用性当前为零**，需优先修复后方可投入使用。
- **guide_engine/**：整体质量较好（Neo4j 全参数化、伤害计算引擎逻辑严谨），主要问题是 game_id 路径穿越（H2）与少量输入校验缺口，修复 H2/M3 后可放心使用。
- **system/**：安全基线扎实（CORS 锚定、强密码哈希、原子写、上传校验均达标），问题集中在 config.py 注释剥离 fallback（M1）、appearance CSS 清洗自相矛盾（M2）及若干非原子写入等持久化细节，无阻断性缺陷，属可持续改进状态。

---

*审查完成：guide_engine + rag + system | 1 Critical + 2 High + 5 Medium + 4 Low*
