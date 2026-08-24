"""graph.py — 情报实体图（SPEC-09 K-01）。

授粉自 zettelforge knowledge_graph.py（MIT，只读参考独立重写）：
- add_node(entity_type, entity_value, properties) → 稳定 id（上游同款签名风格）
- add_edge(src, dst, rel, props, ts)：时序边（上游 add_temporal_edge 语义）
- get_entity_timeline(entity_type, entity_value)：按 intel_edge.ts 过滤排序
- traverse(start_type, start_value, max_depth)：DFS + 环预防（上游 _dfs path 结构）

与 F-03 memory_graph.py（NEKO 记忆域）的关系：只参考接口风格，实现独立
（硬约束：情报是独立域，不复用其实现/表结构）。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timezone
from typing import Any

from mcpserver.sentinel_intel.alias_resolver import AliasResolver
from mcpserver.sentinel_intel.schema import (
    EDGE_RELS,
    ENTITY_TYPES,
    connect,
    edge_id,
    entity_id,
    normalize_value,
    stored_value,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class IntelGraphError(RuntimeError):
    """情报图操作错误（白名单违规/端点缺失），fail-fast 不静默。"""


class IntelGraph:
    """SQLite 情报实体图：实体（四型）+ 时序关系边（四关系）+ 别名归并。"""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn: sqlite3.Connection = connect(db_path)
        self.resolver = AliasResolver(self.conn)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------- 实体
    def add_node(self, etype: str, value: str,
                 props: dict[str, Any] | None = None,
                 ts: str | None = None) -> str:
        """幂等入库一个实体，返回稳定 id。

        同 etype+value 已存在 → 不重复建行，仅刷新 last_seen_at 并合并
        properties（工单用例：同 value 不重复建）。
        新建实体 canonical_id = 自身 id（成为自己的画像主实体）。
        """
        if etype not in ENTITY_TYPES:
            raise IntelGraphError(
                f"etype {etype!r} 不在白名单 {list(ENTITY_TYPES)}")
        if not str(value or "").strip():
            raise IntelGraphError("value 不能为空")
        nid = entity_id(etype, value)
        now = ts or _now_iso()
        existing = self.conn.execute(
            "SELECT id, properties_json FROM intel_entity WHERE id=?",
            (nid,)).fetchone()
        if existing:
            merged = json.loads(existing["properties_json"] or "{}")
            if props:
                merged.update(props)
            self.conn.execute(
                "UPDATE intel_entity SET last_seen_at=?, properties_json=? "
                "WHERE id=?",
                (now, json.dumps(merged, ensure_ascii=False), nid))
            self.conn.commit()
            return nid
        self.conn.execute(
            "INSERT INTO intel_entity(id, etype, value, canonical_id, "
            "properties_json, created_at, last_seen_at) VALUES (?,?,?,?,?,?,?)",
            (nid, etype, stored_value(value), nid,
             json.dumps(props or {}, ensure_ascii=False), now, now))
        self.conn.commit()
        return nid

    def get_node(self, etype: str, value: str) -> dict[str, Any] | None:
        # 按稳定 id 查找（id 由规范化值生成），不依赖存储展示形式
        row = self.conn.execute(
            "SELECT * FROM intel_entity WHERE id=? LIMIT 1",
            (entity_id(etype, value),)).fetchone()
        return self._row2entity(row) if row else None

    # ------------------------------------------------------------- 边
    def add_edge(self, src_id: str, dst_id: str, rel: str,
                 props: dict[str, Any] | None = None,
                 ts: str | None = None) -> str:
        """幂等入库一条时序边，返回稳定 edge id（端点必须已存在，fail-fast）。"""
        if rel not in EDGE_RELS:
            raise IntelGraphError(
                f"rel {rel!r} 不在白名单 {list(EDGE_RELS)}")
        for endpoint in (src_id, dst_id):
            if not self.conn.execute(
                    "SELECT 1 FROM intel_entity WHERE id=?", (endpoint,)).fetchone():
                raise IntelGraphError(f"边端点不存在: {endpoint}")
        ts_value = ts or _now_iso()
        eid = edge_id(src_id, dst_id, rel, ts_value)
        self.conn.execute(
            "INSERT OR IGNORE INTO intel_edge(id, src_id, dst_id, rel, "
            "props_json, ts) VALUES (?,?,?,?,?,?)",
            (eid, src_id, dst_id, rel,
             json.dumps(props or {}, ensure_ascii=False), ts_value))
        self.conn.commit()
        return eid

    def add_alias(self, alias_etype: str, alias_value: str,
                  canonical_etype: str, canonical_value: str,
                  ts: str | None = None) -> str:
        """归并入口：alias 实体 --alias_of--> 画像主实体。

        副作用（归并语义核心）：
        - alias 实体 canonical_id 指向画像主实体
        - intel_alias 登记（source='graph'，供 resolve ③ 直查缓存）
        """
        alias_nid = self.add_node(alias_etype, alias_value, ts=ts)
        canon_nid = self.add_node(canonical_etype, canonical_value, ts=ts)
        self.add_edge(alias_nid, canon_nid, "alias_of", ts=ts)
        self.conn.execute(
            "UPDATE intel_entity SET canonical_id=? WHERE id=?",
            (canon_nid, alias_nid))
        self.conn.execute(
            "INSERT OR IGNORE INTO intel_alias(alias, etype, canonical_id, source) "
            "VALUES (?,?,?,'graph')",
            (normalize_value(alias_value), alias_etype, canon_nid))
        self.conn.commit()
        return canon_nid

    # ------------------------------------------------------------- 遍历
    def get_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        """一跳邻居（出边+入边），附关系/时间/对端实体摘要。"""
        if not self.conn.execute(
                "SELECT 1 FROM intel_entity WHERE id=?", (node_id,)).fetchone():
            raise IntelGraphError(f"节点不存在: {node_id}")
        rows = self.conn.execute(
            "SELECT e.*, "
            "  CASE WHEN e.src_id=? THEN 'out' ELSE 'in' END AS direction, "
            "  CASE WHEN e.src_id=? THEN e.dst_id ELSE e.src_id END AS peer_id "
            "FROM intel_edge e WHERE e.src_id=? OR e.dst_id=? "
            "ORDER BY e.ts",
            (node_id, node_id, node_id, node_id)).fetchall()
        out = []
        for r in rows:
            peer = self.conn.execute(
                "SELECT etype, value, canonical_id FROM intel_entity "
                "WHERE id=?", (r["peer_id"],)).fetchone()
            out.append({
                "direction": r["direction"],
                "rel": r["rel"],
                "ts": r["ts"],
                "peer_id": r["peer_id"],
                "peer_etype": peer["etype"] if peer else None,
                "peer_value": peer["value"] if peer else None,
                "peer_canonical_id": peer["canonical_id"] if peer else None,
            })
        return out

    def traverse(self, start_type: str, start_value: str,
                 max_depth: int = 2) -> list[dict[str, Any]]:
        """从起点实体沿出边 DFS 遍历（≤max_depth 跳），环预防，返回节点+路径。

        照 zettelforge traverse 结构：每项 {node, path}，path 是从起点
        到该节点经过的 (rel, peer_value) 链。只走出边（情报因果方向：
        actor uses infra → infra indicates indicator）；入边归属用
        get_neighbors 反查，避免 depth=1 就把二跳目标卷进来。
        """
        start = self.get_node(start_type, start_value)
        if not start:
            raise IntelGraphError(
                f"起点实体不存在: {start_type}/{normalize_value(start_value)}")
        visited: set[str] = set()
        results: list[dict[str, Any]] = []

        def _dfs(current_id: str, depth: int, path: list[tuple[str, str]]) -> None:
            if current_id in visited:
                return
            visited.add(current_id)
            entity = self.conn.execute(
                "SELECT * FROM intel_entity WHERE id=?", (current_id,)).fetchone()
            results.append({
                "node": self._row2entity(entity),
                "path": [{"rel": rel, "via": via} for rel, via in path],
                "depth": len(path),
            })
            if depth >= max_depth:
                return
            for nb in self.get_neighbors(current_id):
                if nb["direction"] != "out":
                    continue  # 只沿出边扩散；入边不缩短情报链跳数
                peer = self.conn.execute(
                    "SELECT value FROM intel_entity WHERE id=?",
                    (nb["peer_id"],)).fetchone()
                _dfs(nb["peer_id"], depth + 1,
                     path + [(nb["rel"], peer["value"] if peer else nb["peer_id"])])

        _dfs(start["id"], 0, [])
        return results

    # ------------------------------------------------------------- 时间线
    def get_entity_timeline(self, etype: str, value: str,
                            start: str | None = None,
                            end: str | None = None) -> list[dict[str, Any]]:
        """实体活动时间线：以其为端点的边按 ts 升序（可按 [start,end] 过滤）。"""
        entity = self.get_node(etype, value)
        if not entity:
            raise IntelGraphError(
                f"实体不存在: {etype}/{normalize_value(value)}")
        sql = ("SELECT e.*, CASE WHEN e.src_id=? THEN 'out' ELSE 'in' END "
               "AS direction, "
               "CASE WHEN e.src_id=? THEN e.dst_id ELSE e.src_id END AS peer_id "
               "FROM intel_edge e WHERE (e.src_id=? OR e.dst_id=?)")
        params: list[Any] = [entity["id"], entity["id"],
                             entity["id"], entity["id"]]
        if start:
            sql += " AND e.ts >= ?"
            params.append(start)
        if end:
            sql += " AND e.ts <= ?"
            params.append(end)
        sql += " ORDER BY e.ts ASC"
        out = []
        for r in self.conn.execute(sql, params).fetchall():
            peer = self.conn.execute(
                "SELECT etype, value FROM intel_entity WHERE id=?",
                (r["peer_id"],)).fetchone()
            out.append({
                "ts": r["ts"], "rel": r["rel"], "direction": r["direction"],
                "peer_value": peer["value"] if peer else None,
                "peer_etype": peer["etype"] if peer else None,
                "props": json.loads(r["props_json"] or "{}"),
            })
        return out

    # ------------------------------------------------------------- 画像
    def get_profile(self, etype: str, value: str) -> dict[str, Any] | None:
        """画像 = canonical 实体 + 全部归并到同一 canonical_id 的成员 + 成员出边。"""
        entity = self.get_node(etype, value)
        if not entity:
            return None
        canonical_id = entity["canonical_id"]
        members = [self._row2entity(r) for r in self.conn.execute(
            "SELECT * FROM intel_entity WHERE canonical_id=? ORDER BY value",
            (canonical_id,)).fetchall()]
        edges: list[dict[str, Any]] = []
        for m in members:
            for nb in self.get_neighbors(m["id"]):
                if nb["rel"] == "alias_of":
                    continue  # 归并边不进画像出边（画像是结果不是过程）
                edges.append({"member": m["value"], **nb})
        edges.sort(key=lambda e: e["ts"])
        return {
            "canonical_id": canonical_id,
            "canonical_value": next(
                (m["value"] for m in members if m["id"] == canonical_id), None),
            "etype": etype,
            "members": members,
            "edges": edges,
        }

    # ------------------------------------------------------------- 工具
    @staticmethod
    def _row2entity(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "etype": row["etype"], "value": row["value"],
            "canonical_id": row["canonical_id"],
            "properties": json.loads(row["properties_json"] or "{}"),
            "created_at": row["created_at"], "last_seen_at": row["last_seen_at"],
            "weight": row["weight"], "status": row["status"],
            "revoked_at": row["revoked_at"],
        }
