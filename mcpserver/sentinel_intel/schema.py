"""schema.py — 情报实体图 SQLite 三表（SPEC-09 K-01）。

表结构（对齐工单）：
- intel_entity：实体（actor/tool/infra/indicator），canonical_id 指向画像主实体
- intel_edge  ：时序关系边（uses/indicates/alias_of/observed_at），ts 支持时间线
- intel_alias ：别名登记表（resolve 命中路径缓存，source 标三级来源）

设计要点：
- WAL + busy_timeout：L/M 线同仓共用库时的单写者纪律（对照 memory_maas）
- etype/rel 白名单在代码层校验（schema 层 CHECK 会加大迁移负担，L 线还要加状态）
- 稳定实体 id：sha1(etype|normalized_value)[:16] —— 幂等入库天然成立
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

# 实体类型白名单（工单口径：actor/tool/infra/indicator）
ENTITY_TYPES = ("actor", "tool", "infra", "indicator")
# 关系白名单（SPEC-09 总纲口径：uses/indicates/alias_of/observed_at）
EDGE_RELS = ("uses", "indicates", "alias_of", "observed_at")
# 别名来源三级（工单口径）
ALIAS_SOURCES = ("hardcoded", "json", "graph")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intel_entity (
    id              TEXT PRIMARY KEY,
    etype           TEXT NOT NULL,
    value           TEXT NOT NULL,
    canonical_id    TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    weight          REAL NOT NULL DEFAULT 1.0,
    status          TEXT NOT NULL DEFAULT 'active',
    revoked_at      TEXT,
    UNIQUE (etype, value)
);
CREATE INDEX IF NOT EXISTS idx_entity_canonical ON intel_entity(canonical_id);
CREATE INDEX IF NOT EXISTS idx_entity_last_seen ON intel_entity(last_seen_at);

CREATE TABLE IF NOT EXISTS intel_edge (
    id          TEXT PRIMARY KEY,
    src_id      TEXT NOT NULL,
    dst_id      TEXT NOT NULL,
    rel         TEXT NOT NULL,
    props_json  TEXT NOT NULL DEFAULT '{}',
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edge_src ON intel_edge(src_id);
CREATE INDEX IF NOT EXISTS idx_edge_dst ON intel_edge(dst_id);
CREATE INDEX IF NOT EXISTS idx_edge_ts ON intel_edge(ts);

CREATE TABLE IF NOT EXISTS intel_alias (
    alias        TEXT NOT NULL,
    etype        TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (alias, etype)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """打开（必要时创建）情报图库：WAL + busy_timeout + Row 工厂。"""
    path = Path(db_path)
    if path != path.parent:  # 非 ':memory:'
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def entity_id(etype: str, value: str) -> str:
    """稳定实体 id：sha1(etype|规范化value)[:16] —— 同实体永远同 id（幂等根基）。"""
    return hashlib.sha1(f"{etype}|{normalize_value(value)}".encode()).hexdigest()[:16]


def edge_id(src_id: str, dst_id: str, rel: str, ts: str) -> str:
    """稳定边 id：同源同目标同关系同时刻只留一条（时序边天然多条并存）。"""
    raw = f"{src_id}|{dst_id}|{rel}|{ts}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_value(value: str) -> str:
    """匹配用规范化：strip + lower + 连字符转空格（照 zettelforge alias_resolver）。

    只用于查找键（id 生成/别名键），不用于存储展示——入库展示用 stored_value，
    否则 "relay-node-1" 入库变 "relay node 1"，返回与输入不一致。
    """
    return str(value or "").strip().lower().replace("-", " ")


def stored_value(value: str) -> str:
    """入库展示值：仅大小写归一（lower+strip），保留连字符等标点原貌。

    大小写归一保幂等（BG5GXO≡bg5gxo），标点保留保真实（域名/频段标识不失真）。
    """
    return str(value or "").strip().lower()
