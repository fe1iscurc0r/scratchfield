"""sentinel_bridge.py — 边缘频谱哨兵串口桥 + 记忆入库（N-04）。

职责：
1. 串口读取：ESP32-S3 USB-CDC NDJSON 行（pyserial，dev 路径/波特率走环境变量，
   无设备时 mock 模式可跑）。
2. 解析 NDJSON → schema 校验（SentinelReport，见 schemas.py）→ 写入 SQLite 记忆库。
3. MCP 桥：sentinel_ingest（收一条）/ sentinel_status（最近 N 条）/
   sentinel_query（按协议/id 查）。

降级纪律：坏 JSON / 未知协议 / 缺字段 → 跳过并计数，不抛异常、不崩（串口流
不能因为一条坏行停摆）。查询/状态参数错误才 fail-fast（照 sentinel_intel 范式）。

结构照 mcpserver/sentinel_intel/（SPEC-09 K 线）：agent-manifest.json entryPoint
→ SentinelBridge 类 → handle_handoff 分发。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mcpserver.rf_brain.schemas import SentinelReport

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]   # scratchpad/
_DEFAULT_DB_ENV = "SENTINEL_DB"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sentinel_reading (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    protocol    TEXT NOT NULL,
    id          INTEGER NOT NULL,
    channel     TEXT,
    temperature REAL,
    humidity    INTEGER,
    battery     TEXT,
    cmd         INTEGER,
    rssi_dbm    INTEGER,
    crc_ok      INTEGER,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sentinel_proto_id ON sentinel_reading(protocol, id);
CREATE INDEX IF NOT EXISTS idx_sentinel_seq ON sentinel_reading(seq);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SentinelBridgeError(RuntimeError):
    """哨兵桥参数错误（fail-fast，不静默空返回）。"""


# --------------------------------------------------------------------------- #
# SQLite 记忆库
# --------------------------------------------------------------------------- #

class SentinelStore:
    """哨兵上报记忆库：单表时间序列（无重依赖，纯 sqlite3）。"""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        path = Path(db_path)
        if path != Path(":memory:"):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def ingest(self, report: SentinelReport, ts: str | None = None) -> int:
        """写入一条上报，返回自增 seq。"""
        channel = None if report.channel is None else str(report.channel)
        crc = None if report.crc_ok is None else (1 if report.crc_ok else 0)
        cur = self.conn.execute(
            "INSERT INTO sentinel_reading "
            "(ts, protocol, id, channel, temperature, humidity, battery, cmd, "
            " rssi_dbm, crc_ok, raw_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts or _now_iso(), report.protocol, report.id, channel,
             report.temperature, report.humidity, report.battery, report.cmd,
             report.rssi_dbm, crc,
             json.dumps(report.as_dict(), ensure_ascii=False)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _rows_to_dicts(self, rows) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in rows:
            d = json.loads(r["raw_json"])
            d["seq"] = r["seq"]
            d["ts"] = r["ts"]
            out.append(d)
        return out

    def query(self, protocol: str | None = None, sensor_id: int | None = None,
              limit: int = 100) -> list[dict[str, Any]]:
        """按协议/传感器 id 查询（均省略 = 全部），新→旧。"""
        sql = "SELECT * FROM sentinel_reading"
        conds: list[str] = []
        args: list[Any] = []
        if protocol is not None:
            conds.append("protocol=?")
            args.append(protocol)
        if sensor_id is not None:
            conds.append("id=?")
            args.append(sensor_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY seq DESC LIMIT ?"
        args.append(int(limit))
        return self._rows_to_dicts(self.conn.execute(sql, args).fetchall())

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """最近 N 条（status 用）。"""
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM sentinel_reading ORDER BY seq DESC LIMIT ?",
            (int(limit),)).fetchall())

    def count(self, protocol: str | None = None) -> int:
        if protocol is None:
            return int(self.conn.execute(
                "SELECT COUNT(*) FROM sentinel_reading").fetchone()[0])
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM sentinel_reading WHERE protocol=?",
            (protocol,)).fetchone()[0])


# --------------------------------------------------------------------------- #
# 进程内单例（测试 fresh=True 换独立实例）
# --------------------------------------------------------------------------- #

_STORE: SentinelStore | None = None
_STORE_LOCK = threading.Lock()


def get_store(db_path: str | None = None, fresh: bool = False) -> SentinelStore:
    global _STORE
    with _STORE_LOCK:
        if fresh and _STORE is not None:
            _STORE.close()
            _STORE = None
        if _STORE is None:
            path = db_path or os.environ.get(_DEFAULT_DB_ENV,
                                             str(_REPO_ROOT / "sentinel_rf.db"))
            _STORE = SentinelStore(path)
        return _STORE


def reset_store() -> None:
    global _STORE
    with _STORE_LOCK:
        if _STORE is not None:
            _STORE.close()
        _STORE = None


# --------------------------------------------------------------------------- #
# 串口读取（pyserial 懒加载，无设备 = mock 模式）
# --------------------------------------------------------------------------- #

def open_serial():
    """按环境变量打开串口；未配置则返回 None（mock 模式）。

    SENTINEL_SERIAL_PORT（如 COM3 或 /dev/ttyACM0）；SENTINEL_SERIAL_BAUD（默认 115200）。
    """
    port = os.environ.get("SENTINEL_SERIAL_PORT", "").strip()
    if not port:
        return None
    import serial  # 懒加载：仅真机串口路径需要 pyserial
    baud = int(os.environ.get("SENTINEL_SERIAL_BAUD", "115200"))
    return serial.Serial(port, baud, timeout=1)


# --------------------------------------------------------------------------- #
# MCP 桥
# --------------------------------------------------------------------------- #

class SentinelBridge:
    """边缘频谱哨兵记忆 MCP 服务实例。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            result = self._dispatch(tool_name, params)
        except SentinelBridgeError as e:
            logger.warning("[sentinel] %s 失败: %s", tool_name, e)
            return json.dumps({"status": "error", "service": "sentinel",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        except Exception as e:
            logger.exception("[sentinel] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "sentinel",
                               "tool": tool_name, "error": f"未预期异常: {e}"},
                              ensure_ascii=False)
        return json.dumps({"status": "ok", "service": "sentinel",
                           "tool": tool_name, "result": result},
                          ensure_ascii=False)

    def _dispatch(self, tool_name: str, p: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "sentinel_ingest":
            return self._ingest(p)
        if tool_name == "sentinel_status":
            return self._status(p)
        if tool_name == "sentinel_query":
            return self._query(p)
        raise SentinelBridgeError(
            f"sentinel 不支持的工具: {tool_name!r}（可用: sentinel_ingest/"
            "sentinel_status/sentinel_query）")

    # ------------------------------------------------------------ 工具实现

    def ingest_line(self, line: str) -> dict[str, Any]:
        """单行入库：坏 JSON/未知协议/缺字段降级返回 ok=False，不抛异常。"""
        if not isinstance(line, str):
            return {"ok": False, "skipped": 1, "error": "line 必须是字符串"}
        try:
            report = SentinelReport.from_ndjson(line)
        except ValueError as e:
            return {"ok": False, "skipped": 1, "error": str(e)}
        seq = get_store().ingest(report)
        return {"ok": True, "stored": 1, "seq": seq,
                "total": get_store().count()}

    def pump(self, lines: Iterable[str]) -> dict[str, Any]:
        """从行迭代器（mock 串口 / 真串口 readline）批量入库，坏行计数跳过。"""
        ok = bad = 0
        for line in lines:
            if line is None:
                continue
            r = self.ingest_line(line)
            if r["ok"]:
                ok += 1
            else:
                bad += 1
        return {"ok": ok, "bad": bad, "total": get_store().count()}

    def _ingest(self, p: dict[str, Any]) -> dict[str, Any]:
        line = p.get("line") or p.get("ndjson")
        if line is None and isinstance(p.get("data"), dict):
            line = json.dumps(p["data"], ensure_ascii=False)
        if not isinstance(line, str):
            raise SentinelBridgeError(
                "sentinel_ingest 需要 line(NDJSON 字符串) 或 data(对象)")
        return self.ingest_line(line)

    def _status(self, p: dict[str, Any]) -> dict[str, Any]:
        limit = int(p.get("limit", 10))
        store = get_store()
        return {"count": store.count(), "readings": store.recent(limit)}

    def _query(self, p: dict[str, Any]) -> dict[str, Any]:
        protocol = p.get("protocol")
        sensor_id = p.get("id")
        limit = int(p.get("limit", 100))
        if protocol is not None and protocol not in SentinelReport.VALID_PROTOCOLS:
            raise SentinelBridgeError(f"未知协议: {protocol!r}")
        rows = get_store().query(protocol=protocol, sensor_id=sensor_id,
                                 limit=limit)
        return {"count": len(rows), "readings": rows}
