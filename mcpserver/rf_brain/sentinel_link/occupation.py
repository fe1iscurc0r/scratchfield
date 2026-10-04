"""占用事件检测 + HandLog/记忆落地钩子（卷187 D）。

职责分两层（**本卷只做事件落地，不做决策**——决策留给后续"频谱大脑"卷）：

1. **检测**：`OccupationDetector` 逐帧喂入节点扫描结果，当**同一频点**连续
   高 RSSI 持续超过 `hold_s`（默认 60s）时，产出一条占用事件：
   `{node_id, freq_mhz, start_ts, end_ts, duration_s, peak_dbm, mean_dbm, n_samples}`。
   同一 (node, freq) 的持续性占用**只报一次**（事件结束后可再报新一轮）。

2. **落地**：`OccupationHandler` 订阅 EventBus 的 `lumo.sentinel.occupation`
   主题，把事件写入与现有 HamLog / 记忆体系一致的记录格式
   （SQLite 表 `sentinel_occupation`，并调用可选的外部 sink 钩子）。

阈值口径（可调，默认与工单"同频点 >60s 高 RSSI"一致）：

  - 高 RSSI 判定：`rssi_dbm >= high_threshold_dbm`（默认 **-85 dBm**）
  - 持续时长：`duration_s >= hold_s`（默认 **60.0 s**）
  - 频点容差：`freq_tol_mhz`（默认 0.2 MHz，覆盖 1 个扫描 step）
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .protocol import ScanBin

__all__ = [
    "Occupation",
    "OccupationConfig",
    "OccupationDetector",
    "get_detector",
    "reset_detector",
    "OccupationHandler",
    "ensure_occupation_table",
    "query_occupations",
]

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DB_ENV = "SENTINEL_LINK_DB"
_DEFAULT_DB = "sentinel_link.db"

OCCUPATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sentinel_occupation (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id    TEXT    NOT NULL,
    freq_mhz   REAL    NOT NULL,
    start_ts   REAL    NOT NULL,
    end_ts     REAL    NOT NULL,
    duration_s REAL    NOT NULL,
    peak_dbm   REAL    NOT NULL,
    mean_dbm   REAL,
    n_samples  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_occ_node_freq
    ON sentinel_occupation(node_id, freq_mhz, start_ts);
"""


def _utc_iso(ts: float | None = None) -> str:
    ts = time.time() if ts is None else ts
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _db_path(db_path: str | os.PathLike[str] | None = None) -> str:
    if db_path is None:
        db_path = os.environ.get(_DB_ENV) or str(_REPO_ROOT / _DEFAULT_DB)
    return str(db_path)


# ── 数据模型 ─────────────────────────────────────────────────────────────

@dataclass
class OccupationConfig:
    """检测阈值。"""

    high_threshold_dbm: float = -85.0
    hold_s: float = 60.0
    freq_tol_mhz: float = 0.2
    #: 两次样本间最大间隔——超过视为中断，计时清零（丢帧容忍）
    max_gap_s: float = 30.0


@dataclass
class Occupation:
    """一条占用事件。"""

    node_id: str
    freq_mhz: float
    start_ts: float
    end_ts: float
    duration_s: float
    peak_dbm: float
    mean_dbm: float
    n_samples: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "freq_mhz": round(self.freq_mhz, 4),
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_s": round(self.duration_s, 2),
            "peak_dbm": round(self.peak_dbm, 2),
            "mean_dbm": round(self.mean_dbm, 2),
            "n_samples": self.n_samples,
            "start_iso": _utc_iso(self.start_ts),
            "end_iso": _utc_iso(self.end_ts),
            "kind": "sentinel.occupation",
        }


@dataclass
class _Track:
    """单个 (node, freq) 的持续跟踪状态。"""

    freq_mhz: float
    start_ts: float
    last_ts: float
    peak_dbm: float
    sum_dbm: float = 0.0
    n: int = 0
    reported: bool = False

    def add(self, ts: float, dbm: float) -> None:
        self.last_ts = ts
        self.peak_dbm = max(self.peak_dbm, dbm)
        self.sum_dbm += dbm
        self.n += 1


# ── 检测器 ───────────────────────────────────────────────────────────────

