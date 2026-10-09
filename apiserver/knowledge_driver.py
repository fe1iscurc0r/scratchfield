"""知识驱动自举回路（卷131 W131-04 + W131-07）。

日报/RSS/论文 digest 不是存着吃灰，而是真的进入 Lumo 的判断依据：
检索相关知识进 rag_section、工具效果打标签写回、按历史效果推荐工具。

自研设计（不整抄）：
- KnowledgeDriver.query_relevant(goal, context, k) → 检索知识项（TF 关键词匹配，
  复用 local_search 思想但不依赖外部向量服务——保持零外部依赖纪律）
- tag_tool_outcome(tool_name, result, task_context) → 工具效果写回
  （W131-07：success/failure/partial 分类 + 错误类型 + 时间衰减评分
   score = 0.7*old + 0.3*new，效果差降权但不下线）
- get_tool_recommendation(current_task) → 差异化推荐（高分在前，LLM 最终决策）
- 存储：SQLite（仓内既有 aiosqlite 纪律），表 knowledge_items + tool_outcomes
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 时间衰减系数（工单 W131-07.4 原文：score = 0.7*old_score + 0.3*new_score）
_DECAY_OLD, _DECAY_NEW = 0.7, 0.3


def _zh_ngrams(s: str, n: int = 2) -> set[str]:
    """中文 2-gram 切分（连续汉字串 → 重叠二元组）。

    例："热解动力学" → {"热解", "解动", "动力学"}——子串匹配靠 2-gram 交集。
    纯英文词直接整体返回（小写化）。
    """
    out: set[str] = set()
    for tok in re.findall(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]{2,}", s):
        if tok[0].isascii():
            out.add(tok.lower())
        else:
            for i in range(len(tok) - n + 1):
                out.add(tok[i:i + n])
    return out


def _default_db_path() -> Path:
    return Path.home() / ".lumo" / "knowledge_store.db"


@dataclass
class KnowledgeItem:
    """一条知识项（日报结论 / RSS 要点 / 论文摘要 / 工具经验）。"""
    item_id: str
    source_type: str          # daily_brief / rss / paper_digest / tool_outcome
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    # W131-04.2 schema 扩展
    tool_effectiveness_score: float | None = None
    last_used_task: str = ""


@dataclass
class ToolRecommendation:
    tool_name: str
    score: float
    sample_count: int
    reason: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    item_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    tool_effectiveness_score REAL,
    last_used_task TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge_items(source_type);
CREATE TABLE IF NOT EXISTS tool_outcomes (
    tool_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    outcome TEXT NOT NULL,            -- success / failure / partial
    error_type TEXT DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (tool_name, task_type, created_at)
);
CREATE TABLE IF NOT EXISTS tool_scores (
    tool_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.5,
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (tool_name, task_type)
);
"""


