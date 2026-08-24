"""memory_graph — 记忆关联图谱（授粉自 doobidoo/mcp-memory-service）。

授粉源：mcp-memory-service/storage/graph.py（Apache-2.0）
  - store_association：对称关系存双向边（related/contradicts），非对称存有向边
    （causes/fixes/supports/follows）
  - find_connected：递归 CTE 多跳遍历（BFS，含 cycle 预防）
  - shortest_path / get_subgraph / get_relationship_types

落地目标：NEKO 记忆层「会话血统图」的补充——lineage（线性父子）之上加
「关联图谱」（任意两条记忆之间的多跳关系），纯 SQLite 实现，旁路设计，
不触碰 NEKO 现有 FactStore / time_indexed.db / hybrid_recall 路径。

License: Apache-2.0（机制同源 mcp-memory-service；实现独立重写）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 对称关系：A→B 与 B→A 等价，存双向边
SYMMETRIC_RELATIONSHIPS = frozenset({"related", "contradicts"})
# 非对称关系：只存 A→B 有向边（supersedes：矛盾检测新值取代旧值，F-03）
ASYMMETRIC_RELATIONSHIPS = frozenset({"causes", "fixes", "supports", "follows", "supersedes"})
VALID_RELATIONSHIPS = SYMMETRIC_RELATIONSHIPS | ASYMMETRIC_RELATIONSHIPS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_graph (
    source_hash   TEXT NOT NULL,
    target_hash   TEXT NOT NULL,
    similarity    REAL NOT NULL DEFAULT 0.0,
    connection_types TEXT NOT NULL DEFAULT '[]',
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    REAL NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'related',
    PRIMARY KEY (source_hash, target_hash, relationship_type)
);
CREATE INDEX IF NOT EXISTS idx_mg_source ON memory_graph(source_hash);
CREATE INDEX IF NOT EXISTS idx_mg_target ON memory_graph(target_hash);
"""

# 多跳遍历：SQLite 递归 CTE（neighbors 视图合并「出边+对称入边」后单递归）。
# 坑：SQLite WITH RECURSIVE 只允许单个递归成员——多分支 UNION ALL 各自引用
# reach 会触发 `circular reference: reach`。解法：先用非递归 CTE 把
# 「有向出边 + 对称入边（related/contradicts 反向）」展平成邻居视图，
# 递归只发生在单一 reach 分支上，语义等价且无歧义。

def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def normalize_entity_id(name: str) -> str:
    """规范化实体 ID：strip + 小写 + 空格压平。"""
    return " ".join(name.strip().lower().split())


