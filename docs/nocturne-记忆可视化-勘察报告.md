# nocturne_memory 记忆可视化/回滚 · 勘察报告（智能体 NOVEMBER / N-01）

> 勘察对象：`Dataojitori/nocturne_memory`（1335★，MIT，Python，扫货日报 2026-08-27 Top2）
> 勘察性质：只读——直拉上游 README + 目录结构 + 关键源码，对照 NEKO 记忆层（`NEKO/N.E.K.O/memory/`）
> 结论一句话：**借鉴设计模式，不引整包**。nocturne 的「快照 + 回滚 + 可视化 diff」三层是 NEKO 目前缺失的
> 能力，但其形态是独立 MCP 服务器 + 自有 DB schema，直接接入代价大于收益；把「导出→快照→恢复点列表→
> 回滚」这套机制降维成纯标准库旁路，即可补齐 NEKO 的调试短板且零侵入主流程。

---

## 1. 上游架构速览（nocturne_memory）

### 1.1 一句话定位

轻量、可回滚、可视化的 MCP 长期记忆服务器——用「图状结构化记忆 + URI 寻址 + 版本链 + 人类审核面板」
替代 Vector RAG，号称「百万字记忆、新会话省 Token、跨模型同一人格」。定位为 OpenClaw 的 drop-in 平替。

### 1.2 目录结构（main 分支）

```
backend/
  main.py / run_sse.py / mcp_server.py / mcp_wrapper.py   # 三个入口：HTTP / SSE / stdio MCP
  api/          browse / build / maintenance / presets / review / settings / utils
  db/
    database.py  models.py  graph.py  search.py  search_terms.py
    neo4j_client.py          # 旧 Neo4j 后端迁移脚本仍在（migrate_neo4j_to_sqlite.py）
    snapshot.py              # ★ 快照/回滚核心（ChangesetStore）
    migrations/              # 001~014 版本化迁移，迁移前自动备份 DB 文件
  web_app.py / frontend_builder.py / auth.py / namespace_middleware.py
frontend/     React + Vite + TailwindCSS（Memory Explorer / DiffViewer / SnapshotList / Review）
docs/         TOOLS.md + 5 个 memory-audit 子技能（SKILL.md）
```

### 1.3 五个勘察点逐一确认

| 勘察点 | 结论 | 证据 |
|--------|------|------|
| **存储后端** | SQLite（默认）/ PostgreSQL，SQLAlchemy 异步 ORM；旧 Neo4j 已迁走 | `requirements.txt`：`sqlalchemy` + `aiosqlite` + `asyncpg`；`db/neo4j_client.py` + `scripts/migrate_neo4j_to_sqlite.py` |
| **数据模型** | 图状：`nodes`（概念锚点）/ `memories`（内容版本）/ `edges`（有向关系）/ `paths`（URI 路由）/ `glossary_keywords`，支持 namespace 隔离 | `db/models.py`；README「数据模型」图：内容更新不改变身份，版本链 + 废弃标记 |
| **可视化机制** | Web Dashboard（React SPA，FastAPI 内嵌 serve）：树状 Memory Explorer、实时编辑、**Review & Audit 可视化 diff（一键接受/回滚）**、Brain Cleanup | README §326；`frontend/src/components/DiffViewer.jsx`、`SnapshotList.jsx`；`diff_match_patch` + `jieba` 做中文 diff |
| **回滚机制** | 双层：① `ChangesetStore`（行级 before/after 快照，`snapshots/changeset.json` + FileLock）→ `review.py` 按 `node_uuid` 分组做「通用回滚」（`rollback_group`）；② 版本链 `deprecated` + `migrated_to`（每次 update 生成新版本，旧版本留存可一键恢复） | `db/snapshot.py`（overwrite 语义 + `_gc_noop_creates` 级联清理）；`api/review.py:rollback_group`（纯数据驱动回滚：节点新建→级联删、路径删→恢复、边改→UPDATE、记忆改→复活旧版本） |
| **MCP 接口形态** | FastMCP（stdio + SSE 双传输），工具 7 个：`read_memory / create_memory / update_memory / delete_memory / add_alias / manage_triggers / search_memory`，URI 寻址（`core://agent/...`） | `mcp_server.py`：`@mcp.tool()` × 7；`mcp_wrapper.py` 修 Windows CRLF 流 |
| **运行依赖** | 重量级 Web 栈：FastAPI、uvicorn、SQLAlchemy、mcp、pydantic、diff_match_patch、jieba、pyahocorasick、filelock、Pillow、pypinyin + React 前端 + Docker | `backend/requirements.txt`；`docker-compose.yml`；前端需要 node 构建 |

