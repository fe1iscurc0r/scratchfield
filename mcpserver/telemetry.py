"""telemetry.py — 工具调用画像 + 快速失败/熔断（卷189-B）。

B1 调用画像
-----------
表 `tool_calls(id, ts, tool, agent, caller, duration_ms, status, error_kind)`（SQLite）。
写入走**后台队列 + 批量 flush**——队列满则静默丢弃，绝不阻塞调用主路径
（工单红线：调用延迟回归 ≤2%）。

B2 快速失败与熔断
-----------------
- 同一工具 5 分钟窗口失败率 >50% 且样本 ≥5 → 熔断 10 分钟；
- 冷却期满后**半开**：放行一次探测，成功即复位，失败重新熔断；
- 熔断状态可查（circuit_states()）；
- **只作用于外部/adapter 工具**，内置核心 agent 不熔断（工单红线：防止把自己脑子断了）。

纯 Python 标准库（sqlite3 + queue + threading + time），零新重依赖。
时间源可注入（_now），便于单测不 sleep。
"""
from __future__ import annotations

import os
import queue
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

# ---- B2 默认参数（工单口径）----
FAILURE_WINDOW_S = 300      # 5 分钟滑动窗口
COOLDOWN_S = 600            # 熔断 10 分钟
FAILURE_THRESHOLD = 0.5     # 失败率 >50%
MIN_SAMPLES = 5             # 样本 ≥5 才判熔断

# 熔断状态
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"

# 内置（manifest 型）来源不熔断——只熔外部/adapter
EXEMPT_SOURCES = {"manifest"}


def _default_db_path() -> Path:
    """默认落盘：{用户数据目录}/tool_calls.db（与其它 SQLite 一致）。"""
    try:
        from system.config import get_data_dir
        d = Path(get_data_dir())
    except Exception:
        d = Path(os.environ.get("LUMO_DATA_DIR") or (Path.home() / ".lumo"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "tool_calls.db"


class CallRecorder:
    """调用画像写入器：后台线程 + 队列批量 flush（非阻塞）。"""

    def __init__(self, db_path: str | Path | None = None, *,
                 flush_interval: float = 2.0, batch_size: int = 50,
                 max_queue: int = 10000):
        self.db_path = str(db_path or _default_db_path())
        self._q: queue.Queue[tuple] = queue.Queue(maxsize=max_queue)
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._dropped = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._init_db()

    # ---- 表结构 ----

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    tool TEXT NOT NULL,
                    agent TEXT DEFAULT '',
                    caller TEXT DEFAULT '',
                    duration_ms REAL DEFAULT 0,
                    status TEXT DEFAULT 'ok',
                    error_kind TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_ts "
                         "ON tool_calls(tool, ts)")
            conn.commit()
        finally:
            conn.close()

    # ---- 写入（非阻塞）----

    def record(self, tool: str, *, agent: str = "", caller: str = "",
               duration_ms: float = 0.0, status: str = "ok",
               error_kind: str = "") -> None:
        """入队一条调用记录；队列满则静默丢弃（绝不阻塞调用方）。"""
        item = (time.time(), tool, agent, caller, float(duration_ms), status, error_kind)
        try:
            self._q.put_nowait(item)
        except queue.Full:
            with self._lock:
                self._dropped += 1

    def start(self) -> None:
        """启动后台 flush 线程（幂等）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tool-call-flush",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """停止后台线程并 flush 剩余（幂等）。"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._flush_once()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._flush_interval)
            self._flush_once()

    def _flush_once(self) -> int:
        """批量落盘（最多 batch_size 条）。返回写入条数。"""
        rows = []
        while len(rows) < self._batch_size:
            try:
                rows.append(self._q.get_nowait())
            except queue.Empty:
                break
        if not rows:
            return 0
        conn = self._connect()
        try:
            conn.executemany(
                "INSERT INTO tool_calls(ts, tool, agent, caller, duration_ms, status, error_kind)"
                " VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
        finally:
            conn.close()
        return len(rows)

    def flush(self) -> int:
        """同步 flush（测试/关停用）。"""
        return self._flush_once()

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    # ---- 聚合查询 ----

    def stats(self, window: str = "7d") -> dict[str, Any]:
        """按工具聚合：调用数 / P50 / P95 / 失败率 / 最近错误（供 GET /tools/stats）。"""
        secs = parse_window(window)
        since = time.time() - secs
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT tool, duration_ms, status, error_kind, ts FROM tool_calls "
                "WHERE ts >= ? ORDER BY ts", (since,))
            buckets: dict[str, list] = {}
            for tool, dur, status, err, ts in cur.fetchall():
                buckets.setdefault(tool, []).append((dur, status, err, ts))
        finally:
            conn.close()

        out: dict[str, Any] = {}
        for tool, rows in buckets.items():
            durs = sorted(float(r[0]) for r in rows)
            calls = len(rows)
            errors = sum(1 for r in rows if r[1] != "ok")
            last_err = ""
            last_ts = 0.0
            for dur, status, err, ts in rows:
                if ts >= last_ts:
                    last_ts = ts
                if status != "ok" and err:
                    last_err = err
            out[tool] = {
                "calls": calls,
                "p50_ms": round(_percentile(durs, 50), 2),
                "p95_ms": round(_percentile(durs, 95), 2),
                "errors": errors,
                "error_rate": round(errors / calls, 4) if calls else 0.0,
                "last_error": last_err,
                "last_call_ts": last_ts,
            }
        return out

    def total_rows(self) -> int:
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0])
        finally:
            conn.close()