class OccupationDetector:
    """逐帧占用检测。**有状态**，进程内单例（由 `get_detector()` 提供）。"""

    def __init__(self, cfg: OccupationConfig | None = None) -> None:
        self.cfg = cfg or OccupationConfig()
        self._tracks: dict[tuple[str, float], _Track] = {}
        self._lock = threading.RLock()

    # 频点归并：把 freqs 吸附到已跟踪的桶（容差内）
    def _bucket_key(self, node_id: str, freq: float) -> tuple[str, float]:
        for (nid, f) in list(self._tracks.keys()):
            if nid == node_id and abs(f - freq) <= self.cfg.freq_tol_mhz:
                return (nid, f)
        return (node_id, round(freq, 4))

    def feed(self, node_id: str, ts: float,
             bins: Iterable[ScanBin]) -> list[dict[str, Any]]:
        """喂一帧的频点扫描结果，返回**本轮新产生**的占用事件列表。"""
        out: list[dict[str, Any]] = []
        with self._lock:
            seen_keys: set[tuple[str, float]] = set()
            for b in bins:
                if b.rssi_dbm < self.cfg.high_threshold_dbm:
                    continue
                key = self._bucket_key(node_id, b.freq_mhz)
                seen_keys.add(key)
                tr = self._tracks.get(key)
                if tr is None:
                    self._tracks[key] = _Track(
                        freq_mhz=b.freq_mhz, start_ts=ts, last_ts=ts,
                        peak_dbm=b.rssi_dbm, sum_dbm=b.rssi_dbm, n=1)
                    continue
                if ts - tr.last_ts > self.cfg.max_gap_s:
                    # 断档 → 结算旧轨、开新轨
                    ev = self._maybe_emit(key, tr, closed=True)
                    if ev:
                        out.append(ev)
                    self._tracks[key] = _Track(
                        freq_mhz=b.freq_mhz, start_ts=ts, last_ts=ts,
                        peak_dbm=b.rssi_dbm, sum_dbm=b.rssi_dbm, n=1)
                    continue
                tr.add(ts, b.rssi_dbm)
                ev = self._maybe_emit(key, tr, closed=False)
                if ev:
                    out.append(ev)

            # 本轮未命中的高 RSSI 轨：若已持续够久则结算
            for key, tr in list(self._tracks.items()):
                if key in seen_keys:
                    continue
                if ts - tr.last_ts > self.cfg.max_gap_s:
                    ev = self._maybe_emit(key, tr, closed=True)
                    if ev:
                        out.append(ev)
                    del self._tracks[key]
        return out

    def _maybe_emit(self, key: tuple[str, float], tr: _Track,
                    *, closed: bool) -> dict[str, Any] | None:
        """到阈值且未报过 → 产事件（每个持续段只报一次）。"""
        dur = tr.last_ts - tr.start_ts
        if dur < self.cfg.hold_s or tr.reported:
            return None
        tr.reported = True
        occ = Occupation(
            node_id=key[0], freq_mhz=tr.freq_mhz,
            start_ts=tr.start_ts, end_ts=tr.last_ts, duration_s=dur,
            peak_dbm=tr.peak_dbm,
            mean_dbm=(tr.sum_dbm / tr.n) if tr.n else tr.peak_dbm,
            n_samples=tr.n,
        )
        logger.info("[occupation] %s @ %.3fMHz 持续 %.1fs（峰值 %.1fdBm）%s",
                    occ.node_id, occ.freq_mhz, occ.duration_s, occ.peak_dbm,
                    "（已结束）" if closed else "")
        return occ.as_dict()

    def active(self) -> list[dict[str, Any]]:
        """当前正在跟踪的轨（未达阈值也算），供调试。"""
        with self._lock:
            return [
                {"node_id": k[0], "freq_mhz": tr.freq_mhz,
                 "start_ts": tr.start_ts, "duration_s": tr.last_ts - tr.start_ts,
                 "peak_dbm": tr.peak_dbm, "reported": tr.reported}
                for k, tr in self._tracks.items()
            ]

    def reset(self) -> None:
        with self._lock:
            self._tracks.clear()


# 进程级单例（gateway 多帧间保持状态）
_detector: OccupationDetector | None = None


def get_detector() -> OccupationDetector:
    global _detector
    if _detector is None:
        _detector = OccupationDetector()
    return _detector


