"""memory contradiction — 矛盾检测 + supersedes 取代链（F-03）。

机制：同实体同属性不同值 → 矛盾。新事实登记时对每个被取代的旧事实写
MemoryGraph 有向边 new --supersedes--> old（supersedes 已加入
ASYMMETRIC_RELATIONSHIPS，find_connected 只沿出边遍历 → 天然形成
「新 → 旧」的取代链，BFS 可查全链）。

设计：
  - facts_index 轻索引表（SQLite，CREATE IF NOT EXISTS 幂等，兼容现有库）
  - register_fact 幂等（INSERT OR REPLACE）；同值重复登记不误报
  - 检测只比对 (entity, attribute) 相同且 value 不同的条目（自身排除）
  - supersedes 边 metadata 记 {entity, attribute}，可追溯矛盾来源
  - 纯旁路：不触碰 FactStore / 桌宠壳

License: Apache-2.0。
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_graph import MemoryGraph

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts_index (
    fact_id    TEXT NOT NULL PRIMARY KEY,
    entity     TEXT NOT NULL,
    attribute  TEXT NOT NULL,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE (entity, attribute, value)
);
CREATE INDEX IF NOT EXISTS idx_facts_ea ON facts_index(entity, attribute);
"""

# 取代链 BFS 跳数上限（链深超此值视为异常环，防御性截断）
_MAX_CHAIN_HOPS = 32


class ContradictionDetector:
    """矛盾检测器：facts_index 轻索引 + MemoryGraph supersedes 链。"""

    def __init__(self, db_path: str | Path, graph: MemoryGraph):
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self._db_path, check_same_thread=False)
        self.db.executescript(_SCHEMA)  # 幂等迁移：老库/新库统一建表
        self.db.commit()
        self.graph = graph
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 登记 + 检测
    def register_fact(
        self,
        fact_id: str,
        entity: str,
        attribute: str,
        value: str,
        created_at: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """登记事实并检测矛盾。

        返回本次登记取代的旧事实列表（空 = 无矛盾）：
          [{entity, attribute, old_fact_id, old_value, new_fact_id, new_value}]
        同 (entity, attribute, value) 既有登记（含同 fact_id 重复）不构成矛盾。
        幂等：重复登记同事实 → 索引 REPLACE，supersedes 边 INSERT OR REPLACE。
        """
        import time as _time
        fact_id = str(fact_id).strip()
        entity = str(entity).strip()
        attribute = str(attribute).strip()
        value = str(value).strip()
        if not (fact_id and entity and attribute and value):
            raise ValueError("fact_id/entity/attribute/value 均不可为空")
        now = created_at if created_at is not None else _time.time()

        with self._lock:
            # 幂等登记（UNIQUE(e,a,v) 冲突时 REPLACE：同值旧 fact_id 被顶替）
            self.db.execute(
                "INSERT OR REPLACE INTO facts_index"
                " (fact_id, entity, attribute, value, created_at) VALUES (?,?,?,?,?)",
                (fact_id, entity, attribute, value, now),
            )
            self.db.commit()
            # 矛盾检测：同 (e,a) 不同 value 的既有事实（排除自身）
            rows = self.db.execute(
                "SELECT fact_id, value, created_at FROM facts_index"
                " WHERE entity=? AND attribute=? AND value<>? AND fact_id<>?",
                (entity, attribute, value, fact_id),
            ).fetchall()

        contradictions: List[Dict[str, Any]] = []
        for old_id, old_value, old_ts in rows:
            # 新值取代旧值：有向边 new --supersedes--> old（幂等 REPLACE）
            ok = self.graph.store_association(
                fact_id, old_id,
                similarity=0.0,  # 取代边无相似度语义，固定 0
                relationship_type="supersedes",
                metadata={"entity": entity, "attribute": attribute},
            )
            if not ok:
                logger.warning(
                    "[contradiction] supersedes 边写入失败 %s→%s (%s.%s)",
                    fact_id, old_id, entity, attribute,
                )
                continue
            contradictions.append({
                "entity": entity,
                "attribute": attribute,
                "old_fact_id": old_id,
                "old_value": old_value,
                "old_created_at": old_ts,
                "new_fact_id": fact_id,
                "new_value": value,
            })
        if contradictions:
            logger.info(
                "[contradiction] %s.%s 检出 %d 条被取代旧值（新值=%r）",
                entity, attribute, len(contradictions), value,
            )
        return contradictions

    # ------------------------------------------------------------ 查询
    def find_contradictions(self, entity: str, attribute: str) -> List[Dict[str, Any]]:
        """查询某 (entity, attribute) 下的多值事实组（value 去重后 >1 才算）。"""
        with self._lock:
            rows = self.db.execute(
                "SELECT fact_id, value, created_at FROM facts_index"
                " WHERE entity=? AND attribute=? ORDER BY created_at",
                (str(entity).strip(), str(attribute).strip()),
            ).fetchall()
        values = {r[1] for r in rows}
        if len(values) <= 1:
            return []
        return [
            {"fact_id": r[0], "value": r[1], "created_at": r[2]}
            for r in rows
        ]

    def get_supersede_chain(self, fact_id: str) -> List[str]:
        """沿 supersedes 出边遍历：fact_id 直接/间接取代的全部旧事实 id。

        方向语义：supersedes 非对称 → find_connected 只沿出边（新→旧），
        旧事实不会反向出现。返回按跳数升序（直接取代的在前）。
        """
        reached = self.graph.find_connected(
            fact_id, max_hops=_MAX_CHAIN_HOPS, relationship_type="supersedes",
        )
        return [h for h, _dist in reached]

    def count(self) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM facts_index").fetchone()[0]

    def close(self) -> None:
        self.db.close()


__all__ = ["ContradictionDetector"]
