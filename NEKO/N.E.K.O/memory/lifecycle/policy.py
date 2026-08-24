"""SPEC-03 Phase1.4/1.5 — 后台静默写入 + 记忆更新/过期（旁路）。

background.BackgroundWriter：会话摘要 → index_cards 的静默队列线程，
不进 chat token（提交方只入队即返回）。与 NEKO 现有 embedding_worker /
post_turn 写入路径零交集。
policy：last_access 指数衰减 + confidence 门控的 keep/decay/expire 决策。
License: Apache-2.0。
"""
from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..index_cards.store import IndexCardStore, heuristic_summary


# ---------------------------------------------------------------- lifecycle 策略

@dataclass
class LifecyclePolicy:
    half_life_days: float = 14.0        # 半衰期：14 天未访问权重减半
    expire_weight: float = 0.05         # 衰减权重低于此值 → expire
    decay_weight: float = 0.4           # 低于此值 → decay（降权待观察）
    min_confidence_keep: float = 0.25   # 置信度低于此值不参与 keep


def decay_weight(last_access: float, now: float | None = None,
                 half_life_days: float = 14.0) -> float:
    """指数衰减权重 ∈ (0,1]。"""
    now = now or time.time()
    age_days = max(0.0, (now - last_access) / 86400.0)
    return math.pow(0.5, age_days / max(half_life_days, 1e-6))


def expire_decision(record: dict, policy: LifecyclePolicy | None = None,
                    now: float | None = None) -> str:
    """record: {last_access, confidence}。返回 keep | decay | expire。"""
    p = policy or LifecyclePolicy()
    w = decay_weight(record.get("last_access", 0), now, p.half_life_days)
    conf = float(record.get("confidence", 0.5))
    if conf < p.min_confidence_keep:
        return "decay"
    if w * conf < p.expire_weight:
        return "expire"
    if w < p.decay_weight:
        return "decay"
    return "keep"


def enrich(records: list[dict], policy: LifecyclePolicy | None = None,
           now: float | None = None) -> list[dict]:
    """批量为卡片记录附上 weight/decision（不修改原表，返回副本）。"""
    p = policy or LifecyclePolicy()
    out = []
    for r in records:
        rr = dict(r)
        rr["weight"] = round(decay_weight(r.get("last_access", 0), now, p.half_life_days), 4)
        rr["decision"] = expire_decision(r, p, now)
        out.append(rr)
    return out


# ---------------------------------------------------------------- 后台静默写入

class BackgroundWriter:
    """队列消费线程：submit_session_summary 只入队（调用方零等待零 token），
    worker 线程离线建卡。drain() 供测试同步等待。"""

    def __init__(self, store: IndexCardStore | None = None,
                 db_path: str | Path = ":memory:"):
        self.store = store or IndexCardStore(db_path)
        self.q: "queue.Queue[tuple[str, list[dict]]]" = queue.Queue()
        self._stop = threading.Event()
        self.stats = {"submitted": 0, "written": 0, "errors": 0}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="neko-index-card-writer")
        self._thread.start()

    def submit_session_summary(self, session_id: str, turns: list[dict]) -> bool:
        """非阻塞提交。turns 由调用方持有（已是本地数据，不产生额外 chat token）。"""
        self.stats["submitted"] += 1
        self.q.put((session_id, list(turns)))
        # F-01: sync_turn 钩子（默认关闭，开启时每轮提交触发）
        try:
            from ..hooks import HOOK_SYNC_TURN, hooks as _hooks

            _hooks.emit(HOOK_SYNC_TURN, {
                "session_id": session_id,
                "turns": list(turns),
                "enqueued": True,
            })
        except Exception:  # noqa: BLE001 — 钩子失败不影响入队
            pass
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sid, turns = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                card_id = self.store.build_card(sid, turns, summarizer=heuristic_summary)
                self.stats["written"] += 1
                # F-01: on_memory_write 钩子（默认关闭；卡片落库后触发）
                try:
                    from ..hooks import HOOK_MEMORY_WRITE, hooks as _hooks

                    _hooks.emit(HOOK_MEMORY_WRITE, {
                        "session_id": sid,
                        "card_id": card_id,
                        "written": True,
                    }, dedup_key=f"card:{sid}:{card_id}")
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001 — 后台线程不能死
                self.stats["errors"] += 1

    def drain(self, timeout: float = 5.0) -> bool:
        """等待队列清空（测试用）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.q.empty() and self.stats["written"] + self.stats["errors"] >= self.stats["submitted"]:
                return True
            time.sleep(0.02)
        return False

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