def reset_detector(cfg: OccupationConfig | None = None) -> OccupationDetector:
    """重建单例（测试/改阈值用）。"""
    global _detector
    _detector = OccupationDetector(cfg)
    return _detector


# ── 落地：表 + 处理器 ────────────────────────────────────────────────────

def ensure_occupation_table(db_path: str | os.PathLike[str] | None = None) -> str:
    """建好 occupation 表并返回库路径。"""
    path = _db_path(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(OCCUPATION_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def record_occupation(ev: dict[str, Any],
                      db_path: str | os.PathLike[str] | None = None) -> int:
    """落一条占用记录，返回 rowid。格式与 sentinel_* 系列表一致。"""
    path = _db_path(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(OCCUPATION_TABLE_SQL)
        cur = conn.execute(
            "INSERT INTO sentinel_occupation(node_id, freq_mhz, start_ts, end_ts,"
            " duration_s, peak_dbm, mean_dbm, n_samples, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (ev.get("node_id"), float(ev.get("freq_mhz", 0.0)),
             float(ev.get("start_ts", 0.0)), float(ev.get("end_ts", 0.0)),
             float(ev.get("duration_s", 0.0)), float(ev.get("peak_dbm", 0.0)),
             float(ev.get("mean_dbm", 0.0)), int(ev.get("n_samples", 0)),
             _utc_iso()))
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def query_occupations(*, node: str | None = None, hours: float = 72.0,
                      limit: int = 500,
                      db_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """按时间窗查占用记录（新→旧）。"""
    path = _db_path(db_path)
    since = time.time() - hours * 3600.0
    conn = sqlite3.connect(path)
    try:
        conn.executescript(OCCUPATION_TABLE_SQL)
        sql = ("SELECT id, node_id, freq_mhz, start_ts, end_ts, duration_s,"
               " peak_dbm, mean_dbm, n_samples, created_at"
               " FROM sentinel_occupation WHERE start_ts >= ?")
        args: list[Any] = [since]
        if node:
            sql += " AND node_id = ?"; args.append(node)
        sql += " ORDER BY start_ts DESC LIMIT ?"; args.append(int(limit))
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    cols = ("id", "node_id", "freq_mhz", "start_ts", "end_ts", "duration_s",
            "peak_dbm", "mean_dbm", "n_samples", "created_at")
    return [dict(zip(cols, r)) for r in rows]


class OccupationHandler:
    """订阅 `lumo.sentinel.occupation` → 落库（可选外送 HamLog/记忆）。

    :param db_path: 目标库（缺省与网关同库）
    :param extra_sinks: 额外落地回调列表 `(ev) -> None`，用于对接既有 HamLog /
        记忆体系；本卷默认不注册（等 HamLog 侧接口稳定），但钩子留出。
    """

    def __init__(self, db_path: str | os.PathLike[str] | None = None, *,
                 extra_sinks: list[Callable[[dict[str, Any]], None]] | None = None) -> None:
        self.db_path = ensure_occupation_table(db_path)
        self.extra_sinks = list(extra_sinks or [])
        self.recorded = 0
        self.errors = 0

    def handle(self, ev: dict[str, Any]) -> None:
        """EventBus handler 签名（同步）。异常不外抛，只计数。"""
        try:
            if isinstance(ev, str):
                ev = json.loads(ev)
            if not isinstance(ev, dict) or "node_id" not in ev:
                raise ValueError(f"占用事件格式非法: {ev!r}")
            record_occupation(ev, self.db_path)
            self.recorded += 1
            for sink in self.extra_sinks:
                try:
                    sink(ev)
                except Exception as e:              # noqa: BLE001 - 单 sink 失败不扩散
                    logger.warning("[occupation] 外部 sink 失败（忽略）: %s", e)
        except Exception as e:                      # noqa: BLE001 - handler 绝不抛
            self.errors += 1
            logger.warning("[occupation] 落地失败: %s", e)

    def attach(self, bus: Any = None) -> Any:
        """挂到 EventBus，返回 disposer。缺省用 Lumo 进程级总线。"""
        if bus is None:
            from apiserver.event_bus import get_bus
            bus = get_bus()
        return bus.on("lumo.sentinel.occupation", self.handle)

    def stats(self) -> dict[str, int]:
        return {"recorded": self.recorded, "errors": self.errors}
