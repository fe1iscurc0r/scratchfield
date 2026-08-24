"""hamlog_adapter — 陆墨的 QSO/QSL 工具桥。

把本地 HamLog（业余无线电电台日志）的数据封装成 5 个 MCP 工具：
hamlog_qso_search / hamlog_qsl_debts / hamlog_qso_add / hamlog_qsl_update / hamlog_card_content。

数据源（2026-08-18 按 HamLog R1.0.0 实际仓库对齐后的双后端设计）：
1. SQLite 直连（默认，主路径）：HamLog R1.0.0 是 PyQt6 桌面程序，没有 HTTP API，
   数据存 %APPDATA%/HamLog/Log.db（HAMLOG_DB_PATH 可覆盖）。log 表字段：
   id/Callsign/Freq/Year/Month/Day/Time/Mode/Power_self/Power_side/Rst_self/
   Rst_side/QTH/Device/QSL_RX/QSL_SEND/Remarks/CreateTime；settings 表 key-value
   （my_callsign/my_name/my_qth/my_grid 等）。QSL_SEND/QSL_RX 为 YYYYMMDD 日期串，
   空串=未发/未收（卡债判断依据）。
2. HamLog REST（legacy 兜底）：设 HAMLOG_API_URL 后回到 Flask HTTP 契约（见 git 历史，
   DEV 分支曾规划 /api/qso 等端点；实际仓库无此服务，仅保留兼容）。

两种接入方式（同一份工具实现）：
1. 进程内 manifest 接入：agent-manifest.json entryPoint → HamlogBridge，
   scan_and_register_mcp_agents 自动注册，走 handle_handoff 分发。
2. 独立进程 stdio 接入：`python adapter.py --stdio` 起最小 MCP stdio server，
   mcpserver 通过 mcporter_bridge（~/.mcporter/config.json 的 hamlog 条目，
   模板见 mcpserver/external_services.example.json）接入。

fail-fast 原则：数据库不存在（未跑过 HamLog）/ 表缺失 / 数据缺失一律抛 HamlogError，
handle_handoff 转成 {"status": "error", ...}，绝不静默返回空结果。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SQLite 后端（主路径）：HamLog R1.0.0 数据目录
_LOG_TABLE_COLUMNS = (
    "id Callsign Freq Year Month Day Time Mode Power_self Power_side "
    "Rst_self Rst_side QTH Device QSL_RX QSL_SEND Remarks CreateTime"
).split()

# HTTP 后端（legacy 兜底，仅 HAMLOG_API_URL 显式设置时启用）
DEFAULT_API_PREFIX = "/api"
REQUEST_TIMEOUT = 8  # 秒；本地回环服务，超时短一点让 fail-fast 更快


class HamlogError(RuntimeError):
    """HamLog 不可用 / 业务失败统一异常（fail-fast，不允许静默吞掉）。"""


# ---- 后端选择与 SQLite 连接 ----

def _default_db_path() -> Path:
    """HamLog R1.0.0 数据路径（与 AutoDeal.get_user_data_dir 一致）。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "~"))
    elif sys.platform == "darwin":
        base = Path("~/Library/Application Support")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share"))
    return base.expanduser() / "HamLog" / "Log.db"


def _db_path() -> Path:
    return Path(os.environ.get("HAMLOG_DB_PATH") or _default_db_path())


def _sqlite_backend() -> bool:
    """显式设置 HAMLOG_API_URL → HTTP legacy 后端；否则 SQLite 直连。"""
    return not os.environ.get("HAMLOG_API_URL")


