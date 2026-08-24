"""记忆 MaaS 核心 — NEKO 记忆五件套的进程内组合层（只增不改 NEKO）。

设计依据 docs/Memory-MaaS-Research-v1.md：
- 五件套是纯标准库旁路（NEKO/N.E.K.O/memory/），本模块只做 sys.path 注入 +
  import + 组合，不修改 NEKO 任何文件（桌宠壳零改动硬约束）。
- 单写者纪律：三库均为裸 sqlite3（无 WAL/锁），sidecar 是数据目录唯一写进程，
  进程内以一把 RLock 串行化全部读写（毫秒级操作，粒度可接受）。
- 写入即可检索闭环：卡片经 BackgroundWriter 后台写入（SPEC-03 "提交方零等待"），
  写完把卡片文本同步进 HybridSearchIndex，检索命中回附会话血统。

存储布局（MEMORY_MAAS_DATA_DIR，默认 <repo>/memory_maas_data/，已 gitignore）：
    lineage.db / cards.db / hs.db
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]  # scratchpad/
_NEKO_ROOT = _REPO_ROOT / "NEKO" / "N.E.K.O"


class MemoryMaasError(RuntimeError):
    """MaaS 层错误（fail-fast，不静默空返回）。"""


def ensure_neko_path() -> str:
    """把 NEKO/N.E.K.O 注入 sys.path（与 tests/test_spec03_phase1.py 同款手法）。"""
    p = str(_NEKO_ROOT)
    if _NEKO_ROOT.is_dir() and p not in sys.path:
        sys.path.insert(0, p)
    return p


def _import_five_pieces():
    """导入五件套（延迟到运行期，模块 import 期不碰 NEKO）。"""
    ensure_neko_path()
    try:
        from memory.hybrid_search.rrf import HybridSearchIndex, Record
        from memory.index_cards.store import IndexCardStore
        from memory.lineage.model import LineageError, SessionLineage
        from memory.lifecycle.policy import BackgroundWriter, LifecyclePolicy, enrich
    except ImportError as e:  # NEKO 子树缺失/损坏时给出可定位错误
        raise MemoryMaasError(
            f"记忆五件套导入失败（NEKO 根目录={_NEKO_ROOT}）: {e}") from e
    return HybridSearchIndex, Record, IndexCardStore, LineageError, \
        SessionLineage, BackgroundWriter, LifecyclePolicy, enrich


# 模块级单例（sidecar 进程内共享；测试可传入独立实例覆盖）
_CORE: "MemoryMaasCore | None" = None
_CORE_LOCK = threading.Lock()


class MemoryMaasCore:
    """五件套组合核心：lineage + cards(后台写) + hybrid_search + lifecycle。"""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        (HybridSearchIndex, Record, IndexCardStore, LineageError,
         SessionLineage, BackgroundWriter, LifecyclePolicy, enrich) = \
            _import_five_pieces()
        # 把类钉在实例上，避免每次调用重复 import 解析
        self._HybridSearchIndex = HybridSearchIndex
        self._Record = Record
        self._IndexCardStore = IndexCardStore
        self._LineageError = LineageError
        self._SessionLineage = SessionLineage
        self._BackgroundWriter = BackgroundWriter
        self._enrich = enrich
        self.policy = LifecyclePolicy()

        self.data_dir = Path(data_dir or os.environ.get("MEMORY_MAAS_DATA_DIR")
                             or (_REPO_ROOT / "memory_maas_data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._lineage = SessionLineage(self.data_dir / "lineage.db")
        self._cards = IndexCardStore(self.data_dir / "cards.db")
        self._hs = HybridSearchIndex(self.data_dir / "hs.db")
        self._writer = BackgroundWriter(store=self._cards,
                                        db_path=str(self.data_dir / "cards.db"))
        # hs 库不存 Record.meta → 自维护 record_id→meta 映射（启动时从 cards 库重建）
        self._meta_by_id: dict[str, dict[str, Any]] = {}
        self._rebuild_meta()

    def _rebuild_meta(self) -> None:
        """从 cards 库重建检索命中的 meta（进程重启后仍可溯源）。"""
        for card in self._all_cards_full():
            self._meta_by_id[f"card:{card['id']}"] = {
                "card_id": card["id"],
                "session_id": card["session_id"],
                "summary": card.get("summary") or "",
                "topic": card.get("topic") or "",
                "last_access": card.get("last_access"),
            }

    def _all_cards_full(self) -> list[dict[str, Any]]:
        """全量卡片含 last_access（search_by_keyword 不返回该列，直查底层）。"""
        rows = self._cards.db.execute(
            "SELECT id, session_id, topic, summary, keywords, confidence,"
            " created_at, last_access, access_count FROM index_cards"
            " ORDER BY id").fetchall()
        return [{"id": r[0], "session_id": r[1], "topic": r[2],
                 "summary": r[3], "keywords": r[4], "confidence": r[5],
                 "created_at": r[6], "last_access": r[7],
                 "access_count": r[8]} for r in rows]

    # ---- 生命周期 ----
    def start(self) -> None:
        with self._lock:
            self._writer.start()

    def close(self) -> None:
        with self._lock:
            try:
                self._writer.stop(timeout=2.0)
            except Exception as e:  # 停写线程失败不阻塞关闭
                logger.warning("[memory_maas] 停止后台写线程失败: %s", e)
            for store in (self._lineage, self._cards, self._hs):
                try:
                    store.close()
                except Exception:
                    pass

    # ---- 血统（lineage） ----
    def register_session(self, session_id: str, parent_id: str | None = None,
                         branch_label: str = "main",
                         summary: str = "") -> dict[str, Any]:
        if not session_id:
            raise MemoryMaasError("session_id 不能为空")
        with self._lock:
            return self._lineage.register(session_id, parent_id=parent_id,
                                          branch_label=branch_label,
                                          summary=summary)

    def trace(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._lineage.trace(session_id)

    def children(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._lineage.children(session_id)

    def branches_under(self, root_id: str) -> dict[str, list[str]]:
        with self._lock:
            return self._lineage.branches_under(root_id)

    # ---- 索引卡（index_cards + 后台写入） ----
    def write_card(self, session_id: str, turns: list[dict[str, Any]],
                   drain_timeout: float = 5.0) -> dict[str, Any]:
        """后台写卡 + 检索索引同步。drain 等待是为了 HTTP 同步语义。"""
        if not session_id:
            raise MemoryMaasError("session_id 不能为空")
        if not isinstance(turns, list):
            raise MemoryMaasError("turns 必须是数组（对话轮次列表）")
        with self._lock:
            # 写入即有血统：会话未登记时自动补为根节点（已登记则不动其血统）
            if self._lineage.get(session_id) is None:
                self._lineage.register(session_id,
                                       summary=f"[auto] {session_id} 写卡自动登记")
            t0 = time.perf_counter()
            queued = self._writer.submit_session_summary(session_id, turns)
            if not queued:
                raise MemoryMaasError("后台写入队列提交失败（writer 未启动？）")
            self._writer.drain(timeout=drain_timeout)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            cards = self._cards.cards_for_session(session_id)
            if not cards:
                raise MemoryMaasError(
                    f"后台写入未落卡（drain 超时？session={session_id}）")
            # 新卡同步进混合检索索引（id 稳定：card:<id>）
            for card in cards:
                record_id = f"card:{card['id']}"
                self._hs.add(self._Record(
                    id=record_id,
                    text=f"{card.get('topic') or ''} {card.get('summary') or ''}",
                    vector=None,
                    meta={}))
                self._meta_by_id[record_id] = {
                    "card_id": card["id"], "session_id": session_id,
                    "summary": card.get("summary") or "",
                    "topic": card.get("topic") or "",
                    "last_access": card.get("last_access"),
                }
            return {"ok": True, "session_id": session_id,
                    "cards": cards, "submit_latency_ms": latency_ms,
                    "writer_stats": dict(self._writer.stats)}

    def cards_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._cards.cards_for_session(session_id)

    def search_cards(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return self._cards.search_by_keyword(keyword, limit=limit)

    def touch_card(self, card_id: int) -> None:
        with self._lock:
            self._cards.touch(card_id)

    # ---- 混合检索（hybrid_search + 血统回附） ----
    def search(self, query: str, limit: int = 10,
               query_vec: list[float] | None = None,
               with_lineage: bool = True) -> dict[str, Any]:
        if not (query or "").strip():
            raise MemoryMaasError("query 不能为空")
        limit = max(1, min(int(limit or 10), 50))
        with self._lock:
            hits = self._hs.search(query, query_vec=query_vec, limit=limit)
            matches = []
            for record_id, score in hits:
                meta = self._meta_by_id.get(record_id, {})
                entry: dict[str, Any] = {"id": record_id, "score": round(score, 6),
                                         **meta}
                if with_lineage and meta.get("session_id"):
                    entry["lineage"] = self._safe_trace(meta["session_id"])
                matches.append(entry)
            return {"ok": True, "query": query, "count": len(matches),
                    "matches": matches,
                    "stats": {"records": self._hs.count()}}

    def _safe_trace(self, session_id: str) -> list[dict[str, Any]]:
        try:
            return self._lineage.trace(session_id)
        except Exception:
            return []  # 卡片先于血统登记时血统为空，不炸检索

    # ---- 生命周期（lifecycle） ----
    def lifecycle_report(self, limit: int = 500) -> dict[str, Any]:
        """全量卡片 → 衰减/过期决策报告（keep/decay/expire 汇总 + 明细）。"""
        with self._lock:
            cards = self._all_cards_full()[:limit]
            records = [{"card_id": c["id"],
                        "session_id": c["session_id"],
                        "last_access": c.get("last_access") or time.time(),
                        "confidence": float(c.get("confidence") or 0.5)}
                       for c in cards]
            enriched = self._enrich(records, policy=self.policy)
            decisions = [r["decision"] for r in enriched]
            return {
                "ok": True,
                "policy": {"half_life_days": self.policy.half_life_days,
                           "expire_weight": self.policy.expire_weight,
                           "decay_weight": self.policy.decay_weight,
                           "min_confidence_keep": self.policy.min_confidence_keep},
                "total": len(enriched),
                "keep": decisions.count("keep"),
                "decay": decisions.count("decay"),
                "expire": decisions.count("expire"),
                "records": enriched,
            }

    def enrich_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """纯函数暴露：外部记录批量附衰减/过期决策（无落盘副作用）。"""
        if not isinstance(records, list) or not records:
            raise MemoryMaasError("records 必须是非空数组")
        with self._lock:
            return {"ok": True, "records": self._enrich(records,
                                                        policy=self.policy)}

    # ---- 状态 ----
    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "data_dir": str(self.data_dir),
                "neko_root": str(_NEKO_ROOT),
                "lineage_sessions": self._lineage.db.execute(
                    "SELECT COUNT(*) FROM sessions").fetchone()[0],
                "cards": self._cards.db.execute(
                    "SELECT COUNT(*) FROM index_cards").fetchone()[0],
                "hs_records": self._hs.count(),
                "writer_stats": dict(self._writer.stats),
            }


def get_core(data_dir: str | Path | None = None,
             fresh: bool = False) -> MemoryMaasCore:
    """sidecar 进程内单例（测试用 fresh=True 换独立实例时先 close 旧的）。"""
    global _CORE
    with _CORE_LOCK:
        if fresh and _CORE is not None:
            _CORE.close()
            _CORE = None
        if _CORE is None:
            _CORE = MemoryMaasCore(data_dir)
            _CORE.start()
        return _CORE


def reset_core() -> None:
    """测试收尾：close 并清空单例（下次 get_core 按 MEMORY_MAAS_DATA_DIR 重建）。"""
    global _CORE
    with _CORE_LOCK:
        if _CORE is not None:
            _CORE.close()
        _CORE = None