def _percentile(sorted_vals: list[float], p: float) -> float:
    """线性插值百分位（sorted_vals 必须已升序）；空列表返回 0。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def parse_window(window: str) -> float:
    """'7d' / '24h' / '30m' / '90s' / 纯数字(秒) → 秒数；非法回退 7d。"""
    w = str(window or "").strip().lower()
    if not w:
        return 7 * 86400
    unit = w[-1]
    try:
        n = float(w[:-1]) if unit.isalpha() else float(w)
    except ValueError:
        return 7 * 86400
    if not unit.isalpha():
        return n
    return {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 86400) * n


class CircuitBreaker:
    """熔断器：滑动窗口失败率 + 冷却 + 半开探测。

    allow(tool, source) → True=放行 / False=熔断中（调用侧返回 tool_circuit_open）。
    record(tool, ok)    → 记一次结果（成功/失败）。
    exempt 来源（内置 manifest）恒放行、不参与熔断判定。
    """

    def __init__(self, *, window_s: float = FAILURE_WINDOW_S,
                 cooldown_s: float = COOLDOWN_S,
                 threshold: float = FAILURE_THRESHOLD,
                 min_samples: int = MIN_SAMPLES,
                 now_fn: Callable[[], float] = time.time):
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.threshold = threshold
        self.min_samples = min_samples
        self._now = now_fn
        self._events: dict[str, deque[tuple[float, bool]]] = {}
        self._open_until: dict[str, float] = {}
        self._half_open: dict[str, bool] = {}   # 已放行探测、待结果
        self._last_error: dict[str, str] = {}
        self._lock = threading.Lock()

    def _prune(self, tool: str, now: float) -> deque[tuple[float, bool]]:
        dq = self._events.setdefault(tool, deque())
        cutoff = now - self.window_s
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        return dq

    def allow(self, tool: str, source: str = "manifest") -> bool:
        """是否放行本次调用。"""
        if source in EXEMPT_SOURCES:
            return True   # 内置核心 agent 不熔断
        now = self._now()
        with self._lock:
            until = self._open_until.get(tool)
            if until is None:
                return True
            if now >= until:
                # 冷却期满 → 半开：放行一次探测
                self._half_open[tool] = True
                return True
            return False

    def record(self, tool: str, ok: bool, *, source: str = "manifest",
               error: str = "") -> None:
        """记录一次结果并更新熔断状态。"""
        if source in EXEMPT_SOURCES:
            return  # 内置不参与熔断
        now = self._now()
        with self._lock:
            if error:
                self._last_error[tool] = error
            # 半开探测结果
            if self._half_open.get(tool):
                self._half_open[tool] = False
                self._open_until.pop(tool, None)     # 探测成功或失败都先复位
                if ok:
                    self._events.pop(tool, None)     # 成功 → 完全复位
                    return
                # 探测失败 → 立即重新熔断
                self._open_until[tool] = now + self.cooldown_s
                return
            dq = self._prune(tool, now)
            dq.append((now, bool(ok)))
            if len(dq) >= self.min_samples:
                fails = sum(1 for _, ok_ in dq if not ok_)
                if fails / len(dq) > self.threshold:
                    self._open_until[tool] = now + self.cooldown_s

    def state(self, tool: str) -> dict[str, Any]:
        """该工具当前熔断状态（closed/open/half_open + 窗口样本与失败率）。"""
        now = self._now()
        with self._lock:
            until = self._open_until.get(tool)
            dq = self._prune(tool, now)
            samples = len(dq)
            fails = sum(1 for _, ok_ in dq if not ok_)
            if until is None:
                st = STATE_CLOSED
            elif now >= until or self._half_open.get(tool):
                st = STATE_HALF_OPEN
            else:
                st = STATE_OPEN
            return {
                "tool": tool,
                "state": st,
                "samples": samples,
                "failures": fails,
                "fail_rate": round(fails / samples, 4) if samples else 0.0,
                "open_until": until or 0.0,
                "last_error": self._last_error.get(tool, ""),
            }

    def states(self) -> dict[str, dict[str, Any]]:
        """所有非 closed 工具的状态（供 GET /tools/circuit）。"""
        with self._lock:
            tools = set(self._open_until) | set(self._half_open)
        return {t: self.state(t) for t in sorted(tools)}

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._open_until.clear()
            self._half_open.clear()
            self._last_error.clear()


# ---- 模块级单例（懒初始化，便于替换 db 路径做测试）----

_RECORDER: CallRecorder | None = None
_BREAKER: CircuitBreaker | None = None
_LOCK = threading.Lock()


def get_recorder() -> CallRecorder:
    global _RECORDER
    with _LOCK:
        if _RECORDER is None:
            _RECORDER = CallRecorder()
            _RECORDER.start()
        return _RECORDER


def get_breaker() -> CircuitBreaker:
    global _BREAKER
    with _LOCK:
        if _BREAKER is None:
            _BREAKER = CircuitBreaker()
        return _BREAKER


def record_tool_call(tool: str, *, agent: str = "", caller: str = "",
                     duration_ms: float = 0.0, ok: bool = True,
                     error_kind: str = "", source: str = "manifest") -> None:
    """一次调用的画像 + 熔断联合记录（调用侧唯一入口）。"""
    if os.environ.get("MCP_TELEMETRY", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    try:
        get_recorder().record(tool, agent=agent, caller=caller,
                              duration_ms=duration_ms,
                              status="ok" if ok else "error",
                              error_kind=error_kind)
        get_breaker().record(tool, ok, source=source, error=error_kind)
    except Exception:
        pass  # 画像/熔断失败绝不外溢到调用路径


def reset_for_tests(db_path: str | Path | None = None,
                    now_fn: Callable[[], float] | None = None) -> CallRecorder:
    """测试隔离：重建单例（可指定 db 路径与时间源）。"""
    global _RECORDER, _BREAKER
    with _LOCK:
        if _RECORDER is not None:
            _RECORDER.stop()
        _RECORDER = CallRecorder(db_path) if db_path else None
        _BREAKER = CircuitBreaker(now_fn=now_fn) if now_fn else CircuitBreaker()
    return _RECORDER if _RECORDER is not None else get_recorder()
