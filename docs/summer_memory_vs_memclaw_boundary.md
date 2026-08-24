# summer_memory vs. memclaw：职责边界与演进路线

> 面向后续维护者：`summer_memory` 是 scratchpad 项目**原生且紧耦合的主记忆系统**；
> `memclaw` 是从 `vendor/top5/caura-memclaw` 引入的**跨 Agent 记忆总线**，仅作为 MCP 能力
> 包暴露给"能力侧路由/多 Agent 协作"，**不接管任何主链路记忆**。
> 两者在存储介质、数据模型、召回路径、调用时机上都**没有重叠的主路径**。

---

## 1. 职责速查表

| 维度                  | summer_memory (GRAG)                                   | memclaw (vendor adapter)                                 |
|-----------------------|--------------------------------------------------------|----------------------------------------------------------|
| **角色**              | 项目主记忆系统，主链路必走                              | 第三方能力包，可选外挂（可被 ENABLE_ADAPTER_MEMCLAW=0 关掉） |
| **核心产物**          | 五元组 `(e1, r, e2, t, extra)` 知识图谱                | Episodic + Profile + Preference + Summary 文档块        |
| **入库方式**          | 主对话流水 `add_conversation_memory`（apiserver 直接调）| 通过 MCP 工具 `memclaw_remember` 等**显式**触发          |
| **主链路召回**        | `lumo_proxy._query_grag_summer_memory`，在 prompt 注入前 | 不参与主 prompt 注入；只能被 LLM 主动调用工具读回         |
| **存储后端**          | Neo4j + 本地 `quintuples.json`（当前主项目代码里）     | SQLite standalone (`MEMCLAW_DB_PATH`) / PG+pgvector (server 部署可选) |
| **索引技术**          | 图谱关系 + 关键词匹配                                  | BM25 文档搜索 + 可选向量 enrich（没 key 时降级 BM25 即可）|
| **谁是权威源(SSOT)**  | **是**（用户长期记忆的 SSOT 之一）                     | **否**（它自己的库是 ephemeral；若未来要合入主链路，先回灌 summer_memory） |
| **并发写入/锁**       | 由 apiserver 进程统一管理                               | 通过 SqliteBackend 表级事务；memclaw 自己的锁             |
| **清空数据方式**      | `summer_memory/` 下的 json/neo4j 数据库                 | 删 `MEMCLAW_DB_PATH` 文件（默认 `~/.cache/mygit/memclaw.sqlite.db`） |

---

## 2. 典型调用链路，各自独立

### 2.1 summer_memory（主链路，被动写 + 被动读）

```
用户消息 → apiserver/routes/chat 或 message_manager
        │
        ├─► 写：memory_manager.add_conversation_memory(user, ai)
        │        └─► quintuple_extractor → quintuple_graph.store_quintuples(Neo4j / quintuples.json)
        │
        └─► 读：lumo_proxy._hybrid_recall()（3s 超时保护）
                 ├─► _query_grag_summer_memory()  → summer_memory query_graph_by_keywords()
                 └─► _query_rag_standalone()      → 本地向量 RAG
                 └─► 合并结果注入 system prompt
```

- **不经过 MCP**，主链路直接 import `summer_memory.*`；
- 写入是 **post-chat 异步回调**（task_manager 里还带并发队列/失败 fallback）；
- 读是 **prompt 组装前同步召回（3s 超时→降级跳过）**，失败不影响主对话。

### 2.2 memclaw（能力包，主动调用）

```
LLM 决定"跨会话/跨 agent 想记住/检索一条记忆"
        │
        └─► 调用 MCP 工具：memclaw_remember / memclaw_search / memclaw_recall_session
                 └─► mcpserver/adapters/memclaw.py
                          ├─► sys.path 注入 vendor/top5/caura-memclaw/...
                          ├─► ensure_standalone_backend() → SqliteBackend()
                          └─► memory_core.* 的读写 API
```

- **不进入主 prompt 注入链路**；它只能被 LLM 自己在"工具调用回合"读回；
- 写入通常对应某个 agent 的**显式指令**（"记住这个结论，下次接着用"），不是流水账；
- DB 默认放在 `~/.cache/mygit/memclaw.sqlite.db`，完全独立于 summer_memory。

---

## 3. 为什么不用 memclaw 直接换掉 summer_memory

不是技术能不能，而是**迁移成本 / 收益比不成立**：

1. **主链路数据模型不兼容**：summer_memory 的五元组是为 GRAG 关系推理优化的；
   memclaw 的文档块模型是为"跨 Agent 消息摘要"优化的。直接替换要重写：
   - `quintuple_extractor.py` 五元组抽取
   - `quintuple_graph.py` Neo4j 存储与查询
   - `apiserver/routes/lumo_proxy.py` 混合召回的两条分支与 3s 超时兜底
   - 所有依赖 `memory_manager / get_all_quintuples / query_graph_by_keywords` 的调用点
