"""typed 记忆实体模型 — MemoryEntity dataclass + 类型枚举 + SQLite 存储。

设计依据 POLLINATION-2026-08-28-round9（par Typed Memory Model）：
把 flat blob 记忆升级为可过滤 / 可追踪 / 可建关系的 typed 实体——
decision / insight / handoff / note 是四类不同实体，各自成为独立知识资产。

存储：独立旁路库 <data_dir>/entities.db，两张表：
    memory_entities(id, type, content, tags, pinned, source_rank, isolation,
                    created_at, observation_hash)   # typed_memories 正名即此表
    memory_relations(from_id, to_id, rel_type, created_at)
不碰 NEKO 五件套（cards.db / lineage.db / hs.db），纯 sqlite3 标准库，单写者纪律。

observation_hash（03-01 内容哈希去重，claude-mem 授粉）：捕获层对观察
（session_id+title+narrative）算 sha256 前 16 位 hex，唯一索引防重复观察入库；
重复写入返回已存在 id 不抛错（幂等）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence


class MemoryType(str, Enum):
    """typed 记忆实体类型枚举（decision/insight/handoff/note）。"""

    DECISION = "decision"
    INSIGHT = "insight"
    HANDOFF = "handoff"
    NOTE = "note"


class PlatformSource(str, Enum):
    """平台来源枚举（03-04，多端记忆 provenance 打标，claude-mem 授粉）。

    三端写入记忆时透传自身平台名；本地进程内写入默认 local。
    weixin 适配器落地前先占枚举位（写时打标不可后改，枚举先行）。
    """

    WEIXIN = "weixin"
    QQBOT = "qqbot"
    CLI = "cli"
    LOCAL = "local"


VALID_TYPES: tuple[str, ...] = tuple(m.value for m in MemoryType)
DEFAULT_TYPE: str = MemoryType.NOTE.value

# 合法平台集合 + 别名归一表（三端习惯叫法 → 枚举值）
PLATFORM_SOURCES: tuple[str, ...] = tuple(p.value for p in PlatformSource)
_DEFAULT_PLATFORM = PlatformSource.LOCAL.value
_PLATFORM_ALIASES: dict[str, str] = {
    "qq": PlatformSource.QQBOT.value,          # lumo_gateway InboundMessage 用 "qq"
    "wechat": PlatformSource.WEIXIN.value,     # 微信英文习惯叫法
    "wx": PlatformSource.WEIXIN.value,         # 微信缩写
    "terminal": PlatformSource.CLI.value,      # 终端入口别名
    "shell": PlatformSource.CLI.value,
    "": _DEFAULT_PLATFORM,
    "none": _DEFAULT_PLATFORM,
}


class EntityValidationError(ValueError):
    """typed 实体合法性校验失败（非法 type / 内容非字符串等）。"""


def normalize_type(value: Any) -> str:
    """把外部传入的 type 规整为合法枚举值，缺省为 note，非法则抛错。

    向后兼容：不传 type（None / 空串）默认 note；传了但不在枚举内 → 报错。
    """
    if value is None or value == "":
        return DEFAULT_TYPE
    if isinstance(value, MemoryType):
        return value.value
    s = str(value).strip().lower()
    if s in VALID_TYPES:
        return s
    raise EntityValidationError(
        f"非法记忆类型: {value!r}（合法值: {', '.join(VALID_TYPES)}）")


def normalize_platform(value: Any) -> str:
    """把外部传入的 platform 归一为合法枚举值（03-04 写时打标）。

    缺省 local；别名（qq/wechat/wx/terminal/shell）自动映射；
    非法值抛 EntityValidationError（写时打标 fail-fast，不留脏标）。
    """
    if value is None or str(value).strip() == "":
        return _DEFAULT_PLATFORM
    if isinstance(value, PlatformSource):
        return value.value
    s = str(value).strip().lower()
    s = _PLATFORM_ALIASES.get(s, s)
    if s in PLATFORM_SOURCES:
        return s
    raise EntityValidationError(
        f"非法平台来源: {value!r}（合法值: {', '.join(PLATFORM_SOURCES)}"
        f"；别名: qq/wechat/wx/terminal/shell）")


# source_rank 分级（与 guard.py 同源，此处仅提供默认值语义）
SOURCE_USER = 0        # 用户显式
SOURCE_AGENT = 1       # agent 自产
SOURCE_IMPORTED = 2    # 外部导入
SOURCE_UNVERIFIED = 3  # 未验证


def is_valid_type(value: Any) -> bool:
    try:
        normalize_type(value)
        return True
    except EntityValidationError:
        return False


@dataclass
class MemoryEntity:
    """typed 记忆实体（内存态表示）。relations 为出边目标 id 列表（读时投影）。"""

    id: str
    type: str = DEFAULT_TYPE
    content: str = ""
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    relations: list[str] = field(default_factory=list)
    source_rank: int = SOURCE_USER
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.type = normalize_type(self.type)
        if not isinstance(self.content, str):
            raise EntityValidationError("content 必须是字符串")
        if not isinstance(self.source_rank, int):
            raise EntityValidationError("source_rank 必须是整数")
        self.tags = _clean_tags(self.tags)
        self.relations = [r for r in (self.relations or []) if r]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "tags": list(self.tags),
            "pinned": bool(self.pinned),
            "relations": list(self.relations),
            "source_rank": int(self.source_rank),
            "created_at": float(self.created_at),
        }


def _clean_tags(tags: Iterable[str] | None) -> list[str]:
    """去重去空的 tag 列表（保序）。"""
    seen: list[str] = []
    for t in (tags or []):
        s = str(t).strip()
        if s and s not in seen:
            seen.append(s)
    return seen


class TypedMemoryStore:
    """typed 实体 + 关系图谱的 SQLite 存储（纯标准库，独立旁路库）。

    单写者纪律：进程内一把 RLock 串行化全部读写。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    # ---------------------------------------------------------------- schema

    def _ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_entities (
                    id          TEXT PRIMARY KEY,
                    type        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    tags        TEXT NOT NULL DEFAULT '[]',
                    pinned      INTEGER NOT NULL DEFAULT 0,
                    source_rank INTEGER NOT NULL DEFAULT 0,
                    isolation   INTEGER NOT NULL DEFAULT 0,
                    created_at  REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_relations (
                    from_id     TEXT NOT NULL,
                    to_id       TEXT NOT NULL,
                    rel_type    TEXT NOT NULL DEFAULT 'related',
                    created_at  REAL NOT NULL,
                    PRIMARY KEY (from_id, to_id, rel_type)
                );
                CREATE INDEX IF NOT EXISTS idx_entities_type   ON memory_entities(type);
                CREATE INDEX IF NOT EXISTS idx_entities_pinned ON memory_entities(pinned);
                """
            )
            # 03-01 旧库迁移：补 observation_hash 列（CREATE TABLE 不含，走 ALTER）
            cols = {r[1] for r in self._conn.execute(
                "PRAGMA table_info(memory_entities)").fetchall()}
            if "observation_hash" not in cols:
                self._conn.execute(
                    "ALTER TABLE memory_entities"
                    " ADD COLUMN observation_hash TEXT")
            # 03-04 旧库迁移：补 platform_source 列（历史行默认 local）
            if "platform_source" not in cols:
                self._conn.execute(
                    "ALTER TABLE memory_entities"
                    " ADD COLUMN platform_source TEXT"
                    " NOT NULL DEFAULT 'local'")
            # 唯一索引（部分索引：历史空哈希行不占坑，允许并存）
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_obs_hash"
                " ON memory_entities(observation_hash)"
                " WHERE observation_hash IS NOT NULL AND observation_hash != ''")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- 写入

    def add(self, content: str, type: str | None = None, *,
            tags: Sequence[str] | None = None,
            pinned: bool = False,
            relations: Sequence[str] | None = None,
            source_rank: int = SOURCE_USER,
            isolation: bool = False,
            entity_id: str | None = None,
            created_at: float | None = None,
            observation_hash: str | None = None,
            platform: str = _DEFAULT_PLATFORM) -> str:
        """新增实体，返回实体 id（默认 note，向后兼容）。

        observation_hash（03-01）：传入时若已存在同哈希条目，直接返回已有 id
        （幂等，不抛错、不重复入库）；否则随实体一并落库。
        platform（03-04）：写时打标平台来源（weixin/qqbot/cli/local），
        落库后不可改（供应链铁律：provenance 写时定，不后补）。
        """
        etype = normalize_type(type)
        if not isinstance(content, str):
            raise EntityValidationError("content 必须是字符串")
        psrc = normalize_platform(platform)
        obs_hash = (observation_hash or "").strip() or None
        with self._lock:
            if obs_hash:
                existing = self.find_by_observation_hash(obs_hash)
                if existing is not None:
                    return existing["id"]  # 哈希去重命中：返回已存在 id
        eid = entity_id or uuid.uuid4().hex
        tags_json = json.dumps(_clean_tags(tags), ensure_ascii=False)
        ts = float(created_at if created_at is not None else time.time())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO memory_entities"
                " (id, type, content, tags, pinned, source_rank, isolation,"
                "  created_at, observation_hash, platform_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, etype, content, tags_json,
                 int(bool(pinned)), int(source_rank), int(bool(isolation)), ts,
                 obs_hash, psrc))
            for rel in (relations or []):
                if not rel:
                    continue
                self._insert_relation(eid, rel, "related", ts)
        return eid

    def _insert_relation(self, from_id: str, to_id: str,
                         rel_type: str, ts: float | None = None) -> None:
        if from_id == to_id:
            raise EntityValidationError(f"关系循环防护: 不能自关联 {from_id!r}")
        t = float(ts if ts is not None else time.time())
        # INSERT OR IGNORE：同 from→to 同 rel_type 幂等，不重复建边
        self._conn.execute(
            "INSERT OR IGNORE INTO memory_relations"
            " (from_id, to_id, rel_type, created_at) VALUES (?, ?, ?, ?)",
            (from_id, to_id, rel_type, t))

    def update(self, entity_id: str, **fields: Any) -> dict[str, Any]:
        """按白名单字段更新实体，返回更新后的实体 dict。"""
        allowed = {"type", "content", "tags", "pinned", "source_rank", "isolation"}
        updates: dict[str, Any] = {}
        for k, v in fields.items():
            if k not in allowed:
                raise EntityValidationError(f"不支持的更新字段: {k!r}")
            if k == "type":
                v = normalize_type(v)
            elif k == "tags":
                v = json.dumps(_clean_tags(v), ensure_ascii=False)
            elif k in ("pinned", "source_rank", "isolation"):
                v = int(bool(v))
            updates[k] = v
        if not updates:
            return self.get(entity_id)  # type: ignore[return-value]
        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT id FROM memory_entities WHERE id = ?", (entity_id,))
            if cur.fetchone() is None:
                raise EntityValidationError(f"实体不存在: {entity_id!r}")
            cols = ", ".join(f"{k} = ?" for k in updates)
            self._conn.execute(
                f"UPDATE memory_entities SET {cols} WHERE id = ?",
                (*updates.values(), entity_id))
        return self.get(entity_id)  # type: ignore[return-value]

    def set_pinned(self, entity_id: str, pinned: bool = True) -> dict[str, Any]:
        return self.update(entity_id, pinned=pinned)

    def delete(self, entity_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM memory_entities WHERE id = ?", (entity_id,))
            return cur.rowcount > 0

    # ---------------------------------------------------------------- 关系图谱

    def add_relation(self, from_id: str, to_id: str,
                     rel_type: str = "related") -> dict[str, Any]:
        """建立有向关系（from → to）。仅要求 from 存在；拒绝自关联。"""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT id FROM memory_entities WHERE id = ?", (from_id,))
            if cur.fetchone() is None:
                raise EntityValidationError(f"from 实体不存在: {from_id!r}")
            self._insert_relation(from_id, to_id, rel_type)
        return {"ok": True, "from_id": from_id, "to_id": to_id,
                "rel_type": rel_type}

    def get_relations(self, entity_id: str,
                      rel_type: str | None = None) -> list[dict[str, Any]]:
        """出边关系列表（含 rel_type / created_at）。"""
        with self._lock:
            if rel_type is None:
                rows = self._conn.execute(
                    "SELECT to_id, rel_type, created_at FROM memory_relations"
                    " WHERE from_id = ? ORDER BY created_at", (entity_id,)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT to_id, rel_type, created_at FROM memory_relations"
                    " WHERE from_id = ? AND rel_type = ? ORDER BY created_at",
                    (entity_id, rel_type)).fetchall()
        return [{"to_id": r["to_id"], "rel_type": r["rel_type"],
                 "created_at": r["created_at"]} for r in rows]

    def traverse(self, entity_id: str, max_hops: int = 1) -> dict[str, Any]:
        """单跳（可多跳）图遍历，visited 集合防环。返回按深度分组的邻接节点。"""
        max_hops = max(1, int(max_hops))
        seen: set[str] = {entity_id}
        visited: list[str] = [entity_id]
        frontier = [entity_id]
        hops: list[list[dict[str, Any]]] = []
        with self._lock:
            for _ in range(max_hops):
                nxt: list[dict[str, Any]] = []
                for src in frontier:
                    for rel in self.get_relations(src):
                        if rel["to_id"] in seen:
                            continue  # 环 / 重复访问防护
                        seen.add(rel["to_id"])
                        visited.append(rel["to_id"])
                        nxt.append({"id": rel["to_id"],
                                    "rel_type": rel["rel_type"], "via": src})
                if not nxt:
                    break
                hops.append(nxt)
                frontier = [n["id"] for n in nxt]
        return {"ok": True, "root": entity_id, "max_hops": max_hops,
                "visited": visited, "hops": hops}

    # ---------------------------------------------------------------- 查询

    # provenance confidence 映射（供应链铁律：与 origin_rank 同源写时定级，
    # 读时确定性投影，可复算可对账）
    _RANK_CONFIDENCE: dict[int, float] = {0: 0.9, 1: 0.7, 2: 0.4, 3: 0.2}

    def _row_to_entity(self, row: sqlite3.Row) -> dict[str, Any]:
        with self._lock:
            rels = self._conn.execute(
                "SELECT to_id FROM memory_relations WHERE from_id = ?"
                " ORDER BY created_at", (row["id"],)).fetchall()
        rank = int(row["source_rank"])
        platform = row["platform_source"]
        return {
            "id": row["id"],
            "type": row["type"],
            "content": row["content"],
            "tags": json.loads(row["tags"] or "[]"),
            "pinned": bool(row["pinned"]),
            "relations": [r["to_id"] for r in rels],
            "source_rank": rank,
            "isolation": bool(row["isolation"]),
            "created_at": row["created_at"],
            "observation_hash": row["observation_hash"],
            "platform_source": platform,
            # provenance 必填（03-04）：source=平台来源 / ts=写时戳 /
            # confidence=来源分级置信 / origin_rank=来源分级
            "provenance": {
                "source": platform,
                "ts": float(row["created_at"]),
                "confidence": self._RANK_CONFIDENCE.get(rank, 0.2),
                "origin_rank": rank,
            },
        }

    def find_by_observation_hash(self, observation_hash: str) -> dict[str, Any] | None:
        """按内容哈希查条目（03-01 去重前置查询）；无则 None。"""
        h = (observation_hash or "").strip()
        if not h:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_entities WHERE observation_hash = ?",
                (h,)).fetchone()
        return self._row_to_entity(row) if row is not None else None

    def get(self, entity_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_entities WHERE id = ?",
                (entity_id,)).fetchone()
        return self._row_to_entity(row) if row is not None else None

    def list_entities(self, type: str | None = None,
                      tags: Sequence[str] | None = None,
                      pinned: bool | None = None,
                      source_rank_min: int | None = None,
                      source_rank_max: int | None = None,
                      path: str | None = None,
                      project_root: str | Path | None = None,
                      platform: str | None = None,
                      limit: int | None = None) -> list[dict[str, Any]]:
        """按 type / tags（AND 语义）/ pinned / source_rank 区间 / path /
        platform 过滤实体。

        path（03-02 多路径匹配）：对查询路径生成绝对/项目根相对/cwd 相对三种
        归一化形式，任一形式在 content 或 tags 中命中即返回（防 claude-mem
        #2691 单写法落库后其他写法检索不中的坑）。
        platform（03-04）：平台来源过滤，别名自动归一（qq→qqbot）。
        """
        where: list[str] = []
        params: list[Any] = []
        if type is not None:
            where.append("type = ?")
            params.append(normalize_type(type))
        if platform is not None:
            where.append("platform_source = ?")
            params.append(normalize_platform(platform))
        clean = _clean_tags(tags)
        if clean:
            for t in clean:
                where.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        if pinned is not None:
            where.append("pinned = ?")
            params.append(int(bool(pinned)))
        if source_rank_min is not None:
            where.append("source_rank >= ?")
            params.append(int(source_rank_min))
        if source_rank_max is not None:
            where.append("source_rank <= ?")
            params.append(int(source_rank_max))
        if path:
            from mcpserver.memory_maas.paths import path_like_patterns
            pats = path_like_patterns(path, project_root)
            if pats:
                forms = []
                for p in pats:  # 三形式任一命中：content 或 tags
                    forms.append("(content LIKE ? OR tags LIKE ?)")
                    params.extend([p, p])
                where.append("(" + " OR ".join(forms) + ")")
        sql = "SELECT * FROM memory_entities"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += f" LIMIT {max(0, int(limit))}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def count(self, type: str | None = None) -> int:
        if type is None:
            with self._lock:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM memory_entities").fetchone()[0]
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM memory_entities WHERE type = ?",
                (normalize_type(type),)).fetchone()[0]

    def all_relations(self) -> list[dict[str, Any]]:
        """全量关系表（快照导出用）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT from_id, to_id, rel_type, created_at"
                " FROM memory_relations ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def clear(self) -> int:
        """清空实体与关系（快照回滚前调用）。返回被清实体数。"""
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM memory_entities")
            n = cur.rowcount
            self._conn.execute("DELETE FROM memory_relations")
        return n