class MemoryGraph:
    """记忆关联图谱（SQLite 递归 CTE）。"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def is_symmetric(self, relationship_type: str) -> bool:
        return relationship_type in SYMMETRIC_RELATIONSHIPS

    def store_association(
        self,
        source_hash: str,
        target_hash: str,
        similarity: float = 0.5,
        connection_types: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
        relationship_type: str = "related",
    ) -> bool:
        """存储记忆关联。

        - 对称关系（related/contradicts）：存 A→B 与 B→A 双向边
        - 非对称关系（causes/fixes/supports/follows）：只存 A→B
        """
        source_hash = normalize_entity_id(source_hash)
        target_hash = normalize_entity_id(target_hash)
        if not source_hash or not target_hash:
            logger.error("store_association: 空 hash")
            return False
        if source_hash == target_hash:
            logger.warning("store_association: 拒绝自环 %s", source_hash)
            return False
        if not (0.0 <= similarity <= 1.0):
            logger.error("store_association: similarity %s 越界", similarity)
            return False
        if relationship_type not in VALID_RELATIONSHIPS:
            logger.error("store_association: 非法关系类型 %s", relationship_type)
            return False
        if created_at is None:
            created_at = _now()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn_json = json.dumps(connection_types or [], ensure_ascii=False)

        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            try:
                # 正向边
                cursor.execute(
                    """INSERT OR REPLACE INTO memory_graph
                       (source_hash, target_hash, similarity, connection_types,
                        metadata, created_at, relationship_type)
                       VALUES (?,?,?,?,?,?,?)""",
                    (source_hash, target_hash, similarity, conn_json,
                     meta_json, created_at, relationship_type),
                )
                # 对称关系补反向边
                if self.is_symmetric(relationship_type):
                    cursor.execute(
                        """INSERT OR REPLACE INTO memory_graph
                           (source_hash, target_hash, similarity, connection_types,
                            metadata, created_at, relationship_type)
                           VALUES (?,?,?,?,?,?,?)""",
                        (target_hash, source_hash, similarity, conn_json,
                         meta_json, created_at, relationship_type),
                    )
                conn.commit()
                return True
            finally:
                cursor.close()
                conn.close()

    def find_connected(
        self,
        memory_hash: str,
        max_hops: int = 2,
        relationship_type: Optional[str] = None,
    ) -> List[Tuple[str, int]]:
        """多跳遍历：返回 [(hash, distance), ...]，按距离升序。

        方向语义：对称关系（related/contradicts）双向可达；
        非对称关系（causes/fixes/supports/follows）只沿出边（source→target）可达。
        """
        memory_hash = normalize_entity_id(memory_hash)
        if not memory_hash:
            return []
        if max_hops < 1:
            return []

        relationship_filter = ""
        params2: List[Any] = [memory_hash]
        if relationship_type is not None:
            relationship_filter = "AND rel = ?"
            params2.append(relationship_type)
        # 递归最大跳数
        params2.append(max_hops)

        # 递归 CTE：邻居扩展尊重方向性
        #  出边：source = 当前节点 → target（有向，全部关系类型）
        #  入边：target = 当前节点 且 关系对称 → source（仅 related/contradicts 允许反向）
        #  relationship_filter 只加在出边（入边已用 IN 限定对称类型，不叠加）
        #
        # 注意：SQLite WITH RECURSIVE 只允许单个递归引用（reach 只出现在一个
        # UNION ALL 分支的 FROM 中）。这里把「出边 + 对称入边」合并成一个
        # 邻居视图，再用单递归分支扩展，避免 circular reference。
        query = f"""
        WITH RECURSIVE
        neighbors(node, nbr, rel) AS (
            SELECT source_hash, target_hash, relationship_type FROM memory_graph
            UNION ALL
            SELECT target_hash, source_hash, relationship_type FROM memory_graph
            WHERE relationship_type IN ('related', 'contradicts')
        ),
        reach(hash, distance, path) AS (
            SELECT nbr, 1, ',' || nbr || ','
            FROM neighbors
            WHERE node = ?
              {relationship_filter}
            UNION ALL
            SELECT nbr, r.distance + 1, r.path || nbr || ','
            FROM reach r
            JOIN neighbors n ON n.node = r.hash
            WHERE r.distance < ?
              AND instr(r.path, ',' || nbr || ',') = 0
        )
        SELECT hash, MIN(distance) AS distance FROM reach
        GROUP BY hash
        ORDER BY distance;
        """

        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            try:
                rows = cursor.execute(query, params2).fetchall()
                return [(r["hash"], r["distance"]) for r in rows]
            finally:
                cursor.close()
                conn.close()

    def shortest_path(
        self, source_hash: str, target_hash: str
    ) -> Optional[List[str]]:
        """BFS 最短路径（双向）。返回 [source, ..., target] 或 None。"""
        source_hash = normalize_entity_id(source_hash)
        target_hash = normalize_entity_id(target_hash)
        if source_hash == target_hash:
            return [source_hash]

        with self._lock:
            conn = self._get_conn()
            try:
                # BFS：逐层扩展，父节点映射表
                visited: set[str] = {source_hash}
                queue: list[str] = [source_hash]
                parent: dict[str, str | None] = {source_hash: None}
                while queue:
                    node = queue.pop(0)
                    rows = conn.execute(
                        """SELECT CASE WHEN source_hash = ? THEN target_hash ELSE source_hash END AS nbr
                           FROM memory_graph WHERE source_hash = ? OR target_hash = ?""",
                        (node, node, node),
                    ).fetchall()
                    for r in rows:
                        nbr: str = r["nbr"]
                        if nbr in visited:
                            continue
                        visited.add(nbr)
                        parent[nbr] = node
                        if nbr == target_hash:
                            # 回溯路径
                            path: list[str] = [target_hash]
                            cur: str | None = target_hash
                            while cur is not None and parent[cur] is not None:
                                path.append(parent[cur] or "")
                                cur = parent[cur]
                            return list(reversed(path))
                        queue.append(nbr)
                return None
            finally:
                conn.close()

    def get_relationship_types(self, memory_hash: str) -> Dict[str, int]:
        """统计某记忆的关联类型分布。"""
        memory_hash = normalize_entity_id(memory_hash)
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT relationship_type, COUNT(*) AS cnt
                       FROM memory_graph
                       WHERE source_hash = ? OR target_hash = ?
                       GROUP BY relationship_type""",
                    (memory_hash, memory_hash),
                ).fetchall()
                return {r["relationship_type"]: r["cnt"] for r in rows}
            finally:
                conn.close()

    def get_subgraph(
        self, memory_hash: str, max_hops: int = 1
    ) -> Dict[str, Any]:
        """子图提取（F-03 多跳化）：返回 {nodes: [...], edges: [...]}。

        nodes = 起点 + find_connected(max_hops) 可达集（尊重关系方向性）；
        edges = 节点集内部的所有边（对照 mcp-memory-service：子图=可达节点+其间边）。
        max_hops=1 等价旧语义（起点+直接邻居，含对称反向边）。

        注意：find_connected 与本方法都持 self._lock（threading.Lock 不可重入），
        必须先在锁外取可达集，再持锁查边。
        """
        memory_hash = normalize_entity_id(memory_hash)
        if max_hops < 1:
            max_hops = 1
        reached = {memory_hash}
        reached |= {h for h, _ in self.find_connected(memory_hash, max_hops=max_hops)}

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT source_hash, target_hash, similarity, relationship_type
                       FROM memory_graph""",
                ).fetchall()
                edges = []
                for r in rows:
                    if r["source_hash"] in reached and r["target_hash"] in reached:
                        edges.append({
                            "source": r["source_hash"],
                            "target": r["target_hash"],
                            "similarity": r["similarity"],
                            "type": r["relationship_type"],
                        })
                return {"nodes": sorted(reached), "edges": edges}
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                return conn.execute("SELECT COUNT(*) AS c FROM memory_graph").fetchone()["c"]
            finally:
                conn.close()

    def close(self) -> None:
        pass