class KnowledgeDriver:
    """知识驱动器：检索 + 写回 + 推荐。"""

    def __init__(self, db_path: str | Path | None = None):
        self._db = Path(db_path) if db_path else _default_db_path()
        # RLock（可重入）：_ensure_db 在业务方法的锁内被调，普通 Lock 会死锁
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_db()

    def _ensure_db(self) -> None:
        with self._lock:
            if self._conn is None:
                self._db.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(str(self._db), check_same_thread=False,
                                             timeout=10.0)
                self._conn.row_factory = sqlite3.Row
                # WAL + busy_timeout：避免 Windows 文件锁挂起（测试/多线程场景）
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout=10000")
                self._conn.executescript(_SCHEMA)
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ---------- W131-04.1: 检索 ----------
    def query_relevant(self, goal: str, context: str = "", k: int = 5) -> list[KnowledgeItem]:
        """给定当前任务目标，检索相关知识项（TF 关键词匹配 + 新鲜度微调）。"""
        with self._lock:
            self._ensure_db()
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items ORDER BY created_at DESC LIMIT 500").fetchall()
        goal_terms = _zh_ngrams(goal + " " + context)
        if not goal_terms:
            return []
        scored = []
        for r in rows:
            blob = f"{r['title']} {r['content']} {' '.join(json.loads(r['tags']))}"
            overlap = goal_terms & _zh_ngrams(blob)
            if not overlap:
                continue
            # 新鲜度：一周内 ×1.2，一月内 ×1.0，更旧 ×0.8
            age_days = (time.time() - r["created_at"]) / 86400
            fresh = 1.2 if age_days < 7 else (1.0 if age_days < 30 else 0.8)
            scored.append((len(overlap) * fresh, r, overlap))
        scored.sort(key=lambda x: -x[0])
        out = []
        for s, r, ov in scored[:k]:
            # 命中即更新 last_used_task（知识被"用过"的痕迹）
            with self._lock:
                self._conn.execute(
                    "UPDATE knowledge_items SET last_used_task=? WHERE item_id=?",
                    (goal[:80], r["item_id"]))
                self._conn.commit()
            out.append(KnowledgeItem(
                item_id=r["item_id"], source_type=r["source_type"], title=r["title"],
                content=r["content"], tags=json.loads(r["tags"]),
                created_at=r["created_at"],
                tool_effectiveness_score=r["tool_effectiveness_score"],
                last_used_task=goal[:80]))  # 返回更新后的值（调用方视角一致）
        return out

    # ---------- W131-04.2 + W131-07: 写回 ----------
    def ingest(self, source_type: str, title: str, content: str,
               tags: list[str] | None = None, item_id: str | None = None) -> str:
        """写入一条知识项（/api/knowledge/ingest 端点 + cron 管道共用）。"""
        iid = item_id or f"{source_type}-{int(time.time()*1000)}-{abs(hash(title)) % 10000}"
        with self._lock:
            self._ensure_db()
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_items "
                "(item_id, source_type, title, content, tags, created_at) VALUES (?,?,?,?,?,?)",
                (iid, source_type, title[:200], content[:4000],
                 json.dumps(tags or [], ensure_ascii=False), time.time()))
            self._conn.commit()
        return iid

    def tag_tool_outcome(self, tool_name: str, result: dict | Any,
                         task_context: str = "") -> None:
        """工具执行结果打标签写回（W131-04.1 + W131-07.1/2）。

        result 分类：success / failure / partial；failure 记错误类型；
        评分时间衰减更新（0.7*old + 0.3*new）——效果差降权但不下线。
        """
        # 1) 结果分类
        if isinstance(result, dict):
            ok = result.get("ok", result.get("success", False))
            err = str(result.get("error", result.get("error_type", "")))[:120]
            outcome = "success" if ok else "failure"
            if ok and result.get("partial"):
                outcome = "partial"
        else:
            outcome, err = ("success", "") if result else ("failure", "")

        # 2) 任务类型提取（task_context 的首个标签词；空则用 "default"）
        task_type = (re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", task_context)[:1] or ["default"])[0].lower()

        with self._lock:
            self._ensure_db()
            now = time.time()
            # 记 outcome 明细
            self._conn.execute(
                "INSERT OR REPLACE INTO tool_outcomes VALUES (?,?,?,?,?)",
                (tool_name, task_type, outcome, err if outcome == "failure" else "", now))
            # 衰减更新评分
            row = self._conn.execute(
                "SELECT score, sample_count FROM tool_scores WHERE tool_name=? AND task_type=?",
                (tool_name, task_type)).fetchone()
            new_val = {"success": 1.0, "partial": 0.5, "failure": 0.0}[outcome]
            if row:
                old, n = row["score"], row["sample_count"]
                score = _DECAY_OLD * old + _DECAY_NEW * new_val
                self._conn.execute(
                    "UPDATE tool_scores SET score=?, sample_count=?, updated_at=? "
                    "WHERE tool_name=? AND task_type=?",
                    (score, n + 1, now, tool_name, task_type))
            else:
                score = 0.5 + _DECAY_NEW * (new_val - 0.5)
                self._conn.execute(
                    "INSERT INTO tool_scores VALUES (?,?,?,?,?)",
                    (tool_name, task_type, score, 1, now))
            self._conn.commit()
            # 知识项同步（让 query_relevant 也能检索到工具经验）
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_items "
                "(item_id, source_type, title, content, tags, created_at, tool_effectiveness_score, last_used_task) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"tool:{tool_name}:{task_type}", "tool_outcome",
                 f"工具 {tool_name} 在 {task_type} 任务的表现",
                 f"最近结果: {outcome}" + (f"（{err}）" if err else ""),
                 json.dumps([tool_name, task_type, "tool_experience"], ensure_ascii=False),
                 now, score, task_context[:80]))
            self._conn.commit()

    # ---------- W131-04.1 + W131-07.2: 推荐 ----------
    def get_tool_recommendation(self, current_task: str) -> list[ToolRecommendation]:
        """根据历史效果推荐工具（高分在前；效果差降权但不下线——LLM 最终决策）。"""
        task_type = (re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", current_task)[:1] or ["default"])[0].lower()
        with self._lock:
            self._ensure_db()
            rows = self._conn.execute(
                "SELECT tool_name, score, sample_count FROM tool_scores "
                "WHERE task_type=? ORDER BY score DESC", (task_type,)).fetchall()
            # 无该任务类型记录时回退到全局（所有任务类型的均值）
            if not rows:
                rows = self._conn.execute(
                    "SELECT tool_name, AVG(score) AS score, SUM(sample_count) AS sample_count "
                    "FROM tool_scores GROUP BY tool_name ORDER BY score DESC").fetchall()
        return [ToolRecommendation(
            tool_name=r["tool_name"], score=round(r["score"], 3),
            sample_count=r["sample_count"],
            reason=f"{task_type} 历史评分 {r['score']:.2f}（{r['sample_count']} 次）")
            for r in rows]

    # ---------- 测试/运维辅助 ----------
    def stats(self) -> dict:
        with self._lock:
            self._ensure_db()
            n_items = self._conn.execute("SELECT COUNT(*) c FROM knowledge_items").fetchone()["c"]
            n_scores = self._conn.execute("SELECT COUNT(*) c FROM tool_scores").fetchone()["c"]
        return {"knowledge_items": n_items, "tool_scores": n_scores}


# 进程级单例
_driver: KnowledgeDriver | None = None


_driver_lock = threading.Lock()


def get_knowledge_driver(db_path: str | Path | None = None) -> KnowledgeDriver:
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = KnowledgeDriver(db_path)
    return _driver