def _connect(readonly: bool = True) -> sqlite3.Connection:
    """打开 Log.db；文件不存在即 fail-fast（说明 HamLog 从没运行过）。"""
    path = _db_path()
    if not path.exists():
        raise HamlogError(
            f"HamLog 数据库不存在（{path}）：请先在本机运行一次 HamLog 桌面程序生成日志库，"
            f"或用 HAMLOG_DB_PATH 环境变量指向已有 Log.db"
        )
    uri = f"file:{path.as_posix()}" + ("?mode=ro" if readonly else "")
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise HamlogError(f"无法打开 HamLog 数据库 {path}：{exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _require_table(conn: sqlite3.Connection, table: str) -> None:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if row is None:
        raise HamlogError(f"HamLog 数据库缺少 {table} 表：Log.db 可能不是 HamLog 生成或版本不兼容")


def _row_to_qso(row: sqlite3.Row) -> dict[str, Any]:
    """log 表行 → 归一化 QSO dict（日期拼成 YYYY-MM-DD，UTC 时间保留原样）。"""
    rec = {k: row[k] for k in row.keys()}
    date_str = ""
    if rec.get("Year") and rec.get("Month") and rec.get("Day"):
        date_str = f"{int(rec['Year']):04d}-{int(rec['Month']):02d}-{int(rec['Day']):02d}"
    return {
        "qso_id": rec["id"],
        "callsign": rec.get("Callsign") or "",
        "freq": rec.get("Freq") or "",
        "mode": rec.get("Mode") or "",
        "qso_date": date_str,
        "qso_time_utc": rec.get("Time") or "",
        "band": "",
        "power": rec.get("Power_self") or "",
        "rst_sent": rec.get("Rst_side") or "",  # HamLog 语义：Rst_side=我发给对方
        "rst_rcvd": rec.get("Rst_self") or "",  # Rst_self=对方发给我
        "qth": rec.get("QTH") or "",
        "device": rec.get("Device") or "",
        "qsl_sent_date": rec.get("QSL_SEND") or "",
        "qsl_rcvd_date": rec.get("QSL_RX") or "",
        "remarks": rec.get("Remarks") or "",
    }


_CN_DATE_RE = re.compile(r"^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*$")


def _normalize_date_str(value: str) -> str:
    """把常见口语化日期统一成可解析形式：2026年8月21日 → 2026-8-21，点号分隔 → 横线。"""
    text = str(value).strip()
    m = _CN_DATE_RE.match(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return text.replace(".", "-")


def _parse_date_arg(value: str, field: str) -> datetime:
    text = _normalize_date_str(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise HamlogError(f"{field} 日期格式无法识别: {value!r}（支持 YYYY-MM-DD / YYYYMMDD / YYYY年M月D日）")


# ---- HTTP legacy 后端（HAMLOG_API_URL 显式设置时启用） ----

def _base_url() -> str:
    return os.environ.get("HAMLOG_API_URL", "").rstrip("/")


def _api_prefix() -> str:
    return os.environ.get("HAMLOG_API_PREFIX", DEFAULT_API_PREFIX).strip() or DEFAULT_API_PREFIX


def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """发起 HamLog HTTP 请求，返回 data 字段；任何异常路径都抛 HamlogError。"""
    import requests  # 延迟导入：SQLite 主路径用不到 requests

    url = f"{_base_url()}{_api_prefix()}{path}"
    clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    try:
        resp = requests.request(
            method, url, params=clean_params, json=json_body, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        raise HamlogError(f"HamLog API 不可达（{url}）：{exc}。请确认 HamLog 已启动，或不设 HAMLOG_API_URL 走 SQLite 直连") from exc

    try:
        payload = resp.json()
    except ValueError:
        payload = None

    if resp.status_code != 200:
        detail = _extract_error_message(payload) or resp.text[:200]
        raise HamlogError(f"HamLog API 返回 HTTP {resp.status_code}（{method} {path}）：{detail}")
    if not isinstance(payload, dict):
        raise HamlogError(f"HamLog API 响应不是 JSON 对象（{method} {path}）")

    code = payload.get("code")
    if code is not None and code != 200:
        detail = _extract_error_message(payload) or "未知业务错误"
        raise HamlogError(f"HamLog 业务错误 code={code}：{detail}")

    return payload.get("data", payload)


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("message", "msg", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


# ---- 记录归一化（容忍 HamLog 字段命名差异） ----

_QSO_FIELD_ALIASES = {
    "callsign": ("callsign", "call", "their_callsign"),
    "freq": ("freq", "frequency", "freq_mhz"),
    "mode": ("mode",),
    "rst_sent": ("rst_sent", "rst_s", "report_sent"),
    "rst_rcvd": ("rst_rcvd", "rst_r", "report_received"),
    "qso_date": ("qso_date", "date", "datetime"),
    "band": ("band",),
    "power": ("power", "tx_power"),
    "qsl_status": ("qsl_status", "qsl"),
}


def _pick(record: dict[str, Any], field: str) -> Any:
    for alias in _QSO_FIELD_ALIASES.get(field, (field,)):
        if alias in record and record[alias] not in (None, ""):
            return record[alias]
    return None


def _normalize_qso(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"raw": record}
    normalized = {field: _pick(record, field) for field in _QSO_FIELD_ALIASES}
    normalized["qso_id"] = record.get("qso_id") or record.get("id")
    # 保留未映射的额外字段，避免信息丢失
    for key, value in record.items():
        if key not in normalized and value not in (None, ""):
            normalized.setdefault(key, value)
    return normalized


def _normalize_debt(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"raw": record}
    debt_type = record.get("debt_type") or record.get("type") or ""
    if debt_type not in ("i_owe", "they_owe"):
        # 兼容方向字段表达：owed=我欠的，owing=欠我的
        direction = str(record.get("direction") or "").lower()
        debt_type = "i_owe" if direction == "owed" else "they_owe" if direction == "owing" else debt_type
    status = str(record.get("status") or "pending").lower()
    if status not in ("sent", "received", "pending"):
        status = "pending"
    return {
        "callsign": record.get("callsign") or record.get("call") or "",
        "qso_date": record.get("qso_date") or record.get("date") or "",
        "band": record.get("band") or "",
        "mode": record.get("mode") or "",
        "status": status,
        "debt_type": debt_type,
    }


# ---- 5 个工具（SQLite 主路径 + HTTP legacy 兜底） ----

def qso_search(
    callsign: str = "",
    since: str = "",
    until: str = "",
    band: str = "",
    mode: str = "",
) -> list[dict[str, Any]]:
    """搜索 QSO 记录。所有条件可选，至少给一个才有意义。"""
    if _sqlite_backend():
        return _sqlite_qso_search(callsign, since, until, band, mode)
    data = _request(
        "GET",
        "/qso/search",
        params={"callsign": callsign, "since": since, "until": until, "band": band, "mode": mode},
    )
    if isinstance(data, dict):  # 容忍 {"list": [...]} 包装
        data = data.get("list") or data.get("items") or []
    if not isinstance(data, list):
        raise HamlogError(f"HamLog qso/search 返回了非列表数据: {type(data).__name__}")
    return [_normalize_qso(r) for r in data]


def _sqlite_qso_search(callsign: str, since: str, until: str, band: str, mode: str) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if str(callsign or "").strip():
        clauses.append("UPPER(Callsign) LIKE UPPER(?)")
        args.append(f"%{str(callsign).strip()}%")
    if str(since or "").strip():
        since_dt = _parse_date_arg(since, "since")
        clauses.append("(Year*10000 + Month*100 + Day) >= ?")
        args.append(since_dt.year * 10000 + since_dt.month * 100 + since_dt.day)
    if str(until or "").strip():
        until_dt = _parse_date_arg(until, "until")
        clauses.append("(Year*10000 + Month*100 + Day) <= ?")
        args.append(until_dt.year * 10000 + until_dt.month * 100 + until_dt.day)
    if str(mode or "").strip():
        clauses.append("UPPER(Mode) = UPPER(?)")
        args.append(str(mode).strip())
    if str(band or "").strip():  # HamLog 无 band 字段：按频率前缀近似匹配（fail-fast 提示）
        band = str(band).strip().lower()
        _BAND_FREQ_PREFIX = {"160m": "1.8", "80m": "3.5", "40m": "7", "30m": "10", "20m": "14", "17m": "18", "15m": "21", "12m": "24", "10m": "28", "6m": "50", "2m": "144", "70cm": "43"}
        prefix = _BAND_FREQ_PREFIX.get(band)
        if prefix is None:
            raise HamlogError(f"HamLog 无独立 band 字段，无法按波段 {band!r} 过滤（支持 {_BAND_FREQ_PREFIX.keys()}），请改用频率前缀搜 callsign=或去掉该条件")
        clauses.append("Freq LIKE ?")
        args.append(f"{prefix}%")
    sql = "SELECT * FROM log"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY Year DESC, Month DESC, Day DESC, Time DESC LIMIT 200"
    conn = _connect(readonly=True)
    try:
        _require_table(conn, "log")
        rows = conn.execute(sql, args).fetchall()
    except sqlite3.Error as exc:
        raise HamlogError(f"HamLog 日志查询失败: {exc}") from exc
    finally:
        conn.close()
    return [_row_to_qso(r) for r in rows]


def qsl_debts(direction: str = "all") -> list[dict[str, Any]]:
    """QSL 卡债清单。direction: owed=我欠的 / owing=欠我的 / all=全部。"""
    direction = str(direction or "all").strip().lower()
    if direction not in ("owed", "owing", "all"):
        raise HamlogError(f"direction 只能是 owed/owing/all，收到: {direction!r}")
    if _sqlite_backend():
        return _sqlite_qsl_debts(direction)
    data = _request("GET", "/qsl/debts", params={"direction": direction})
    if isinstance(data, dict):
        data = data.get("list") or data.get("items") or []
    if not isinstance(data, list):
        raise HamlogError(f"HamLog qsl/debts 返回了非列表数据: {type(data).__name__}")
    debts = [_normalize_debt(r) for r in data]
    if direction != "all":  # 双重保险：HamLog 没过滤干净时本地兜底
        expected = "i_owe" if direction == "owed" else "they_owe"
        debts = [d for d in debts if d.get("debt_type") == expected]
    return debts


def _sqlite_qsl_debts(direction: str) -> list[dict[str, Any]]:
    """卡债语义：QSL_SEND 空=我还没发（i_owe）；QSL_RX 空=对方还没回卡（they_owe）。"""
    conn = _connect(readonly=True)
    try:
        _require_table(conn, "log")
        debts: list[dict[str, Any]] = []
        if direction in ("owed", "all"):
            for r in conn.execute("SELECT * FROM log WHERE COALESCE(QSL_SEND,'')='' ORDER BY Year, Month, Day, Time"):
                q = _row_to_qso(r)
                debts.append({"callsign": q["callsign"], "qso_date": q["qso_date"], "band": "", "mode": q["mode"], "status": "pending", "debt_type": "i_owe", "qso_id": q["qso_id"]})
        if direction in ("owing", "all"):
            for r in conn.execute("SELECT * FROM log WHERE COALESCE(QSL_RX,'')='' ORDER BY Year, Month, Day, Time"):
                q = _row_to_qso(r)
                debts.append({"callsign": q["callsign"], "qso_date": q["qso_date"], "band": "", "mode": q["mode"], "status": "pending", "debt_type": "they_owe", "qso_id": q["qso_id"]})
        return debts
    except sqlite3.Error as exc:
        raise HamlogError(f"HamLog 卡债查询失败: {exc}") from exc
    finally:
        conn.close()


def _alias_input_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """按 _QSO_FIELD_ALIASES 归一化输入字段（容忍 LLM 用 call/date 等别名），其余字段原样透传。"""
    out: dict[str, Any] = {}
    for field, aliases in _QSO_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in fields and str(fields[alias]).strip():
                out[field] = fields[alias]
                break
    for key, value in fields.items():
        if key not in out and value not in (None, ""):
            out.setdefault(key, value)
    return out


def qso_add(**fields: Any) -> dict[str, Any]:
    """新增一条 QSO。必需字段：callsign/mode；qso_date 缺省取当天（UTC）。"""
    fields = _alias_input_fields(fields)
    if not str(fields.get("qso_date") or "").strip():
        fields["qso_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    required = ("callsign", "mode")
    missing = [f for f in required if not str(fields.get(f) or "").strip()]
    if missing:
        raise HamlogError(f"qso_add 缺少必需字段: {', '.join(missing)}（qso_date 不填默认当天 UTC）")
    if _sqlite_backend():
        return _sqlite_qso_add(fields)
    data = _request("POST", "/qso", json_body={k: v for k, v in fields.items() if v is not None})
    qso_id = None
    if isinstance(data, dict):
        qso_id = data.get("qso_id") or data.get("id")
    return {"success": True, "qso_id": qso_id}


def _sqlite_qso_add(fields: dict[str, Any]) -> dict[str, Any]:
    qso_dt = _parse_date_arg(fields["qso_date"], "qso_date")
    row = {
        "Callsign": str(fields["callsign"]).strip().upper(),
        "Freq": str(fields.get("freq") or "").strip(),
        "Year": qso_dt.year,
        "Month": qso_dt.month,
        "Day": qso_dt.day,
        "Time": str(fields.get("qso_time_utc") or fields.get("time") or "").strip(),
        "Mode": str(fields["mode"]).strip().upper(),
        "Power_self": str(fields.get("power") or "5W").strip(),
        "Power_side": str(fields.get("power_side") or "").strip(),
        "Rst_self": str(fields.get("rst_rcvd") or "59").strip(),
        "Rst_side": str(fields.get("rst_sent") or "59").strip(),
        "QTH": str(fields.get("qth") or "").strip(),
        "Device": str(fields.get("device") or "").strip(),
        "QSL_RX": str(fields.get("qsl_rcvd_date") or "").strip(),
        "QSL_SEND": str(fields.get("qsl_sent_date") or "").strip(),
        "Remarks": str(fields.get("remarks") or "").strip(),
    }
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn = _connect(readonly=False)
    try:
        _require_table(conn, "log")
        cur = conn.execute(f"INSERT INTO log ({columns}) VALUES ({placeholders})", tuple(row.values()))
        conn.commit()
        return {"success": True, "qso_id": cur.lastrowid}
    except sqlite3.Error as exc:
        raise HamlogError(f"HamLog 写入 QSO 失败: {exc}") from exc
    finally:
        conn.close()


def qsl_update(
    qso_id: int,
    status: str,
    sent_date: str = "",
    received_date: str = "",
) -> dict[str, Any]:
    """更新某条 QSO 的 QSL 收发状态。"""
    if not str(qso_id or "").strip():
        raise HamlogError("qsl_update 缺少 qso_id")
    status = str(status or "").strip().lower()
    if status not in ("sent", "received", "pending"):
        raise HamlogError(f"status 只能是 sent/received/pending，收到: {status!r}")
    if _sqlite_backend():
        return _sqlite_qsl_update(int(qso_id), status, sent_date, received_date)
    body: dict[str, Any] = {"status": status}
    if sent_date:
        body["sent_date"] = sent_date
    if received_date:
        body["received_date"] = received_date
    _request("PUT", f"/qsl/{int(qso_id)}", json_body=body)
    return {"success": True}


def _sqlite_qsl_update(qso_id: int, status: str, sent_date: str, received_date: str) -> dict[str, Any]:
    updates: dict[str, str] = {}
    today = datetime.utcnow().strftime("%Y%m%d")
    if status == "sent":
        updates["QSL_SEND"] = (_parse_date_arg(sent_date, "sent_date").strftime("%Y%m%d") if sent_date else today)
    elif status == "received":
        updates["QSL_RX"] = (_parse_date_arg(received_date, "received_date").strftime("%Y%m%d") if received_date else today)
    else:  # pending → 清空对应方向（双向都清，语义=未收发）
        updates["QSL_SEND"] = ""
        updates["QSL_RX"] = ""
    sets = ", ".join(f"{k}=?" for k in updates)
    conn = _connect(readonly=False)
    try:
        _require_table(conn, "log")
        cur = conn.execute(f"UPDATE log SET {sets} WHERE id=?", (*updates.values(), qso_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HamlogError(f"未找到 qso_id={qso_id} 的 QSO 记录，无法更新 QSL 状态")
        return {"success": True, "qso_id": qso_id}
    except sqlite3.Error as exc:
        raise HamlogError(f"HamLog 更新 QSL 状态失败: {exc}") from exc
    finally:
        conn.close()


def card_content(qso_id: int) -> dict[str, Any]:
    """取一条 QSO 生成 QSL 卡填写内容（content_lines 可直接逐行抄卡）。"""
    if not str(qso_id or "").strip():
        raise HamlogError("card_content 缺少 qso_id")
    if _sqlite_backend():
        return _sqlite_card_content(int(qso_id))
    qso_raw = _request("GET", f"/qso/{int(qso_id)}")
    if not isinstance(qso_raw, dict):
        raise HamlogError(f"HamLog qso/{qso_id} 返回了非对象数据")
    qso = _normalize_qso(qso_raw)

    my_callsign = qso_raw.get("my_callsign") or ""
    my_grid = qso_raw.get("my_grid") or ""
    their_grid = qso_raw.get("their_grid") or qso_raw.get("grid") or ""
    if not my_callsign or not my_grid:
        station = _request("GET", "/station")
        if isinstance(station, dict):
            my_callsign = my_callsign or station.get("callsign") or ""
            my_grid = my_grid or station.get("grid") or ""
    if not my_callsign:
        raise HamlogError("无法确定本台呼号（HamLog qso 记录与 /api/station 均缺 my_callsign）")
    return _build_card(qso.get("callsign") or "", qso.get("qso_date") or "", qso.get("freq"), qso.get("band") or "",
                       qso.get("mode") or "", str(qso_raw.get("qso_time_utc") or qso_raw.get("time_utc") or ""),
                       qso.get("rst_sent") or "", qso.get("rst_rcvd") or "", their_grid, my_callsign, my_grid)


def _sqlite_card_content(qso_id: int) -> dict[str, Any]:
    conn = _connect(readonly=True)
    try:
        _require_table(conn, "log")
        row = conn.execute("SELECT * FROM log WHERE id=?", (qso_id,)).fetchone()
        if row is None:
            raise HamlogError(f"未找到 qso_id={qso_id} 的 QSO 记录")
        qso = _row_to_qso(row)
        my_callsign, my_grid = "", ""
        settings_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
        if settings_exists:
            for key in ("my_callsign", "my_grid"):
                value = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                if value and value["value"]:
                    if key == "my_callsign":
                        my_callsign = value["value"]
                    else:
                        my_grid = value["value"]
    except sqlite3.Error as exc:
        raise HamlogError(f"HamLog 取卡信息失败: {exc}") from exc
    finally:
        conn.close()
    if not my_callsign:
        raise HamlogError("无法确定本台呼号（HamLog settings 表缺 my_callsign，请先在 HamLog 设置里填写本台信息）")
    return _build_card(qso["callsign"], qso["qso_date"], qso["freq"], qso["band"], qso["mode"], qso["qso_time_utc"],
                       qso["rst_sent"], qso["rst_rcvd"], "", my_callsign, my_grid)


def _build_card(their_callsign: str, qso_date: str, freq: Any, band: str, mode: str, qso_time_utc: str,
                rst_sent: str, rst_rcvd: str, their_grid: str, my_callsign: str, my_grid: str) -> dict[str, Any]:
    lines = [
        "===== QSL INFO =====",
        f"TO: {their_callsign}",
    ]
    if their_grid:
        lines.append(f"TO GRID: {their_grid}")
    lines.append(f"FROM: {my_callsign}" + (f" (GRID {my_grid})" if my_grid else ""))
    if freq:
        lines.append(f"FREQ: {freq} MHz")
    if band:
        lines.append(f"BAND: {band}")
    if mode:
        lines.append(f"MODE: {mode}")
    if qso_date:
        lines.append(f"DATE: {qso_date} UTC")
    if qso_time_utc:
        lines.append(f"TIME: {qso_time_utc}")
    if rst_sent:
        lines.append(f"RST SENT: {rst_sent}")
    if rst_rcvd:
        lines.append(f"RST RCVD: {rst_rcvd}")
    lines.append("TNX QSO  73!")

    return {
        "my_callsign": my_callsign,
        "my_grid": my_grid,
        "their_callsign": their_callsign,
        "their_grid": their_grid,
        "freq": freq,
        "band": band,
        "mode": mode,
        "rst_sent": rst_sent,
        "rst_rcvd": rst_rcvd,
        "qso_date": qso_date,
        "qso_time_utc": qso_time_utc,
        "content_lines": lines,
    }


_TOOLS: dict[str, Any] = {
    "hamlog_qso_search": qso_search,
    "hamlog_qsl_debts": qsl_debts,
    "hamlog_qso_add": qso_add,
    "hamlog_qsl_update": qsl_update,
    "hamlog_card_content": card_content,
}


class HamlogBridge:
    """进程内接入入口（manifest entryPoint），handle_handoff 分发到 5 个工具。"""

    name = "hamlog_adapter"

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if not tool_name:
            return json.dumps(
                {"status": "error", "message": "缺少 tool_name", "data": {}}, ensure_ascii=False
            )
        func = _TOOLS.get(tool_name)
        if func is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"未知工具 {tool_name}，可用: {', '.join(sorted(_TOOLS))}",
                    "data": {},
                },
                ensure_ascii=False,
            )
        # 路由字段（tool_name/agentType/service_name/_tool_call_id）不进工具参数；
        # 兼容嵌套 params/arguments（同 rsba1_adapter 约定），避免具名参数工具被路由键污染报 TypeError
        raw = task.get("params") if isinstance(task.get("params"), dict) else None
        if raw is None and isinstance(task.get("arguments"), dict):
            raw = task["arguments"]
        source = raw if raw is not None else task
        arguments = {
            k: v for k, v in source.items()
            if k not in ("tool_name", "agentType", "service_name", "_tool_call_id", "params", "arguments")
        }
        try:
            result = func(**arguments)
            return json.dumps(
                {"status": "success", "message": "ok", "data": result},
                ensure_ascii=False,
                default=str,
            )
        except HamlogError as exc:
            return json.dumps(
                {"status": "error", "message": str(exc), "data": {}}, ensure_ascii=False
            )
        except TypeError as exc:
            return json.dumps(
                {"status": "error", "message": f"参数错误: {exc}", "data": {}}, ensure_ascii=False
            )


# ---- 独立进程 stdio MCP server（mcporter_bridge 接入用） ----

_TOOL_SCHEMAS = [
    {
        "name": "hamlog_qso_search",
        "description": "搜索 HamLog 里的 QSO 通联记录（呼号/日期区间/波段/模式均可选）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "callsign": {"type": "string", "description": "对方呼号（可部分匹配，取决于 HamLog）"},
                "since": {"type": "string", "description": "起始日期 YYYY-MM-DD"},
                "until": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "band": {"type": "string", "description": "波段，如 20m/40m"},
                "mode": {"type": "string", "description": "模式，如 SSB/FT8/CW"},
            },
        },
    },
    {
        "name": "hamlog_qsl_debts",
        "description": "QSL 卡债清单：owed=我欠的 / owing=欠我的 / all=全部",
        "inputSchema": {
            "type": "object",
            "properties": {"direction": {"type": "string", "enum": ["owed", "owing", "all"]}},
        },
    },
    {
        "name": "hamlog_qso_add",
        "description": "新增一条 QSO 记录（qso_date 缺省取当天 UTC）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "callsign": {"type": "string"},
                "freq": {"type": "string"},
                "mode": {"type": "string"},
                "rst_sent": {"type": "string"},
                "rst_rcvd": {"type": "string"},
                "qso_date": {"type": "string"},
                "band": {"type": "string"},
                "power": {"type": "string"},
            },
            "required": ["callsign", "mode"],
        },
    },
    {
        "name": "hamlog_qsl_update",
        "description": "更新某条 QSO 的 QSL 收发状态",
        "inputSchema": {
            "type": "object",
            "properties": {
                "qso_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["sent", "received", "pending"]},
                "sent_date": {"type": "string"},
                "received_date": {"type": "string"},
            },
            "required": ["qso_id", "status"],
        },
    },
    {
        "name": "hamlog_card_content",
        "description": "取一条 QSO 生成 QSL 卡填写内容（content_lines 可直接逐行抄卡）",
        "inputSchema": {
            "type": "object",
            "properties": {"qso_id": {"type": "integer"}},
            "required": ["qso_id"],
        },
    },
]


def _stdio_main() -> None:
    """最小 MCP stdio server：换行分隔 JSON-RPC 2.0（initialize/tools/list/tools/call）。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        result: Any = None

        if method == "initialize":
            result = {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hamlog_adapter", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": _TOOL_SCHEMAS}
        elif method == "tools/call":
            params = msg.get("params", {}) or {}
            tool_name = params.get("name") or ""
            arguments = params.get("arguments", {}) or {}
            func = _TOOLS.get(tool_name)
            if func is None:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
                }
            else:
                try:
                    data = func(**arguments)
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}
                        ]
                    }
                except HamlogError as exc:
                    result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        elif method and method.startswith("notifications/"):
            continue  # 通知类消息无响应
        else:
            if msg_id is None:
                continue
            result = None
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"不支持的方法: {method}"},
            }
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        if msg_id is not None:
            response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        _stdio_main()
    else:
        print("用法: python adapter.py --stdio  （MCP stdio server 模式）")
