"""SPEC-03 Phase1.2 — AAAK 压缩索引卡（旁路）。

会话主题 → 压缩卡片 → 定位 chunk。独立 SQLite 表 index_cards，不触碰
NEKO 现有 FactStore / time_indexed.db 写入路径。摘要器为启发式抽取
（无 LLM 依赖，离线可测）；接 LLM 时替换 summarizer 回调即可。
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

STOPWORDS = set("的 了 是 我 你 他 她 它 我们 你们 在 和 与 有 就 不 都 而 及 对 以 为 也 这 那 吗 呢 吧 a an the is are was were of to in on for and or".split())

_CARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    chunk_refs TEXT NOT NULL,          -- JSON: [{turn_start, turn_end}]
    keywords TEXT NOT NULL,            -- JSON: [str]
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at REAL NOT NULL,
    last_access REAL NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    memory_type TEXT NOT NULL DEFAULT 'fact',
    tags TEXT NOT NULL DEFAULT '[]',   -- JSON: [str]
    weight REAL NOT NULL DEFAULT 0.5,
    enriched_at REAL
);
CREATE INDEX IF NOT EXISTS idx_cards_session ON index_cards(session_id);
"""


def heuristic_summary(turns: list[dict], topk: int = 6) -> tuple[str, list[str]]:
    """频词抽取主题 + 覆盖句。turns: [{role, content}]。返回 (summary, keywords)。"""
    text = " ".join(t.get("content", "") for t in turns)
    words = [w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}|[A-Za-z][A-Za-z0-9_-]{2,}", text)
             if w.lower() not in STOPWORDS]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    keywords = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:topk]]
    first = turns[0].get("content", "")[:80] if turns else ""
    summary = (first + "；主题词：" + "、".join(keywords))[:300]
    return summary, keywords


class IndexCardStore:
    def __init__(self, db_path: str | Path):
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(_CARD_SCHEMA)
        self._migrate()
        self.db.commit()

    def _migrate(self) -> None:
        """兼容旧库：缺失 enrichment 列时 ALTER TABLE 补列（幂等）。"""
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(index_cards)").fetchall()}
        for col, ddl in (
            ("memory_type", "ALTER TABLE index_cards ADD COLUMN memory_type TEXT NOT NULL DEFAULT 'fact'"),
            ("tags", "ALTER TABLE index_cards ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"),
            ("weight", "ALTER TABLE index_cards ADD COLUMN weight REAL NOT NULL DEFAULT 0.5"),
            ("enriched_at", "ALTER TABLE index_cards ADD COLUMN enriched_at REAL"),
        ):
            if col not in cols:
                self.db.execute(ddl)
                cols.add(col)

    def build_card(self, session_id: str, turns: list[dict],
                   summarizer=None, confidence: float | None = None) -> int:
        """从会话 turns 建一张压缩卡。summarizer(turns)->(summary,keywords) 可注入 LLM。"""
        summary, keywords = (summarizer or heuristic_summary)(turns)
        if confidence is None:
            # 启发式置信：覆盖率（有内容的 turn 占比）× 信息量（关键词数/topk）
            filled = sum(1 for t in turns if t.get("content", "").strip()) / max(len(turns), 1)
            confidence = round(min(1.0, 0.5 * filled + 0.5 * min(len(keywords) / 6, 1.0)), 3)
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO index_cards(session_id, topic, summary, chunk_refs, keywords,"
            " confidence, created_at, last_access) VALUES (?,?,?,?,?,?,?,?)",
            (session_id, keywords[0] if keywords else session_id, summary,
             json.dumps([{"turn_start": 0, "turn_end": len(turns) - 1}]),
             json.dumps(keywords), confidence, now, now),
        )
        self.db.commit()
        return cur.lastrowid

    def cards_for_session(self, session_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, session_id, topic, summary, chunk_refs, keywords, confidence, created_at,"
            " last_access, access_count, memory_type, tags, weight, enriched_at"
            " FROM index_cards WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [self._row2dict(r) for r in rows]

    def search_by_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, session_id, topic, summary, keywords, confidence FROM index_cards"
            " WHERE topic LIKE ? OR keywords LIKE ? OR summary LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [{"id": r[0], "session_id": r[1], "topic": r[2], "summary": r[3],
                 "keywords": json.loads(r[4]), "confidence": r[5]} for r in rows]

    def touch(self, card_id: int) -> None:
        """Phase1.5 配套：访问即续命（lifecycle 依据 last_access 衰减）。"""
        self.db.execute(
            "UPDATE index_cards SET last_access=?, access_count=access_count+1 WHERE id=?",
            (time.time(), card_id),
        )
        self.db.commit()

    @staticmethod
    def _row2dict(r) -> dict:
        return {
            "id": r[0], "session_id": r[1], "topic": r[2], "summary": r[3],
            "chunk_refs": json.loads(r[4]), "keywords": json.loads(r[5]),
            "confidence": r[6], "created_at": r[7], "last_access": r[8],
            "access_count": r[9], "memory_type": r[10],
            "tags": json.loads(r[11]) if r[11] else [],
            "weight": r[12], "enriched_at": r[13],
        }

    def close(self) -> None:
        self.db.close()