2. **SSOT 风险**：summer_memory 当前还承担"离线/无 PG/无向量时也能用"的降级保证；
   memclaw 的 enrich 在没 key 时虽可跑 BM25，但**召回语义能力和线上已验证的 GRAG 不等价**。
3. **线上历史数据**：如果迁移，需要设计一条 `quintuples.json → memclaw Episodic 档` 的回灌脚本，
   并且要支持双向回滚（出问题切回 summer_memory）。这不是一个"薄适配器"能解决的事。

---

## 4. 未来演进建议（两条可能路径，分阶段）

### 路径 A：保守长期共存（推荐，**默认选择**）

- **Phase 1（当前即完成）**：memclaw 仅通过 MCP 工具暴露，供多 Agent / 能力侧使用；
  summer_memory 继续是主链路 SSOT。
- **Phase 2（如果确实需要两条记忆对齐）**：新增一个**单向同步器**，仅把
  `summer_memory` 五元组摘要 **回灌** 进 memclaw，方向是 `summer_memory → memclaw`，
  不反向，保证 SSOT 唯一。同步器示例接口：

  ```python
  # summer_memory/integrations/memclaw_sync.py（建议未来新建，不在本次任务里落地）
  async def sync_quintuples_snapshot_to_memclaw(limit: int = 500) -> int:
      """把 summer_memory 最新 N 条五元组转成 1-sentence/条的 memclaw episodic 记忆。"""
  ```

- **Phase 3（远未来）**：抽象一个 `memory_backend` 接口，允许后端在 Neo4j /
  MemClaw SQLite / PG 间可插拔，再做平滑 A/B。

### 路径 B：激进替换（不推荐）

- 必须补齐：回灌脚本、A/B 召回质量测试、主 prompt 注入兜底、迁移 rollback 开关、
  老数据保留期策略、`lumo_proxy` 双写观察期。整体工作量 ≥ 1 个迭代，在当前任务中不做。

---

## 5. 已落地的隔离措施清单

为防止两者边界被误踩，本次已落地如下**硬隔离**：

1. **独立存储**：
   - summer_memory：`summer_memory/quintuples.json` + Neo4j；
   - memclaw adapter：`os.environ["MEMCLAW_DB_PATH"]` 默认
     `~/.cache/mygit/memclaw.sqlite.db`，项目根目录下**没有** sqlite 文件。
2. **独立 import 路径**：
   - summer_memory：主路径，直接 `from summer_memory.xxx import ...`；
   - memclaw：必须走 `mcpserver/adapters/memclaw.py` 里的 `_ensure_vendor_path()`
     才会把 `vendor/top5/caura-memclaw/...` 注入 sys.path，主链路不直接 import。
3. **功能开关**：`ENABLE_ADAPTER_MEMCLAW=0` 直接禁用 memclaw 注册，对 summer_memory 零影响。
4. **register_capability 两条线**：
   - summer_memory 走 `MANIFEST_CACHE`（作为 `apiserver/agentserver` 的一个能力由主链路管理）；
   - memclaw 走 `_ADAPTER_CAPABILITIES`（`mcp_registry.register_capability`）。
5. **无跨写回**：memclaw 的 `remember() / enrich()` **不会**反向写入
   `summer_memory.quintuples.json` 或 Neo4j；避免 SSOT 分裂。

---

## 6. 维护中常见坑 & 正确做法

| ❌ 坑                                               | ✅ 正确做法                                                                 |
|-----------------------------------------------------|-----------------------------------------------------------------------------|
| 在 `lumo_proxy` 主召回里直接 `import memclaw.*`     | 如需跨记忆读：先把 memclaw 结果作为**第三路召回分支**，和 GRAG/vector 并列，并单独加 2s 超时。 |
| 让 memclaw adapter 直接调 `memory_manager.add_conversation_memory` | 双写会引入 SSOT 分裂；真要对齐走 Phase 2 单向回灌脚本，**别在 adapter 热路径硬接**。 |
| 把 `MEMCLAW_DB_PATH` 设到 `summer_memory/` 下       | 保持默认 `~/.cache/mygit/`，别让用户误删 summer_memory 时顺带把 memclaw 也清空。 |
| 在 `ENABLE_ADAPTER_MEMCLAW=0` 场景下假设 memclaw 已存在 | 所有调用前先走 `mcp_registry.list_registered_capabilities()` 查是否存在 memclaw。 |
