"""alias_resolver.py — 三级回退别名解析（SPEC-09 K-01）。

授粉自 zettelforge alias_resolver.py（MIT，只读参考独立重写）：
- 规范化：lower + strip + 连字符转空格（上游同款）
- 多级回退；未命中返回规范化形式并记 log（上游 return entity.lower() 语义）
- 与上游差异：上游第一优先是 TypeDB alias-of（重依赖），本版按工单改为
  ① hardcoded → ② entity_aliases.json → ③ 图回退（自家 SQLite intel_edge
  的 rel='alias_of' 边，不依赖 TypeDB）；图回退命中后写 intel_alias 缓存
  （source='graph'），下次同查询免图遍历。
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path

from mcpserver.sentinel_intel.schema import entity_id, normalize_value

logger = logging.getLogger(__name__)

# ① 硬编码内置表（照 zettelforge 样例：fancy bear→apt28 这类业界通用别名）
HARDCODED_ALIASES: dict[str, dict[str, str]] = {
    "actor": {
        "fancy bear": "apt28",
        "pawn storm": "apt28",
        "cozy bear": "apt29",
        "the duk": "apt37",
    },
    "tool": {
        "x-agent": "xagent",
    },
    "infra": {},
    "indicator": {},
}

_DEFAULT_ALIAS_FILE = Path(__file__).resolve().parent / "entity_aliases.json"


def _fold_ws(text: str) -> str:
    """匹配键忽略空白：「雪 风」与「雪风」视同一名（排版变体）。

    只作用于匹配键；未命中返回的规范化原文仍保留空格形态。
    """
    return re.sub(r"\s+", "", text)


# 硬编码表的空白折叠匹配视图（键 = fold(normalize_value(key))）
_HARDCODED_MATCH: dict[str, dict[str, str]] = {
    etype: {_fold_ws(normalize_value(k)): v for k, v in mapping.items()}
    for etype, mapping in HARDCODED_ALIASES.items()
}


class AliasResolver:
    """三级回退别名解析器：resolve(etype, alias) → canonical value。

    ① 硬编码内置表（HARDCODED_ALIASES）
    ② entity_aliases.json 外部扩展（文件存在则读入合并，etype→{alias: canonical}）
    ③ 图回退：intel_edge 中 rel='alias_of' 的边（alias 实体 → 画像主实体）
    未命中：返回规范化 alias（lower+连字符转空格）并记 log。
    """

    def __init__(self, conn: sqlite3.Connection,
                 alias_file: str | Path | None = None) -> None:
        self.conn = conn
        self.alias_file = Path(alias_file) if alias_file else _DEFAULT_ALIAS_FILE

    # ---- ② JSON 外部扩展 ----
    def _json_aliases(self) -> dict[str, dict[str, str]]:
        if not self.alias_file.is_file():
            return {}
        try:
            data = json.loads(self.alias_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[sentinel_intel] entity_aliases.json 读取失败(%s): %s",
                           self.alias_file, e)
            return {}
        if not isinstance(data, dict):
            logger.warning("[sentinel_intel] entity_aliases.json 结构非 dict，忽略")
            return {}
        out: dict[str, dict[str, str]] = {}
        for etype, mapping in data.items():
            if isinstance(mapping, dict):
                # 键规范化+空白折叠用于匹配；目标值保持原貌（不破坏连字符等真实形态）
                out[str(etype)] = {_fold_ws(normalize_value(k)): str(v).strip()
                                   for k, v in mapping.items()}
        return out

    # ---- ③ 图回退：自家 SQLite alias_of 边 ----
    def _graph_resolve(self, etype: str, alias_norm: str) -> str | None:
        """查 intel_edge 中 rel='alias_of' 的边：alias 实体 → 画像主实体。

        链式 alias（A alias_of B，B alias_of C）沿边追到底（BFS 防环）。
        """
        try:
            # 按稳定 id 定位实体（存储展示值不含连字符转空格，不能用 value 匹配）
            row = self.conn.execute(
                "SELECT id FROM intel_entity WHERE id=? LIMIT 1",
                (entity_id(etype, alias_norm),)).fetchone()
        except sqlite3.Error as e:
            logger.warning("[sentinel_intel] 图回退查询失败: %s", e)
            return None
        if not row:
            return None
        node_id: str = row["id"]
        seen: set[str] = {node_id}
        while True:
            edge = self.conn.execute(
                "SELECT dst_id FROM intel_edge "
                "WHERE src_id=? AND rel='alias_of' LIMIT 1",
                (node_id,)).fetchone()
            if not edge or edge["dst_id"] in seen:
                break
            node_id = edge["dst_id"]
            seen.add(node_id)
        target = self.conn.execute(
            "SELECT value, canonical_id FROM intel_entity WHERE id=? LIMIT 1",
            (node_id,)).fetchone()
        if not target:
            return None
        # 命中后写 intel_alias 缓存（source='graph'），下次免图遍历
        self.conn.execute(
            "INSERT OR IGNORE INTO intel_alias(alias, etype, canonical_id, source) "
            "VALUES (?,?,?,'graph')",
            (alias_norm, etype, target["canonical_id"]))
        self.conn.commit()
        return target["value"]

    # ---- 对外入口 ----
    def resolve(self, etype: str, alias: str) -> str:
        """三级回退解析，返回 canonical value；未命中返回规范化 alias。"""
        alias_norm = normalize_value(alias)
        if not alias_norm:
            logger.info("[sentinel_intel] alias 为空，原样返回")
            return alias_norm

        # ① 硬编码（空白折叠匹配）
        hit = _HARDCODED_MATCH.get(etype, {}).get(_fold_ws(alias_norm))
        if hit:
            logger.debug("[sentinel_intel] alias '%s/%s' → %s (hardcoded)",
                         etype, alias_norm, hit)
            return hit

        # ② JSON 扩展（空白折叠匹配）
        hit = self._json_aliases().get(etype, {}).get(_fold_ws(alias_norm))
        if hit:
            logger.debug("[sentinel_intel] alias '%s/%s' → %s (json)",
                         etype, alias_norm, hit)
            return hit

        # ③ 图回退（intel_edge rel='alias_of'）
        hit = self._graph_resolve(etype, alias_norm)
        if hit:
            logger.debug("[sentinel_intel] alias '%s/%s' → %s (graph)",
                         etype, alias_norm, hit)
            return hit

        logger.info("[sentinel_intel] alias 未命中三级回退: %s/%s → 原样返回",
                    etype, alias_norm)
        return alias_norm

    def resolve_canonical_id(self, etype: str, alias: str) -> str | None:
        """解析并直接给出 canonical 实体 id（未命中返回 None）。"""
        canonical_value = self.resolve(etype, alias)
        row = self.conn.execute(
            "SELECT id FROM intel_entity WHERE id=? LIMIT 1",
            (entity_id(etype, canonical_value),)).fetchone()
        return row["id"] if row else None
