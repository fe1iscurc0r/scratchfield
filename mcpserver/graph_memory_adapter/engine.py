"""轻量 KG 记忆引擎（卷139）——三表 + recursive CTE，零外部依赖。

设计来源：Glitch-Cat-Club/graph-memory-starter（MIT · 227★）
只借鉴设计，不复制代码。上游是「批量建图 + 只读检索」，本仓扩展了
「对话中增量写入」的 remember() 路径（Lumo 的记忆是边聊边长的）。

核心不变量（与上游一致）：
  1. 实体 ID 确定性：uuid5(NAMESPACE_OID, "{type}:{normalised_name}")
     → 同名实体跨文档/跨轮次自动归一，无需 ML 消歧
  2. 检索用一条 recursive CTE 走多跳（纯 SQLite，无模型调用，快且确定）
  3. 边携带 source_doc，回答可回溯来源
  4. 条件类信息（金额/日期/时间窗）挂在实体 description 上，不挂在边上
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------- 路径策略

def default_db_path() -> Path:
    """默认库位置：<repo>/knowledge-base/graph_memory/graph_memory.db。

    与既有 knowledge-base/（academic/infra/knowledge/mcp）同级同策略：
    知识类数据统一落在该目录树下。`LUMO_GRAPH_MEMORY_DB` 可覆盖（测试用）。
    """
    env = os.environ.get("LUMO_GRAPH_MEMORY_DB")
    if env:
        return Path(env)
    repo = Path(__file__).resolve().parents[2]
    return repo / "knowledge-base" / "graph_memory" / "graph_memory.db"


# ---------------------------------------------------------------- 标识与归一

def normalise(name: str) -> str:
    """名称归一：小写、去空白、空白转下划线（上游同款）。"""
    return re.sub(r"\s+", "_", str(name or "").strip().lower())


def entity_id(type_: str, name: str) -> str:
    """确定性实体 ID：同 type + 同归一名的实体永远是同一个节点。"""
    key = f"{(type_ or '').strip() or 'THING'}:{normalise(name)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, key))


# ---------------------------------------------------------------- 检索结果

@dataclass
class Facts:
    """一次检索的产出（与上游 recall.Facts 同构）。"""

    triples: list[tuple[str, str, str, str]] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)
    ms: float = 0.0
    hops: int = 0

    def as_text(self) -> str:
        """人类/LLM 可读的注入文本（上游同款排版，中文标注）。"""
        header = f"记忆：{len(self.triples)} 条事实（{self.ms:.0f} ms，{self.hops} 跳内）"
        if not self.triples:
            return header + "\n（本次提问在图谱里没有匹配）"
        width = max(len(f"{s} --[{p}]--> {t}") for s, p, t, _ in self.triples)
        lines = [
            f"{f'{s} --[{p}]--> {t}':<{width}}   ({doc})" for s, p, t, doc in self.triples
        ]
        text = header + "\n\n" + "\n".join(lines)
        if self.notes:
            # 条件挂在实体上而非边上——必须一并带出，否则事实不完整
            text += "\n\n其中：\n" + "\n".join(f"  {n}: {d}" for n, d in self.notes)
        return text

    def to_dict(self) -> dict:
        return {
            "triples": [
                {"source": s, "predicate": p, "target": t, "source_doc": doc}
                for s, p, t, doc in self.triples
            ],
            "notes": [{"name": n, "description": d} for n, d in self.notes],
            "ms": round(self.ms, 2),
            "hops": self.hops,
        }


# ---------------------------------------------------------------- 引擎

# 多跳走图：seed 命中实体 → 沿 relations 双向扩展 depth 跳 → 收集两端都在
# 走图集合内的边，按"离 seed 最近"排序。这是上游那条 recursive CTE 的骨架。
_WALK_SQL = """
WITH RECURSIVE walk(entity_id, depth) AS (
  SELECT id, 0 FROM entities WHERE id IN ({seeds})
  UNION
  SELECT CASE WHEN r.source_id = w.entity_id
              THEN r.target_id ELSE r.source_id END,
         w.depth + 1
  FROM relations r JOIN walk w
    ON w.entity_id IN (r.source_id, r.target_id)
  WHERE w.depth < ?
)
SELECT e1.name, r.predicate, e2.name, r.source_doc,
       MIN((SELECT MIN(depth) FROM walk WHERE entity_id = r.source_id),
           (SELECT MIN(depth) FROM walk WHERE entity_id = r.target_id)) AS near
FROM relations r
JOIN entities e1 ON e1.id = r.source_id
JOIN entities e2 ON e2.id = r.target_id
WHERE r.source_id IN (SELECT entity_id FROM walk)
  AND r.target_id IN (SELECT entity_id FROM walk)
