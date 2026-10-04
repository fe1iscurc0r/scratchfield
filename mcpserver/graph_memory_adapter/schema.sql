-- 轻量 KG 记忆 · SQLite schema（卷139）
--
-- 借鉴 Glitch-Cat-Club/graph-memory-starter（MIT · 227★）的三表设计：
--   实体表 + 关系表 + 别名表，一条 recursive CTE 走多跳，零外部依赖。
-- 原样保留其设计意图（确定性 ID / 边携带来源 / 别名归一），
-- 本仓扩展：新增 idx_* 索引与 memory_meta（写入侧的可追溯信息）。
--
-- 设计要点（来自上游源码 src/schema.sql 与 src/build_graph.py）：
--   * id = uuid5(NAMESPACE_OID, "{type}:{normalised_name}")
--     → 同一实体在不同文档/不同轮次出现，落到同一个节点，无需 ML 消歧
--   * 条件（金额/日期/时间窗）写在实体 description 里，而不是边上
--   * source_doc 记在关系上，回答时能回溯来源（citation）

CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,   -- uuid5(type + normalised name)
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source_doc  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS relations (
    source_id  TEXT NOT NULL,
    target_id  TEXT NOT NULL,
    predicate  TEXT NOT NULL,
    source_doc TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);

CREATE TABLE IF NOT EXISTS aliases (
    entity_id TEXT NOT NULL,
    alias     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alias_text ON aliases(alias);

-- 本仓扩展：写入元信息（谁在什么时候记的，便于审计与清理）
CREATE TABLE IF NOT EXISTS memory_meta (
    entity_id  TEXT NOT NULL,
    created_at REAL NOT NULL,
    origin     TEXT NOT NULL DEFAULT ''   -- 写入来源：对话/工具/导入
);
