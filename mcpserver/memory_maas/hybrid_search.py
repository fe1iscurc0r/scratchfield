# -*- coding: utf-8 -*-
"""
记忆混合检索融合 — W66-05

三路并行检索 → 加权 RRF 融合排序：
  语义路（向量余弦）+ BM25/FTS5 路（关键词）+ 实体路（结构化标签/字段匹配）

设计原则：
- 不破坏现有独立路径；各路独立可调用。
- 融合失败（任何一路炸）自动降级到单路，不抛错。
- mock 数据验证（不依赖 NEKO 真实向量服务）。
"""
from __future__ import annotations

import math
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 索引结构常量
# 与 mcpserver/memory_maas/entities.py 的 TypedMemoryStore 共用 schema：
#   memory_entities(id, type, content, tags, pinned, source_rank, ...)
# 记忆实体有 id/content/tags/type 等字段，天然支持实体路匹配。

DEFAULT_RRF_K = 60  # 与 NEKO rrf.py 保持一致


# ---------------------------------------------------------------- fp16 编解码（与 NEKO rrf.py 同构）

def encode_fp16(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}e", *vec)


def decode_fp16(blob: bytes) -> list[float]:
    n = len(blob) // 2
    return list(struct.unpack(f"<{n}e", blob))


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


# ---------------------------------------------------------------- 数据结构

@dataclass
class SearchRecord:
    """单条记忆记录（内存态）。"""
    id: str
    content: str
    type: str = "note"
    tags: list[str] = field(default_factory=list)
    source_rank: int = 0
    vector: list[float] | None = None  # 可选；无向量时语义路跳过该条
    meta: dict = field(default_factory=dict)


@dataclass
class RouteResult:
    """单路检索结果。"""
    route: str           # "semantic" | "bm25" | "entity"
    ids: list[str]       # 按排名排序的 id 列表
    scores: dict[str, float]  # id → 原始分数（用于加权）
    hit_count: int


@dataclass
class FusionResult:
    """融合后的最终结果。"""
    ids: list[str]                   # 融合后按 RRF 排序
    scores: dict[str, float]         # RRF 累加分数
    fusion_method: str               # "rrf_weighted" | "single_route"
    routes_used: list[str]           # 本次实际使用的路
    degraded: bool                   # 是否降级到单路


# ---------------------------------------------------------------- BM25 实现（Okapi BM25，标准参数 k1=1.5, b=0.75）

_BM25_K1 = 1.5
_BM25_B = 0.75


def _tokenize_cjk(text: str) -> list[str]:
    """简体中文字符 2-gram + 3-gram（不依赖 jieba）。
    
    策略：逐段处理——纯 CJK 段生成 n-gram；非 CJK 段按空白分词（strip）。
    只保留≥2字符的 token。
    """
    import re
    text = text.strip()
    if not text:
        return []
    tokens: list[str] = []
    cjk_re = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    non_cjk_re = re.compile(r"[^\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")
    for seg in non_cjk_re.split(text):
        seg = seg.strip()
        if not seg:
            continue
        # 纯 CJK 段 → n-gram
        if cjk_re.match(seg[0]):
            for n in (2, 3):
                for i in range(len(seg) - n + 1):
                    tokens.append(seg[i:i + n])
        else:
            # 非 CJK 段（Latin/数字/标点）→ 直接分词
            for w in seg.split():
                if len(w) >= 2:
                    tokens.append(w)
    return tokens


def _bm25_score(query_terms: list[str], doc_terms: list[str],
                avgdl: float, n_docs: int,
                df: dict[str, int]) -> float:
    """单文档 BM25 得分。"""
    doc_len = len(doc_terms)
    norm = 1.0 - _BM25_B + _BM25_B * doc_len / avgdl
    score = 0.0
    seen = set()
    for term in query_terms:
        if term in seen:
            continue
        seen.add(term)
        n = df.get(term, 0)
        if n == 0:
            continue
        tf = doc_terms.count(term)
        if tf == 0:
            continue
        idf = math.log((n_docs - n + 0.5) / (n + 0.5) + 1.0)
        score += idf * (tf * (_BM25_K1 + 1)) / (tf + _BM25_K1 * norm)
    return score