### 1.4 回滚机制原文解读（值得借鉴的核心）

nocturne 的回滚不是「全库备份文件」，而是**行级 changeset 累积 + 按节点分组 + 数据驱动还原**：

1. **写时快照**：每次 AI 写记忆，`ChangesetStore.record()` 把该行的 `before` / `after` 存进单一 `changeset.json`。首次触碰某主键冻结 `before`，后续触碰只覆盖 `after`。
2. **净零过滤**：`before == after` 的行自动从展示里过滤；`_gc_noop_creates` 清掉「建了又删」的孤儿级联。
3. **因果锚点**：`_get_causal_anchors` 把「删节点→删路径→弃边」的级联折叠回根节点，避免「回滚一半导致外键断裂」。
4. **通用回滚**：`rollback_group(node_uuid)` 不存操作日志，而是动态检查 before 状态精确还原——节点是新建的→整棵级联删；路径删了→按父先子后恢复；边改了→UPDATE；记忆改了→复活旧版本。
5. **人工确认**：删除/清理需人类明确确认；迁移前自动备份 DB 文件（`.bak`）。

这套「**导出 → 快照 → 恢复点列表 → 回滚前强制备份 → 精确还原**」的模式，正是 NEKO 需要的。

---

## 2. NEKO 记忆层现状对照

NEKO 记忆层（`NEKO/N.E.K.O/memory/`）已具备的能力：

| 模块 | 能力 | 来源模式 |
|------|------|----------|
| `hooks.py` | 6 事件生命周期钩子（prefetch/sync_turn/on_session_end/on_pre_compress/on_memory_write/system_prompt_block），默认关闭、幂等、fail-safe | agentmemory |
| `enrichment.py` | 索引卡增强管线（LLM + 规则降级，六字段契约永不失败） | caura |
| `memory_graph.py` | SQLite 递归 CTE 记忆关联图谱（对称/非对称关系、多跳遍历、最短路径、子图） | mcp-memory-service |
| `facts.py` / `recent.py` / `timeindex.py` / `evidence.py` / `reflection.py` / `hybrid_recall.py` / `embeddings.py` | 事实存储、会话历史、时间索引、证据、反思、混合召回、向量 | 自研 + 授粉 |
| `index_cards/` / `lineage/` / `lifecycle/` / `compaction_v2/` | 索引卡、血统、压缩 | 授粉 |
| 存储落盘 | 每角色目录：`facts.json / persona.json / recent.json / time_indexed.db / settings.json ...`（`_MIGRATION_MAP`） | 自研 |

### NEKO 差距表（nocturne 有、NEKO 缺）

| # | 能力 | nocturne 提供 | NEKO 现状 | 差距判定 |
|---|------|---------------|-----------|----------|
| G1 | **可视化记忆浏览器** | React Dashboard：树状浏览、实时编辑、diff 视图 | 无 Web 记忆浏览器（仅测试脚本 `gen_memory_fold_map.py` 打目录） | **缺**（但旁路可先不做 UI，CLI + JSON 快照已是「最小可视化」） |
| G2 | **快照 / 恢复点列表** | `ChangesetStore` + `snapshots/` 目录 | 只有 `facts_archive.json` 追加归档 + 迁移备份，无「用户可命名的恢复点」 | **缺**（N-02 补齐） |
| G3 | **回滚前强制备份** | 迁移前 `.bak`；回滚前保留 before 状态 | 回滚无强制备份当前态（`cloudsave_runtime` 有备份但面向云同步，非调试回滚） | **缺**（N-02 补齐） |
| G4 | **行级 before/after diff** | `DiffViewer` + `diff_match_patch` 中文 diff | 无 diff 可视化 | **缺**（旁路 JSON 快照可含 hash 供比对，UI 后置） |
| G5 | **人类审核门** | Review & Audit + Brain Cleanup 需确认 | 无人类确认门 | **缺**（回滚 CLI 交互确认可覆盖） |
| G6 | **MCP 工具集** | 7 个 MCP 工具 | NEKO 走自研 main_routers/memory_server，不暴露 MCP 记忆工具 | 不适用（定位不同，不追平） |

