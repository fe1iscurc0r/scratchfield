"""Sentinel-Link 网关 —— 节点回传接收 / 校验 / 去重 / 重排 / 入库（卷187 B1）。

消费三种来源（与 simulator 对齐）::

    python -m mcpserver.rf_brain.sentinel_link.gateway --source tcp://127.0.0.1:48910
    python -m mcpserver.rf_brain.sentinel_link.gateway --source serial:/dev/ttyACM0
    python -m mcpserver.rf_brain.sentinel_link.gateway --source file:canary.ndjson

处理链（**降级纪律：坏帧只计数，绝不崩**）：:

    line → protocol.decode()  ──失败──→ 分类计数（bad_json/crc/unknown）丢弃
                              └─成功─→ 去重(node_id+ts+帧型) → 乱序重排 → 落库 → EventBus

落库两张表（NDJSON 展开成行）：

  - ``sentinel_scans(id, node_id, ts, freq_mhz, rssi_dbm, sf)``     每频点一行
  - ``sentinel_env(id, node_id, ts, temp_c, hum_pct, pres_hpa, bat_mv, lat, lon)``  每帧一行

同时把整帧原始 JSON 存 ``sentinel_frames`` 便于回放排查。

去重口径：**同 (node_id, ts, 帧型) 视为重复**（simulator --chaos 的重复帧即此形态），
用内存 LRU 窗口 + 表唯一索引双保险。
乱序：同 node 的帧按 ts 排序后再入库；缓存上限 ``reorder_window``，超限强制刷出。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .protocol import EnvSample, ScanBin, decode, parse_scan_config

__all__ = ["GatewayStats", "SentinelGateway", "SqliteSink", "main"]

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]        # scratchpad/
_DB_ENV = "SENTINEL_LINK_DB"
_DEFAULT_DB = "sentinel_link.db"
_OFFLINE_AFTER_S = 60.0        # 心跳超时判离线（验收项 5）

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sentinel_scans (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id  TEXT    NOT NULL,
    ts       REAL    NOT NULL,
    freq_mhz REAL    NOT NULL,
    rssi_dbm REAL    NOT NULL,
    sf       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scans_node_ts ON sentinel_scans(node_id, ts);

CREATE TABLE IF NOT EXISTS sentinel_env (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id  TEXT    NOT NULL,
    ts       REAL    NOT NULL,
    temp_c   REAL,
    hum_pct  REAL,
    pres_hpa REAL,
    bat_mv   INTEGER,
    lat      REAL,
    lon      REAL
);
CREATE INDEX IF NOT EXISTS idx_env_node_ts ON sentinel_env(node_id, ts);

CREATE TABLE IF NOT EXISTS sentinel_frames (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    ftype     TEXT    NOT NULL,
    raw_json  TEXT    NOT NULL,
    UNIQUE(node_id, ts, ftype)
);

CREATE TABLE IF NOT EXISTS sentinel_nodes (
    node_id   TEXT PRIMARY KEY,
    last_seen REAL NOT NULL,
    fw        TEXT,
    n_frames  INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> float:
    return time.time()


def _utc_iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


# ── 统计 ─────────────────────────────────────────────────────────────────

@dataclass
class GatewayStats:
    """网关处理计数（验收项 3 的"帧数/丢弃数/重复数"证据来源）。"""

    received: int = 0          # 总收行数
    ok: int = 0                # 成功解析并入库
    dropped_bad_json: int = 0
    dropped_crc: int = 0
    dropped_unknown_type: int = 0
    dropped_other: int = 0
    duplicate: int = 0
    reordered: int = 0         # 因乱序被延迟排序的帧数
    scans_rows: int = 0        # 写入 sentinel_scans 的行数
    env_rows: int = 0
    hello: int = 0
    occupation_events: int = 0 # 发出的 sentinel.occupation 事件数

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)

    def summary(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)


# ── SQLite sink ──────────────────────────────────────────────────────────

class SqliteSink:
    """落库：三张表（scans / env / frames）+ nodes 心跳表。

    线程安全：单连接 + 锁（网关本身单线程消费，锁留给外部多线程调用）。
    """

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get(_DB_ENV) or str(_REPO_ROOT / _DEFAULT_DB)
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=20000")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def frame_exists(self, node_id: str, ts: float, ftype: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM sentinel_frames WHERE node_id=? AND ts=? AND ftype=? LIMIT 1",
                (node_id, ts, ftype))
            return cur.fetchone() is not None

    def write_scan(self, node_id: str, ts: float, bins: list[ScanBin],
                   env: EnvSample | None) -> None:
        """写一帧 scan：频点入 scans 表，env 入 env 表。"""
        with self._lock:
            self._conn.executemany(
                "INSERT INTO sentinel_scans(node_id, ts, freq_mhz, rssi_dbm, sf)"
                " VALUES(?,?,?,?,?)",
                [(node_id, ts, b.freq_mhz, b.rssi_dbm, b.sf) for b in bins])
            if env is not None:
                e = env
                if any(v is not None for v in
                       (e.temp_c, e.hum_pct, e.pres_hpa, e.bat_mv, e.lat, e.lon)):
                    self._conn.execute(
                        "INSERT INTO sentinel_env(node_id, ts, temp_c, hum_pct,"
                        " pres_hpa, bat_mv, lat, lon) VALUES(?,?,?,?,?,?,?,?)",
                        (node_id, ts, e.temp_c, e.hum_pct, e.pres_hpa,
                         e.bat_mv, e.lat, e.lon))
            self._conn.commit()

    def write_env(self, node_id: str, ts: float, env: EnvSample) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO sentinel_env(node_id, ts, temp_c, hum_pct,"
                " pres_hpa, bat_mv, lat, lon) VALUES(?,?,?,?,?,?,?,?)",
                (node_id, ts, env.temp_c, env.hum_pct, env.pres_hpa,
                 env.bat_mv, env.lat, env.lon))
            self._conn.commit()

    def write_frame(self, node_id: str, ts: float, ftype: str, raw: str) -> bool:
        """写 frames 表（唯一索引兜底去重）。返回 True=新插入，False=已存在。"""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO sentinel_frames(node_id, ts, ftype, raw_json)"
                    " VALUES(?,?,?,?)", (node_id, ts, ftype, raw))
            except sqlite3.IntegrityError:
                return False
            self._conn.commit()
            return True

    def touch_node(self, node_id: str, ts: float, fw: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO sentinel_nodes(node_id, last_seen, fw, n_frames)"
                " VALUES(?,?,?,1)"
                " ON CONFLICT(node_id) DO UPDATE SET"
                "   last_seen=excluded.last_seen, fw=excluded.fw,"
                "   n_frames=sentinel_nodes.n_frames+1",
                (node_id, ts, fw))
            self._conn.commit()

    # ── 查询（供 API / 测试）──
    def list_nodes(self, now: float | None = None) -> list[dict[str, Any]]:
        now = _now() if now is None else now
        with self._lock:
            cur = self._conn.execute(
                "SELECT node_id, last_seen, fw, n_frames FROM sentinel_nodes"
                " ORDER BY node_id")
            rows = cur.fetchall()
        out = []
        for node_id, last_seen, fw, n in rows:
            online = (now - float(last_seen)) <= _OFFLINE_AFTER_S
            out.append({"node_id": node_id, "last_seen": float(last_seen),
                        "last_seen_iso": _utc_iso(float(last_seen)),
                        "fw": fw, "frames": int(n),
                        "online": online,
                        "age_s": round(now - float(last_seen), 1)})
        return out

    def query_spectrum(self, *, frm: float | None = None, to: float | None = None,
                       node: str | None = None, limit: int = 20000) -> list[dict[str, Any]]:
        sql = "SELECT node_id, ts, freq_mhz, rssi_dbm, sf FROM sentinel_scans WHERE 1=1"
        args: list[Any] = []
        if frm is not None:
            sql += " AND ts >= ?"; args.append(frm)
        if to is not None:
            sql += " AND ts <= ?"; args.append(to)
        if node:
            sql += " AND node_id = ?"; args.append(node)
        sql += " ORDER BY ts ASC, freq_mhz ASC LIMIT ?"; args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [{"node_id": r[0], "ts": r[1], "freq_mhz": r[2],
                 "rssi_dbm": r[3], "sf": r[4]} for r in rows]

    def query_env(self, *, node: str | None = None, hours: float = 24.0,
                  limit: int = 20000) -> list[dict[str, Any]]:
        since = _now() - hours * 3600.0
        sql = ("SELECT node_id, ts, temp_c, hum_pct, pres_hpa, bat_mv, lat, lon"
               " FROM sentinel_env WHERE ts >= ?")
        args: list[Any] = [since]
        if node:
            sql += " AND node_id = ?"; args.append(node)
        sql += " ORDER BY ts ASC LIMIT ?"; args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [{"node_id": r[0], "ts": r[1], "temp_c": r[2], "hum_pct": r[3],
                 "pres_hpa": r[4], "bat_mv": r[5], "lat": r[6], "lon": r[7]}
                for r in rows]


# ── 网关主体 ─────────────────────────────────────────────────────────────

class SentinelGateway:
    """消费帧流 → 校验/去重/重排 → 落库 → EventBus。

    :param sink: SqliteSink（可注入内存库做测试）
    :param emit: 事件发射回调 `(topic, payload) -> None`；缺省用 Lumo EventBus
    :param dedup_window: 内存去重窗口条数
    :param reorder_window: 乱序缓存上限（超过按 ts 强制刷出）
    """

    def __init__(self, sink: SqliteSink, *,
                 emit: Callable[[str, dict[str, Any]], None] | None = None,
                 dedup_window: int = 4096,
                 reorder_window: int = 64) -> None:
        self.sink = sink
        self._emit_fn = emit
        self.stats = GatewayStats()
        self._dedup: OrderedDict[tuple[str, float, str], None] = OrderedDict()
        self._dedup_max = dedup_window
        self._pending: dict[str, list[tuple[float, str, dict[str, Any]]]] = {}
        self._reorder_max = reorder_window
        # 占用检测（任务 D 钩子，默认开启）
        self._occupation = None

    # ── 事件发射 ──
    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        if self._emit_fn is not None:
            self._emit_fn(topic, payload)
            return
        try:
            from apiserver.event_bus import get_bus
            get_bus().emit(topic, payload)
        except Exception as e:                      # noqa: BLE001 - 事件失败不影响入库
            logger.debug("[gateway] EventBus 发射失败（忽略）: %s", e)

    # ── 去重 ──
    def _is_duplicate(self, node_id: str, ts: float, ftype: str) -> bool:
        key = (node_id, round(float(ts), 3), ftype)
        if key in self._dedup:
            self.stats.duplicate += 1
            return True
        self._dedup[key] = None
        if len(self._dedup) > self._dedup_max:
            self._dedup.popitem(last=False)
        return False

    # ── 单行消费（核心）──
    def consume_line(self, line: str, now: float | None = None) -> dict[str, Any] | None:
        """消费一行 NDJSON。**永不抛异常**；返回入库的帧 dict 或 None。"""
        now = _now() if now is None else now
        self.stats.received += 1

        frame, err = decode(line)
        if frame is None:
            low = err.lower()
            if "json" in low:
                self.stats.dropped_bad_json += 1
            elif "crc" in low:
                self.stats.dropped_crc += 1
            elif "未知帧类型" in err:
                self.stats.dropped_unknown_type += 1
            else:
                self.stats.dropped_other += 1
            return None

        node_id = frame["node_id"]
        ts = float(frame["ts"])
        ftype = frame["t"]

        # 去重：内存窗口 + 表级唯一索引双保险（跨进程重启后内存窗口已空）。
        # 两条路径都要计数，避免"表命中但 duplicate 不涨"的统计黑洞。
        if self._is_duplicate(node_id, ts, ftype):
            return None
        if self.sink.frame_exists(node_id, ts, ftype):
            self.stats.duplicate += 1
            return None

        if not self.sink.write_frame(node_id, ts, ftype, line):
            self.stats.duplicate += 1
            return None

        self._apply_frame(frame, now)
        self.stats.ok += 1
        self.sink.touch_node(node_id, ts, frame.get("fw") or "")
        return frame

    def _apply_frame(self, frame: dict[str, Any], now: float) -> None:
        """把已确立的帧写入 scans/env 表并发事件。"""
        node_id, ts, ftype = frame["node_id"], float(frame["ts"]), frame["t"]
        payload = frame["payload"]

        if ftype == "scan":
            bins: list[ScanBin] = []
            for raw in payload.get("rssi_scan") or []:
                try:
                    bins.append(ScanBin.from_dict(raw))
                except Exception as e:              # noqa: BLE001 - 单点坏不废整帧
                    logger.debug("[gateway] 跳过坏频点: %s", e)
            env = None
            if payload.get("env"):
                try:
                    env = EnvSample.from_dict(payload["env"])
                except Exception as e:              # noqa: BLE001
                    logger.debug("[gateway] 跳过坏 env: %s", e)
                    env = None
            if bins:
                # 乱序处理：与同节点最近帧比较，若 ts 落后则计数
                hist = self._pending.get(node_id) or []
                if hist and ts < max(h[0] for h in hist):
                    self.stats.reordered += 1
                self.sink.write_scan(node_id, ts, bins, env)
                self.stats.scans_rows += len(bins)
                if env is not None:
                    self.stats.env_rows += 1
                self._feed_occupation(node_id, ts, bins)
                self._emit("lumo.sentinel.scan", {
                    "node_id": node_id, "ts": ts,
                    "n_bins": len(bins),
                    "peak_dbm": max((b.rssi_dbm for b in bins),
                                    default=None),
                    "event": payload.get("event"),
                    "ts_iso": _utc_iso(ts),
                })
            self._push_pending(node_id, ts, frame)

        elif ftype == "env":
            env = None
            if payload.get("env"):
                try:
                    env = EnvSample.from_dict(payload["env"])
                except Exception as e:              # noqa: BLE001
                    logger.debug("[gateway] 跳过坏 env: %s", e)
            if env is not None:
                self.sink.write_env(node_id, ts, env)
                self.stats.env_rows += 1
                self._emit("lumo.sentinel.env", {
                    "node_id": node_id, "ts": ts, "ts_iso": _utc_iso(ts),
                    "env": env.to_dict(),
                })

        elif ftype == "hello":
            self.stats.hello += 1
            self._emit("lumo.sentinel.node_online", {
                "node_id": node_id, "ts": ts, "fw": frame.get("fw"),
                "caps": payload.get("caps") or {}, "ts_iso": _utc_iso(ts),
            })

    def _push_pending(self, node_id: str, ts: float,
                      frame: dict[str, Any]) -> None:
        """维护乱序窗口（仅用 ts 单调性做统计，超限清空）。"""
        hist = self._pending.setdefault(node_id, [])
        hist.append((ts, frame.get("fw") or "", frame))
        if len(hist) > self._reorder_max:
            del hist[:len(hist) - self._reorder_max]

    def _feed_occupation(self, node_id: str, ts: float,
                         bins: list[ScanBin]) -> None:
        """把帧喂给占用检测器（任务 D）。检测器缺失时静默跳过。"""
        if self._occupation is None:
            try:
                from .occupation import get_detector
                self._occupation = get_detector()
            except Exception:                       # noqa: BLE001
                return
        try:
            events = self._occupation.feed(node_id, ts, bins)
        except Exception as e:                      # noqa: BLE001
            logger.debug("[gateway] 占用检测异常（忽略）: %s", e)
            return
        for ev in events:
            self.stats.occupation_events += 1
            self._emit("lumo.sentinel.occupation", ev)
            logger.info("[gateway] 占用事件 %s @ %.3fMHz 持续 %.1fs",
                        node_id, ev.get("freq_mhz", 0.0), ev.get("duration_s", 0.0))

    # ── 批量消费 ──
    def consume_lines(self, lines: Iterable[str], now: float | None = None) -> GatewayStats:
        for line in lines:
            self.consume_line(line, now=now)
        return self.stats


# ── 来源适配器 ───────────────────────────────────────────────────────────

def iter_lines_from_source(source: str, *,
                           reconnect_s: float = 2.0,
                           stop_after: float | None = None) -> Iterator[str]:
    """把 `--source` 规格转成行迭代器。

    规格：``tcp://host:port`` / ``serial:PORT`` / ``file:path``
    """
    if source.startswith("tcp://"):
        yield from _iter_tcp(source[len("tcp://"):], reconnect_s=reconnect_s,
                             stop_after=stop_after)
    elif source.startswith("serial:"):
        yield from _iter_serial(source[len("serial:"):], stop_after=stop_after)
    elif source.startswith("file:"):
        yield from _iter_file(source[len("file:"):])
    else:
        raise ValueError(f"未知 source 规格: {source!r}"
                         "（应为 tcp://host:port | serial:PORT | file:path）")


def _iter_file(path: str) -> Iterator[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield line


def _iter_tcp(hostport: str, *, reconnect_s: float,
              stop_after: float | None) -> Iterator[str]:
    import socket
    host, _, port_s = hostport.partition(":")
    port = int(port_s or 48910)
    t0 = time.time()
    while True:
        if stop_after is not None and time.time() - t0 >= stop_after:
            return
        try:
            with socket.create_connection((host, port), timeout=5.0) as sk:
                sk.settimeout(1.0)
                buf = b""
                print(f"[gateway] 已连接 {host}:{port}", file=sys.stderr, flush=True)
                while True:
                    if stop_after is not None and time.time() - t0 >= stop_after:
                        return
                    try:
                        chunk = sk.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        raw, _, buf = buf.partition(b"\n")
                        line = raw.decode("utf-8", errors="replace").strip()
                        if line:
                            yield line
        except OSError as e:
            print(f"[gateway] TCP 连接失败（{e}），{reconnect_s}s 后重试",
                  file=sys.stderr, flush=True)
            time.sleep(reconnect_s)


def _iter_serial(port: str, *, stop_after: float | None) -> Iterator[str]:
    try:
        import serial  # type: ignore
    except ImportError as e:
        raise RuntimeError("serial 模式需要 pyserial：pip install pyserial") from e
    baud = int(os.environ.get("SENTINEL_SERIAL_BAUD", "115200"))
    t0 = time.time()
    with serial.Serial(port, baud, timeout=1.0) as sp:
        print(f"[gateway] 已打开串口 {port}@{baud}", file=sys.stderr, flush=True)
        while True:
            if stop_after is not None and time.time() - t0 >= stop_after:
                return
            raw = sp.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                yield line


# ── CLI ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gateway",
        description="Sentinel-Link 网关：收帧 → 校验/去重/入库 → EventBus",
    )
    p.add_argument("--source", required=True,
                   help="tcp://host:port | serial:PORT | file:path")
    p.add_argument("--db", default=None,
                   help=f"SQLite 路径（缺省 $SENTINEL_LINK_DB 或 {_DEFAULT_DB}）")
    p.add_argument("--duration", type=float, default=None,
                   help="跑满 N 秒后退出（缺省一直跑）")
    p.add_argument("--quiet", action="store_true", help="不打印收尾统计")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    sink = SqliteSink(args.db)
    gw = SentinelGateway(sink)
    print(f"[gateway] 库={sink.db_path} 来源={args.source}", file=sys.stderr, flush=True)
    try:
        for line in iter_lines_from_source(args.source, stop_after=args.duration):
            gw.consume_line(line)
    except KeyboardInterrupt:
        print("\n[gateway] 收到中断，退出", file=sys.stderr, flush=True)
    finally:
        sink.close()
    if not args.quiet:
        print(f"[gateway] 统计: {gw.stats.summary()}", file=sys.stderr)
    return 0


if __name__ == "__main__":                    # pragma: no cover
    raise SystemExit(main())