def bm25_route(query: str, pool: list[SearchRecord], limit: int = 10) -> RouteResult:
    """BM25 关键词检索路。"""
    if not query or not pool:
        return RouteResult(route="bm25", ids=[], scores={}, hit_count=0)

    q_terms = _tokenize_cjk(query)
    if not q_terms:
        return RouteResult(route="bm25", ids=[], scores={}, hit_count=0)

    n_docs = len(pool)
    doc_terms_list: list[list[str]] = [_tokenize_cjk(r.content) for r in pool]
    total_len = sum(len(t) for t in doc_terms_list)
    avgdl = total_len / n_docs if n_docs else 1.0

    # DF（仅 query terms）
    q_unique = set(q_terms)
    df = {t: sum(1 for terms in doc_terms_list for _ in [1] if t in terms)
          for t in q_unique}

    scored: list[tuple[str, float]] = []
    for rec, terms in zip(pool, doc_terms_list):
        s = _bm25_score(q_terms, terms, avgdl, n_docs, df)
        if s > 0:
            scored.append((rec.id, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    ids = [i for i, _ in scored[:limit]]
    scores = {i: s for i, s in scored[:limit]}
    return RouteResult(route="bm25", ids=ids, scores=scores, hit_count=len(ids))


def semantic_route(query_vec: list[float],
                    pool: list[SearchRecord],
                    limit: int = 10) -> RouteResult:
    """向量语义检索路（余弦相似度）。"""
    if not query_vec or not pool:
        return RouteResult(route="semantic", ids=[], scores={}, hit_count=0)

    scored: list[tuple[str, float]] = []
    for rec in pool:
        if rec.vector is None:
            continue
        s = cosine(query_vec, rec.vector)
        if s > 0:
            scored.append((rec.id, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    ids = [i for i, _ in scored[:limit]]
    scores = {i: s for i, s in scored[:limit]}
    return RouteResult(route="semantic", ids=ids, scores=scores, hit_count=len(ids))


def entity_route(query: str,
                  pool: list[SearchRecord],
                  limit: int = 10) -> RouteResult:
    """实体字段匹配路（type 匹配 + tags 包含 + content 关键词）。"""
    if not query or not pool:
        return RouteResult(route="entity", ids=[], scores={}, hit_count=0)

    q_lower = query.lower()
    scored: list[tuple[str, float]] = []

    for rec in pool:
        score = 0.0
        # type 精确匹配权重 2.0
        if rec.type and rec.type in q_lower:
            score += 2.0
        # tag 命中权重 1.5
        for tag in rec.tags:
            if tag and tag.lower() in q_lower:
                score += 1.5
                break
        # content 包含关键词权重 1.0
        if rec.content and q_lower in rec.content.lower():
            score += 1.0
        if score > 0:
            scored.append((rec.id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    ids = [i for i, _ in scored[:limit]]
    scores = {i: s for i, s in scored[:limit]}
    return RouteResult(route="entity", ids=ids, scores=scores, hit_count=len(ids))


# ---------------------------------------------------------------- RRF 融合

def rrf_fuse(routes: list[RouteResult],
              k: int = DEFAULT_RRF_K,
              weights: dict[str, float] | None = None) -> FusionResult:
    """多路排名列表 → RRF 融合排名。

    任何一路炸（空 ids）时自动降级到其余路；
    仅剩一路时返回单路结果（degraded=True）。
    """
    weights = weights or {}
    active_routes = [r for r in routes if r.hit_count > 0]

    if not active_routes:
        return FusionResult(
            ids=[], scores={}, fusion_method="none",
            routes_used=[], degraded=True)

    if len(active_routes) == 1:
        r = active_routes[0]
        return FusionResult(
            ids=r.ids[:],
            scores=r.scores.copy(),
            fusion_method="single_route",
            routes_used=[r.route],
            degraded=True)

    # 多路加权 RRF
    scores: dict[str, float] = {}
    for route_result in active_routes:
        w = weights.get(route_result.route, 1.0)
        for rank, rid in enumerate(route_result.ids, start=1):
            scores[rid] = scores.get(rid, 0.0) + w / (k + rank)

    sorted_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    return FusionResult(
        ids=sorted_ids,
        scores=scores,
        fusion_method="rrf_weighted",
        routes_used=[r.route for r in active_routes],
        degraded=False)


# ---------------------------------------------------------------- 主混合检索入口

def hybrid_search(query: str,
                  pool: list[SearchRecord],
                  query_vec: list[float] | None = None,
                  limit: int = 10,
                  weights: dict[str, float] | None = None,
                  k: int = DEFAULT_RRF_K) -> FusionResult:
    """三路并行检索 → 加权 RRF 融合。

    参数：
        query:      原始查询文本
        pool:       SearchRecord 列表
        query_vec:  可选；提供时启用语义路
        limit:      返回 top-k 数量
        weights:    各路权重（默认 1.0）
        k:          RRF k 参数

    降级策略：
        - query_vec=None：语义路关闭，只跑 BM25+Entity
        - 任一路失败：其余路继续，降级到单路时 degraded=True
    """
    routes: list[RouteResult] = []

    # BM25 路（必开）
    try:
        routes.append(bm25_route(query, pool, limit=limit * 3))
    except Exception:
        pass

    # 实体路（必开）
    try:
        routes.append(entity_route(query, pool, limit=limit * 3))
    except Exception:
        pass

    # 语义路（可选）
    if query_vec is not None:
        try:
            routes.append(semantic_route(query_vec, pool, limit=limit * 3))
        except Exception:
            pass

    # 融合
    try:
        result = rrf_fuse(routes, k=k, weights=weights)
    except Exception:
        # 降级：取 BM25 结果（最可靠的路）
        bm25_result = next((r for r in routes if r.route == "bm25"), None)
        if bm25_result:
            return FusionResult(
                ids=bm25_result.ids[:limit],
                scores=bm25_result.scores.copy(),
                fusion_method="bm25_fallback",
                routes_used=["bm25"],
                degraded=True)
        return FusionResult(
            ids=[], scores={}, fusion_method="none",
            routes_used=[], degraded=True)

    # 截取 top-k
    return FusionResult(
        ids=result.ids[:limit],
        scores={k: v for k, v in result.scores.items() if k in result.ids[:limit]},
        fusion_method=result.fusion_method,
        routes_used=result.routes_used,
        degraded=result.degraded,
    )


# ---------------------------------------------------------------- SQLite FTS5 索引（与 NEKO HybridSearchIndex 独立，不碰原表）

class HybridSearchSQLite:
    """纯 FTS5 + 向量 BLOB 的内存/磁盘混合检索索引。

    与 NEKO memory/hybrid_search/rrf.py 完全独立（不同表名、不同路径），
    不读写任何 NEKO 既有数据库。
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None
        self._pool: list[SearchRecord] = []  # 内存池（测试用）
        self._use_sqlite = self._db_path is not None
        if self._use_sqlite:
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS mm_fts USING fts5"
            "(id UNINDEXED, content, tokenize='unicode61')"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS mm_vecs (id TEXT PRIMARY KEY, vec BLOB)"
        )
        self._conn.commit()

    def add(self, rec: SearchRecord) -> None:
        if self._use_sqlite and self._conn:
            self._conn.execute(
                "INSERT INTO mm_fts(id, content) VALUES (?, ?)",
                (rec.id, rec.content))
            if rec.vector is not None:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mm_vecs(id, vec) VALUES (?, ?)",
                    (rec.id, encode_fp16(rec.vector)))
            self._conn.commit()
        self._pool.append(rec)

    def search(self, query: str,
               query_vec: list[float] | None = None,
               limit: int = 10,
               weights: dict[str, float] | None = None) -> FusionResult:
        pool = self._pool if self._use_sqlite else self._pool
        return hybrid_search(query, pool, query_vec=query_vec,
                             limit=limit, weights=weights)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def count(self) -> int:
        return len(self._pool)