ORDER BY near
"""


class GraphMemory:
    """轻量 KG 记忆：写入（remember）+ 检索（recall）+ 注入格式化（hook_prompt）。"""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.executescript(
            (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------ 写入

    def remember(self, entity: str, relation: str, target: str,
                 entity_type: str = "", target_type: str = "",
                 description: str = "", target_description: str = "",
                 source_doc: str = "", aliases: Iterable[str] | None = None,
                 origin: str = "dialogue") -> dict:
        """记一条 (entity --[relation]--> target) 三元组（幂等：重复写不产生重复行）。

        条件类信息（金额/日期/时间窗）应写进 description —— 与上游约定一致。
        """
        if not (entity and relation and target):
            return {"ok": False, "error": "empty_operand",
                    "detail": "entity / relation / target 三者都不能为空"}

        src_id = entity_id(entity_type, entity)
        dst_id = entity_id(target_type, target)
        now = time.time()
        cur = self._conn.cursor()

        for eid, name, type_, desc in (
            (src_id, entity, entity_type, description),
            (dst_id, target, target_type, target_description),
        ):
            cur.execute(
                "INSERT OR IGNORE INTO entities(id,name,type,description,source_doc) "
                "VALUES (?,?,?,?,?)", (eid, name, type_, desc, source_doc))
            # 已存在且本次带描述而旧描述为空 → 补上（条件信息不丢）
            if desc:
                cur.execute(
                    "UPDATE entities SET description=? WHERE id=? AND description=''",
                    (desc, eid))
            cur.execute(
                "INSERT INTO memory_meta(entity_id, created_at, origin) VALUES (?,?,?)",
                (eid, now, origin))

        cur.execute(
            "SELECT 1 FROM relations WHERE source_id=? AND target_id=? AND predicate=? LIMIT 1",
            (src_id, dst_id, relation))
        created = cur.fetchone() is None
        if created:
            cur.execute(
                "INSERT INTO relations(source_id,target_id,predicate,source_doc) "
                "VALUES (?,?,?,?)", (src_id, dst_id, relation, source_doc))

        for alias in (aliases or []):
            if str(alias).strip():
                cur.execute("INSERT INTO aliases(entity_id, alias) VALUES (?,?)",
                            (src_id, str(alias).strip()))

        self._conn.commit()
        return {"ok": True, "created": created,
                "source_id": src_id, "target_id": dst_id, "predicate": relation}

    def ingest_entities(self, nodes: list[dict], edges: list[dict],
                        aliases: list[dict] | None = None,
                        source_doc: str = "") -> dict:
        """批量写入（卷142 抽取管线的落地接口）。

        nodes:  [{"name","type","description"}]
        edges:  [{"source","predicate","target"}]
        aliases:[{"entity","alias"}]
        """
        types: dict[str, str] = {}
        for n in nodes or []:
            if n.get("name"):
                types[n["name"]] = n.get("type", "")
        written = 0
        for n in nodes or []:
            if not n.get("name"):
                continue
            self.remember(
                n["name"], "__self__", n["name"],
                entity_type=n.get("type", ""), target_type=n.get("type", ""),
                description=n.get("description", ""), source_doc=source_doc,
                origin="extract")
            written += 1
        # 自指边只用于建实体，不留在关系表里
        self._conn.execute("DELETE FROM relations WHERE predicate='__self__'")
        for e in edges or []:
            if not (e.get("source") and e.get("predicate") and e.get("target")):
                continue
            self.remember(e["source"], e["predicate"], e["target"],
                          entity_type=types.get(e["source"], ""),
                          target_type=types.get(e["target"], ""),
                          source_doc=source_doc, origin="extract")
            written += 1
        for a in aliases or []:
            if a.get("entity") and a.get("alias"):
                self.add_alias(a["entity"], a["alias"])
        self._conn.commit()
        return {"ok": True, "written": written}

    def add_alias(self, entity_name: str, alias: str) -> dict:
        """给实体补别名（检索时的 seed 命中面）。"""
        row = self._conn.execute(
            "SELECT id FROM entities WHERE name=? LIMIT 1", (entity_name,)).fetchone()
        if row is None:
            return {"ok": False, "error": "entity_not_found", "name": entity_name}
        self._conn.execute("INSERT INTO aliases(entity_id, alias) VALUES (?,?)",
                           (row["id"], alias))
        self._conn.commit()
        return {"ok": True, "entity_id": row["id"], "alias": alias}

    # ------------------------------------------------ 检索

    def _seeds(self, question: str) -> list[str]:
        """命中实体：名字或别名出现在提问里（上游做法：词边界匹配）。"""
        q = (question or "").lower()
        if not q.strip():
            return []
        found: dict[str, bool] = {}
        rows = list(self._conn.execute("SELECT id, name FROM entities"))
        rows += list(self._conn.execute("SELECT entity_id AS id, alias AS name FROM aliases"))
        for eid, text in rows:
            t = str(text or "").strip().lower()
            if not t:
                continue
            # 中文没有 \b 词边界，退化为子串包含；拉丁文走词边界
            hit = (re.search(rf"\b{re.escape(t)}\b", q) if t.isascii()
                   else (t in q))
            if hit:
                found[eid] = True
        return list(found)

    def recall(self, query: str, hops: int = 3, top_k: int = 8) -> Facts:
        """从提问出发走 hops 跳，返回相关三元组（纯 SQLite，无模型调用）。"""
        t0 = time.perf_counter()
        seeds = self._seeds(query)
        if not seeds:
            return Facts([], [], (time.perf_counter() - t0) * 1000, hops)
        marks = ",".join("?" * len(seeds))
        rows = self._conn.execute(
            _WALK_SQL.format(seeds=marks), (*seeds, int(hops))).fetchall()
        triples = [(r[0], r[1], r[2], r[3]) for r in rows[: max(1, int(top_k))]]
        names = {n for s, _, t, _ in triples for n in (s, t)}
        notes: list[tuple[str, str]] = []
        if names:
            marks = ",".join("?" * len(names))
            notes = [
                (r["name"], r["description"])
                for r in self._conn.execute(
                    f"SELECT name, description FROM entities "  # noqa: S608
                    f"WHERE name IN ({marks}) AND description != '' ORDER BY name",
                    tuple(names))
            ]
        return Facts(triples, notes, (time.perf_counter() - t0) * 1000, hops)

    def hook_prompt(self, context: str, hops: int = 3, top_k: int = 8,
                    max_chars: int = 2000) -> str:
        """把检索结果格式化成可直接注入的上下文（失败一律退化为空串，不抛错）。

        与上游 recall_hook.py 的 additionalContext 同义；此处返回文本，
        由调用方决定挂到哪（MCP 工具返回值 / 对话附加上下文）。
        """
        try:
            facts = self.recall(context, hops=hops, top_k=top_k)
            if not facts.triples:
                return ""
            text = facts.as_text()
            return text[:max_chars]
        except Exception:
            return ""  # 注入是旁路：任何异常都不该影响主对话

    # ------------------------------------------------ 运维/观测

    def stats(self) -> dict:
        q = lambda sql: self._conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "db_path": str(self.db_path),
            "entities": q("SELECT COUNT(*) FROM entities"),
            "relations": q("SELECT COUNT(*) FROM relations"),
            "aliases": q("SELECT COUNT(*) FROM aliases"),
        }

    def export_subgraph(self, query: str, hops: int = 3, top_k: int = 8) -> dict:
        """导出子图（前端可视化用：nodes + links）。"""
        facts = self.recall(query, hops=hops, top_k=top_k)
        names = {n for s, _, t, _ in facts.triples for n in (s, t)}
        nodes = [
            {"name": r["name"], "type": r["type"], "description": r["description"]}
            for r in self._conn.execute(
                "SELECT name, type, description FROM entities ORDER BY name")
            if r["name"] in names
        ]
        return {"nodes": nodes,
                "links": [{"source": s, "predicate": p, "target": t, "source_doc": d}
                          for s, p, t, d in facts.triples]}

    def clear(self) -> None:
        """清空图谱（测试/重置用）。"""
        for t in ("relations", "aliases", "memory_meta", "entities"):
            self._conn.execute(f"DELETE FROM {t}")  # noqa: S608
        self._conn.commit()


# ---------------------------------------------------------------- 单例（按路径缓存）

_memories: dict[str, GraphMemory] = {}


def get_graph_memory(db_path: str | Path | None = None) -> GraphMemory:
    """取（或建）某路径对应的记忆实例。

    注意：按**解析后的绝对路径**缓存——不同路径得到不同实例，
    同一路径反复调用复用同一实例（避免误串库）。
    """
    target = Path(db_path) if db_path else default_db_path()
    key = str(target.resolve() if target.exists() else target.absolute())
    if key not in _memories:
        _memories[key] = GraphMemory(target)
    return _memories[key]


def reset_graph_memory(db_path: str | Path | None = None) -> None:
    """关闭并清除缓存（测试收尾 / 换库用）。不传路径则全部清理。"""
    global _memories
    if db_path is None:
        for m in _memories.values():
            try:
                m.close()
            except Exception:
                pass
        _memories = {}
        return
    target = Path(db_path)
    key = str(target.resolve() if target.exists() else target.absolute())
    m = _memories.pop(key, None)
    if m is not None:
        try:
            m.close()
        except Exception:
            pass