> NEKO 的 hooks / 图谱 CTE / enrichment 是 nocturne **没有**的（nocturne 无 6-hook 生命周期、无 enrichment 索引卡、无递归 CTE 图谱——它的图是节点/边表）。两系统互补，非替代。

---

## 3. 落地建议

### 结论：**借鉴设计模式（borrow），不接入整包（not integrate），不弃用（not abandon）**

理由：

1. **「接入」不可行也不划算**：nocturne 是独立 MCP 服务器，自带 DB schema（nodes/memories/edges/paths + namespace + 迁移链），要接入就得「跑第二个服务 + 数据迁移 + 改主流程」，直接违反本线「旁路零侵入」硬约束，且拉进 FastAPI/React 整条 Web 栈。

2. **「借鉴」可低成本补齐短板**：真正有价值的是 **G2/G3/G4 那套机制**（导出 → 快照 → 恢复点列表 → 回滚前强制备份 → 精确还原），它可以降维成纯标准库旁路，直接作用于 NEKO 每角色记忆目录（JSON + SQLite 文件），不动 `memory/` 主流程任何文件。

3. **「弃用」浪费了扫货价值**：nocturne 的「行级 changeset + 数据驱动通用回滚 + 人工确认」是调试记忆漂移的正确范式，值得内化为设计文档供后续参考（尤其 G4 的 diff 可视化和 G5 的确认门，作为未来 UI 化方向记录在案，不在本次写码范围）。

### 落地映射（N-02 依据本结论执行）

| nocturne 机制 | NEKO 旁路落地 |
|---------------|----------------|
| `ChangesetStore`（写时行级 before/after） | `snap.py`：导出每角色记忆目录现状为 JSON 快照（含文件内容 + sha256 + 恢复点元数据），落独立 `memory_snapshot/` 目录，不污染记忆目录 |
| `snapshots/` 目录 + 恢复点列表 | `snap.py` 的 `list` 子命令：列出全部快照与恢复点标记 |
| 回滚前强制备份（`.bak` / before 态） | `rollback.py`：restore 前先只读校验（坏快照报错），再**强制备份当前态**，最后回写 |
| `rollback_group`（数据驱动精确还原） | `rollback.py`：按快照文件逐文件还原（只读校验 → 备份 → 回写） |
| 可视化 diff / 审核门（G1/G4/G5） | **不在 N-02 写码范围**——记为未来方向：JSON 快照天然可 diff，UI 化可后置 |

### 未来方向（记录在案，本次不做）

- G1 可视化：把快照 JSON 挂一个只读网页浏览器（nocturne 的 `DiffViewer.jsx` 模式值得借鉴）。
- G4 diff：快照含 sha256，可做「两次快照逐文件 diff」。
- G5 确认门：CLI restore 加 `--yes` 交互确认。

---

## 4. 附：验收口径

- 本报告落盘 `docs/nocturne-记忆可视化-勘察报告.md`，含：架构说明（§1）→ NEKO 差距表（§2）→ 明确落地建议（§3，借鉴 + 理由）。
- 只读勘察：未 copy nocturne 代码；未评估记忆内容对错，只评估机制。
- N-02 按本结论「借鉴」分支执行：纯标准库旁路快照/回滚，不动 `memory/` 主流程。
