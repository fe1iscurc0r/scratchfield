"""哨兵网格 · 云服串口桥 + rf_brain 记忆入库（N-04）

职责：收 ESP32 哨兵节点（N-03 固件）经 USB-CDC 串口上报的 NDJSON 行，
校验字段 → 写入本地 SQLite 记忆（sentinel_events 表）→ 供查询工具消费。

设计纪律：
- pyserial 是**可选依赖**：无设备 / 未装 serial 时走 mock 模式（feed_line
  手动喂数据），不 import serial 也能跑——云服无真机照样验收。
- 存储用标准库 sqlite3，不引入新重依赖；不碰 NEKO/apiserver 主流程。
- 串口设备路径 / 波特率 / DB 路径全部走环境变量，不硬编码。

NDJSON 行格式（与 N-03 固件约定）：
    {"src":"sentinel","protocol":"acurite-tower","id":4660,"channel":"C",
     "temperature_c":25.0,"humidity_pct":50,"battery":"OK","rssi_dbm":-85.0}
坏 JSON / 未知协议 / 缺 src 字段 → 降级为 failed 记录，不抛异常、不中断。
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# 环境变量配置（不硬编码）
_DB_PATH = os.environ.get("SENTINEL_DB_PATH", "")
_SERIAL_PORT = os.environ.get("SENTINEL_SERIAL_PORT", "")
_SERIAL_BAUD = int(os.environ.get("SENTINEL_SERIAL_BAUD", "115200"))

_KNOWN_PROTOCOLS = {
    "acurite-tower", "acurite-515", "lacrosse-tx141th-bv2",
    "acurite-5n1", "acurite-atlas",  # 未来协议预留
}

_lock = threading.Lock()  # sqlite 单写连接，串口/HTTP 多线程下防竞争


def _default_db() -> Path:
    """DB 路径：环境变量优先，否则放 rf_brain 包目录下。"""
    if _DB_PATH:
        return Path(_DB_PATH)
    return Path(__file__).resolve().parent / "sentinel_events.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentinel_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            protocol TEXT NOT NULL,
            device_id INTEGER,
            channel TEXT,
            temperature_c REAL,
            humidity_pct INTEGER,
            temperature_f REAL,
            battery TEXT,
            rssi_dbm REAL,
            raw_json TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


@dataclass
class IngestResult:
    status: str                       # "ok" / "failed"
    protocol: str | None = None
    device_id: int | None = None
    reason: str = ""


def ingest(line: str, db_path: Path | None = None) -> IngestResult:
    """收一条 NDJSON 行 → 校验 → 入库。坏数据降级为 failed 记录。"""
    db = db_path or _default_db()
    ts = datetime.now(timezone.utc).isoformat()
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        _record_failed(db, ts, line, f"bad json: {e}")
        return IngestResult(status="failed", reason=f"bad json: {e}")

    if not isinstance(obj, dict) or obj.get("src") != "sentinel":
        _record_failed(db, ts, line, "missing src=sentinel")
        return IngestResult(status="failed", reason="missing src=sentinel")

    protocol = obj.get("protocol", "")
    if protocol not in _KNOWN_PROTOCOLS:
        _record_failed(db, ts, line, f"unknown protocol: {protocol}")
        return IngestResult(status="failed", reason=f"unknown protocol: {protocol}")

    with _lock:
        conn = _connect(db)
        conn.execute(
            "INSERT INTO sentinel_events "
            "(ts, protocol, device_id, channel, temperature_c, humidity_pct, "
            " temperature_f, battery, rssi_dbm, raw_json, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts, protocol,
                obj.get("id"), obj.get("channel"),
                obj.get("temperature_c"), obj.get("humidity_pct"),
                obj.get("temperature_f"), obj.get("battery"),
                obj.get("rssi_dbm"), line, "ok",
            ),
        )
        conn.commit()
        conn.close()
    return IngestResult(status="ok", protocol=protocol, device_id=obj.get("id"))


def _record_failed(db: Path, ts: str, raw: str, reason: str) -> None:
    with _lock:
        conn = _connect(db)
        conn.execute(
            "INSERT INTO sentinel_events (ts, protocol, raw_json, status) "
            "VALUES (?,?,?,?)",
            (ts, "", raw, f"failed: {reason}"),
        )
        conn.commit()
        conn.close()


def status(n: int = 10, db_path: Path | None = None) -> list[dict]:
    """最近 n 条事件（含 failed）。"""
    db = db_path or _default_db()
    conn = _connect(db)
    rows = conn.execute(
        "SELECT ts, protocol, device_id, temperature_c, humidity_pct, rssi_dbm, "
        "status FROM sentinel_events ORDER BY id DESC LIMIT ?", (n,),
    ).fetchall()
    conn.close()
    return [
        {"ts": r[0], "protocol": r[1], "device_id": r[2],
         "temperature_c": r[3], "humidity_pct": r[4], "rssi_dbm": r[5], "status": r[6]}
        for r in rows
    ]


def query(protocol: str | None = None, device_id: int | None = None,
          db_path: Path | None = None) -> list[dict]:
    """按协议 / 设备 ID 查事件。"""
    db = db_path or _default_db()
    conn = _connect(db)
    sql = "SELECT ts, protocol, device_id, temperature_c, humidity_pct, status FROM sentinel_events WHERE 1=1"
    args: list = []
    if protocol:
        sql += " AND protocol = ?"
        args.append(protocol)
    if device_id is not None:
        sql += " AND device_id = ?"
        args.append(device_id)
    sql += " ORDER BY id DESC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return [
        {"ts": r[0], "protocol": r[1], "device_id": r[2],
         "temperature_c": r[3], "humidity_pct": r[4], "status": r[5]}
        for r in rows
    ]


def read_serial_loop(db_path: Path | None = None, stop_event: threading.Event | None = None):
    """串口读取循环（真机用）：阻塞读行 → ingest。无 serial 模块则跳过。

    N-03 固件就绪后，此循环由部署脚本拉起；云服 mock 验收不依赖它。
    """
    try:
        import serial  # noqa: F401  # 可选依赖
    except ImportError:
        return  # 无真机环境，静默跳过

    import serial as pyserial
    db = db_path or _default_db()
    stop = stop_event or threading.Event()
    with pyserial.Serial(_SERIAL_PORT, _SERIAL_BAUD, timeout=1) as ser:
        buf = b""
        while not stop.is_set():
            chunk = ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    ingest(text, db)


def feed_line(line: str, db_path: Path | None = None) -> IngestResult:
    """mock 模式入口：手动喂一条 NDJSON（等价串口读到一行）。"""
    return ingest(line, db_path)
