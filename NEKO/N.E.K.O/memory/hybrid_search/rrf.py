"""SPEC-03 Phase1.1 — 混合检索旁路（FTS5 关键词 × 向量余弦，RRF 融合）。

非侵入旁路：自建独立 SQLite（FTS5 + fp16 向量 BLOB），不读不写 NEKO 现有
FactStore / facts_fts_v2 / hybrid_recall.py 的任何路径。现有 hybrid_recall
（BM25+cosine, RRF k=60）保持不动；本模块提供可独立评测/对照的第二实现，
评测数据见 tests/test_spec03_phase1.py。

License: Apache-2.0（RRF 融合为通用技术，参数对齐仓库内 rag/rag_service.py 与
NEKO memory/hybrid_recall.py 的 k=60 惯例）。
"""
from __future__ import annotations

import json
import math
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RRF_K = 60  # 与仓库既有 hybrid_recall / rag_service 的 RRF k 保持一致


# ---------------------------------------------------------------- fp16 编解码
# 与 NEKO memory/_embeddings/schema.py 的 encode_vector_fp16 同构（独立实现，避免依赖）。

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


# ---------------------------------------------------------------- RRF 融合

def rrf_fuse(rank_lists: dict[str, list[str]], k: int = DEFAULT_RRF_K,
             weights: dict[str, float] | None = None) -> list[tuple[str, float]]:
    """多路排名列表 → RRF 融合排名。rank_lists: {路名: [id 按名次]}"""
    weights = weights or {}
    scores: dict[str, float] = {}
    for route, ids in rank_lists.items():
        w = weights.get(route, 1.0)
        for rank, id_ in enumerate(ids, start=1):
            scores[id_] = scores.get(id_, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


# ---------------------------------------------------------------- 旁路索引

@dataclass
class Record:
    id: str
    text: str
    vector: list[float] | None = None
    meta: dict = field(default_factory=dict)


class HybridSearchIndex:
    """独立 SQLite：FTS5(unicode61) + 向量 BLOB。add/search；不做任何后台写。"""

    def __init__(self, db_path: str | Path):
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS hs_fts USING fts5"
            "(id UNINDEXED, content, tokenize='unicode61')"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS hs_vecs (id TEXT PRIMARY KEY, vec BLOB)"
        )
        self.db.commit()

    # ---- 写（仅本模块自有表）
    def add(self, rec: Record) -> None:
        self.db.execute("INSERT INTO hs_fts(id, content) VALUES (?, ?)", (rec.id, rec.text))
        if rec.vector is not None:
            self.db.execute(
                "INSERT OR REPLACE INTO hs_vecs(id, vec) VALUES (?, ?)",
                (rec.id, encode_fp16(rec.vector)),
            )
        self.db.commit()

    def add_many(self, recs: list[Record]) -> None:
        for r in recs:
            self.add(r)

    # ---- 双路检索
    def _keyword_rank(self, query: str, limit: int) -> list[str]:
        toks = [t for t in query.replace("「", " ").replace("」", " ").split() if t]
        if not toks:
            return []
        cond = " OR ".join("content MATCH ?" for _ in toks)
        rows = self.db.execute(
            f"SELECT id FROM hs_fts WHERE {cond} ORDER BY bm25(hs_fts) LIMIT ?",
            [*toks, limit],
        ).fetchall()
        return [r[0] for r in rows]

    def _vector_rank(self, query_vec: list[float], limit: int) -> list[str]:
        rows = self.db.execute("SELECT id, vec FROM hs_vecs").fetchall()
        scored = [(cosine(query_vec, decode_fp16(blob)), rid) for rid, blob in rows if blob]
        scored.sort(reverse=True)
        return [rid for _, rid in scored[:limit]]

    def search(self, query: str, query_vec: list[float] | None = None,
               limit: int = 10, k: int = DEFAULT_RRF_K) -> list[tuple[str, float]]:
        """关键词路必开；query_vec 提供时叠加向量路 → RRF。"""
        routes: dict[str, list[str]] = {"kw": self._keyword_rank(query, limit * 3)}
        if query_vec is not None:
            routes["vec"] = self._vector_rank(query_vec, limit * 3)
        return rrf_fuse(routes, k=k)[:limit]

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM hs_fts").fetchone()[0]

    def close(self) -> None:
        self.db.close()


# ---------------------------------------------------------------- 评测 harness

def evaluate_recall(index: HybridSearchIndex, queries: list[dict],
                    limit: int = 5, with_vector: bool = True) -> dict:
    """queries: [{q, qvec, expected_ids}]。返回 keyword-only vs hybrid 的 recall@limit。

    用于 SPEC-03 验收 1（20 次随机查询，对照基线 = 关键词单路；mem0 无仓内可复现
    基线，参考 MemClaw LoCoMo 77.6% LLM-judge 口径，见 docs/SPEC-03-report.md）。
    """
    kw_hits = hyb_hits = 0
    per_query = []
    for item in queries:
        exp = set(item["expected_ids"])
        kw = [rid for rid, _ in index.search(item["q"], None, limit=limit)]
        hyb = [rid for rid, _ in index.search(item["q"], item.get("qvec") if with_vector else None, limit=limit)]
        kw_r = len(exp & set(kw)) / len(exp) if exp else 0.0
        hyb_r = len(exp & set(hyb)) / len(exp) if exp else 0.0
        kw_hits += kw_r
        hyb_hits += hyb_r
        per_query.append({"q": item["q"], "kw": round(kw_r, 3), "hybrid": round(hyb_r, 3)})
    n = len(queries) or 1
    return {
        "n": len(queries),
        "limit": limit,
        "keyword_recall": round(kw_hits / n, 4),
        "hybrid_recall": round(hyb_hits / n, 4),
        "hybrid_ge_keyword": hyb_hits >= kw_hits,
        "per_query": per_query,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
