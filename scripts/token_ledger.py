#!/usr/bin/env python3
"""Hermes token 账本审计 CLI（工单 261）。

单一 CLI，纯标准库，**只读**打开 state.db（`mode=ro&immutable=1`），绝不写入。

子命令
------
summary  三段 token + 缓存命中率 + 按模型拆分 + 成本拆分（单价缺省为 null，不用 0 冒充）
tools    按 tool_name 聚合 role='tool' 的条数/字符量（含 P95、最大值）
cache    按天 / 按模型的命中率时间序 + 缓存失效事件检测
reflush  回注放大：按「该消息之后还有多少次 API 调用」摊薄，得到真实账单权重
loops    扫 request_dump 样本，找同工具同参数的连续重复（报错循环）
report   生成基线报告 Markdown 骨架

设计约束（工单 §4）
-------------------
* 不硬编码任何模型单价；单价来自外部 ``scripts/token_pricing.json``（``--pricing`` 可覆盖）。
* 单价缺失时成本列一律 ``None``，绝不填 0。
* `messages.token_count` 实测全为 NULL，故字符量走 ``length(content)``。
* 所有子命令流式打进度到 stderr；总耗时 > 30s 时末尾打印 ``scanned N rows in Xs``。

用法
----
    python3 scripts/token_ledger.py summary --since 30d [--json]
    python3 scripts/token_ledger.py tools   --since 30d --top 20 [--json]
    python3 scripts/token_ledger.py cache   --since 30d [--json]
    python3 scripts/token_ledger.py reflush --since 30d [--json]
    python3 scripts/token_ledger.py loops   --dumps ~/.hermes/sessions --min-repeat 3 [--json]
    python3 scripts/token_ledger.py report  --since 30d --out docs/reports/hermes-token-ledger-2026-10-18.md
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

DEFAULT_DB = os.path.expanduser("~/.hermes/state.db")
DEFAULT_PRICING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_pricing.json")
PROGRESS_EVERY = 100_000
SLOW_THRESHOLD_S = 30.0


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
class LedgerError(Exception):
    """可预期的业务错误（打印到 stderr + 退出码 1，不抛 traceback）。"""


def log_progress(done: int, total: int | None = None) -> None:
    if total:
        print(f"[token_ledger] scanned {done}/{total} rows", file=sys.stderr, flush=True)
    else:
        print(f"[token_ledger] scanned {done} rows", file=sys.stderr, flush=True)


def open_ro(path: str) -> sqlite3.Connection:
    """只读 + immutable 打开，物理上保证不改库。"""
    if not os.path.exists(path):
        raise LedgerError(f"state.db 不存在: {path}")
    uri = f"file:{path}?mode=ro&immutable=1"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        # 触发一次最小查询，空库 / 缺表在这里就暴露
        con.execute("SELECT COUNT(*) FROM sessions").fetchone()
        con.execute("SELECT COUNT(*) FROM messages").fetchone()
    except sqlite3.Error as exc:
        raise LedgerError(f"打不开或表结构不符: {path} ({exc})") from exc
    return con


def parse_since(spec: str) -> tuple[float, float, str, str]:
    """返回 (start_ts, end_ts, since_iso, until_iso)。支持 30d / 7d / 2026-09-18。"""
    now = datetime.now(timezone.utc)
    spec = (spec or "30d").strip()
    if spec.endswith("d") and spec[:-1].isdigit():
        days = int(spec[:-1])
        start = now - timedelta(days=days)
    else:
        try:
            start = datetime.strptime(spec, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise LedgerError(f"--since 无法解析: {spec}（用 30d / 7d / 2026-09-18）") from exc
    return start.timestamp(), now.timestamp(), start.date().isoformat(), now.date().isoformat()


def load_pricing(path: str | None) -> dict:
    """读单价表；文件不存在/无该项 ⇒ 返回空 dict（成本列全部 null）。"""
    target = path or DEFAULT_PRICING
    if not os.path.exists(target):
        return {}
    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def cost_of(tokens: dict, model: str, pricing: dict) -> dict | None:
    """按单价算成本；**任一必需单价缺失即整体 None**（绝不填 0）。"""
    unit = pricing.get(model)
    if not unit:
        return None
    unit_scale = unit.get("_unit", "USD_per_1M_tokens")
    if unit_scale != "USD_per_1M_tokens":
        return None
    out = {}
    for kind in ("input", "cache_read", "cache_write", "output"):
        price = unit.get(kind)
        if not isinstance(price, (int, float)):
            return None
        out[kind] = tokens.get(kind, 0) / 1_000_000 * price
    out["total"] = sum(out.values())
    return out


def hit_rate(cache_read: int, input_tokens: int) -> float | None:
    """命中率 = cache_read / (input + cache_read)；分母为 0 时返回 None。"""
    denom = (cache_read or 0) + (input_tokens or 0)
    if denom <= 0:
        return None
    return cache_read / denom


def emit(payload: dict, as_json: bool, human_lines: list[str] | None = None) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif human_lines:
        print("\n".join(human_lines))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def finish(t0: float, scanned: int) -> None:
    elapsed = time.time() - t0
    if elapsed > SLOW_THRESHOLD_S:
        print(f"scanned {scanned} rows in {elapsed:.1f}s", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# A-1 summary
# --------------------------------------------------------------------------- #
TOKEN_COLS = {
    "input": "input_tokens",
    "cache_read": "cache_read_tokens",
    "cache_write": "cache_write_tokens",
    "output": "output_tokens",
    "reasoning": "reasoning_tokens",
}


def _sum_sessions(con: sqlite3.Connection, start: float, end: float, where_extra: str = "") -> dict:
    cols = ", ".join(f"COALESCE(SUM({col}),0) AS {alias}" for alias, col in TOKEN_COLS.items())
    sql = (
        f"SELECT COUNT(*) AS n, COALESCE(SUM(api_call_count),0) AS calls, {cols} "
        f"FROM sessions WHERE started_at >= ? AND started_at < ? {where_extra}"
    )
    row = con.execute(sql, (start, end)).fetchone()
    tokens = {k: row[k] for k in TOKEN_COLS}
    return {"sessions": row["n"], "requests": row["calls"], "tokens": tokens}


def cmd_summary(args) -> int:
    t0 = time.time()
    start, end, since_iso, until_iso = parse_since(args.since)
    con = open_ro(args.db)
    try:
        agg = _sum_sessions(con, start, end)
        if agg["sessions"] == 0:
            raise LedgerError(
                f"窗口 {since_iso} ~ {until_iso} 内没有任何 session"
                "（检查 --since / --db 是否指向正确的库）"
            )
        unknown = con.execute(
            "SELECT COUNT(*) FROM sessions WHERE started_at >= ? AND started_at < ?"
            " AND (cost_status IS NULL OR cost_status = 'unknown')",
            (start, end),
        ).fetchone()[0]

        by_model = []
        rows = con.execute(
            "SELECT COALESCE(model,'(unknown)') AS model, COUNT(*) AS n,"
            " COALESCE(SUM(api_call_count),0) AS calls,"
            " COALESCE(SUM(input_tokens),0) AS inp,"
            " COALESCE(SUM(cache_read_tokens),0) AS cread,"
            " COALESCE(SUM(cache_write_tokens),0) AS cwrite,"
            " COALESCE(SUM(output_tokens),0) AS outp,"
            " COALESCE(SUM(reasoning_tokens),0) AS reas"
            " FROM sessions WHERE started_at >= ? AND started_at < ?"
            " GROUP BY COALESCE(model,'(unknown)') ORDER BY calls DESC",
            (start, end),
        ).fetchall()
        for r in rows:
            by_model.append(
                {
                    "model": r["model"],
                    "sessions": r["n"],
                    "api_calls": r["calls"],
                    "input": r["inp"],
                    "cache_read": r["cread"],
                    "cache_write": r["cwrite"],
                    "output": r["outp"],
                    "reasoning": r["reas"],
                    "cache_hit_rate": hit_rate(r["cread"], r["inp"]),
                }
            )

        pricing = load_pricing(args.pricing)
        warnings = []
        if unknown:
            warnings.append(f"{unknown} 条 session 的 cost_status 为 unknown，estimated_cost 仅供量级参考")
        if not pricing:
            warnings.append("未配置单价（scripts/token_pricing.json 为空或不存在），成本列全部为 null")

        cost_breakdown = {
            "input": None,
            "cache_read": None,
            "cache_write": None,
            "output": None,
            "note": "单价未配置，见 --pricing" if not pricing else None,
        }
        if pricing:
            total = {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0}
            priced_any = False
            for item in by_model:
                c = cost_of(item, item["model"], pricing)
                if c is None:
                    continue
                priced_any = True
                for kind in total:
                    total[kind] += c[kind]
            if priced_any:
                cost_breakdown.update(total)
                cost_breakdown["note"] = None

        payload = {
            "window": {"since": since_iso, "until": until_iso},
            "requests": agg["requests"],
            "sessions": agg["sessions"],
            "tokens": agg["tokens"],
            "cache_hit_rate": hit_rate(agg["tokens"]["cache_read"], agg["tokens"]["input"]),
            "cost_breakdown": cost_breakdown,
            "by_model": by_model,
            "warnings": warnings,
        }

        hr = payload["cache_hit_rate"]
        lines = [
            f"窗口: {since_iso} ~ {until_iso}",
            f"sessions: {agg['sessions']}   api_calls: {agg['requests']}",
            f"input      {agg['tokens']['input']:>14,}",
            f"cache_read {agg['tokens']['cache_read']:>14,}",
            f"cache_write{agg['tokens']['cache_write']:>14,}",
            f"output     {agg['tokens']['output']:>14,}",
            f"reasoning  {agg['tokens']['reasoning']:>14,}",
            f"缓存命中率: {'n/a' if hr is None else f'{hr:.1%}'}",
            "成本: " + ("单价未配置（null）" if not pricing else "见 --json"),
        ]
        for w in warnings:
            lines.append(f"! {w}")
        emit(payload, args.json, lines)
        finish(t0, agg["sessions"])
        return 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# A-2 tools
# --------------------------------------------------------------------------- #
def cmd_tools(args) -> int:
    t0 = time.time()
    start, end, since_iso, until_iso = parse_since(args.since)
    con = open_ro(args.db)
    try:
        session_ids = [
            r[0]
            for r in con.execute(
                "SELECT id FROM sessions WHERE started_at >= ? AND started_at < ?", (start, end)
            ).fetchall()
        ]
        if not session_ids:
            raise LedgerError("窗口内没有 session（先用 summary 确认时间范围）")

        sizes: dict[str, list[int]] = defaultdict(list)
        placeholders = ",".join("?" for _ in session_ids)
        sql = (
            "SELECT COALESCE(tool_name,'(none)') AS tool, LENGTH(COALESCE(content,'')) AS n "
            f"FROM messages WHERE role='tool' AND session_id IN ({placeholders})"
        )
        scanned = 0
        for row in con.execute(sql, session_ids):
            sizes[row["tool"]].append(row["n"] or 0)
            scanned += 1
            if scanned % PROGRESS_EVERY == 0:
                log_progress(scanned)

        items = []
        for tool, vals in sizes.items():
            vals.sort()
            n = len(vals)
            p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
            items.append(
                {
                    "tool_name": tool,
                    "calls": n,
                    "chars": sum(vals),
                    "mean_chars": round(sum(vals) / n, 1) if n else 0.0,
                    "p95_chars": vals[p95_idx] if n else 0,
                    "max_chars": vals[-1] if n else 0,
                }
            )
        items.sort(key=lambda x: (-x["chars"], x["tool_name"]))
        top = args.top if args.top and args.top > 0 else len(items)
        items = items[:top]

        payload = {
            "window": {"since": since_iso, "until": until_iso},
            "tools": items,
            "scanned_messages": scanned,
        }
        lines = [f"窗口 {since_iso} ~ {until_iso}  工具消息 {scanned:,} 条", ""]
        lines.append(f"{'tool':<20}{'calls':>8}{'chars':>15}{'mean':>10}{'p95':>10}{'max':>10}")
        for it in items:
            lines.append(
                f"{it['tool_name']:<20}{it['calls']:>8}{it['chars']:>15,}"
                f"{it['mean_chars']:>10}{it['p95_chars']:>10,}{it['max_chars']:>10,}"
            )
        emit(payload, args.json, lines)
        finish(t0, scanned)
        return 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# A-3 cache
# --------------------------------------------------------------------------- #
def _invalidations(con: sqlite3.Connection, start: float, end: float, threshold: float) -> list[dict]:
    """缓存失效事件检测。

    精度说明：state.db 只有 session 级聚合（无逐请求 token），因此在
    **同一模型、按 started_at 相邻的两个 session** 上做近似：
    后者的 input_tokens 若 > 前者 cache_read * threshold ⇒ 记为一次失效。
    同时记录 system_prompt_hash 是否变化，便于判断原因。
    """
    rows = con.execute(
        "SELECT id, model, started_at, COALESCE(input_tokens,0) AS inp,"
        " COALESCE(cache_read_tokens,0) AS cread, system_prompt_hash"
        " FROM sessions WHERE started_at >= ? AND started_at < ?"
        " ORDER BY started_at ASC",
        (start, end),
    ).fetchall()
    events = []
    prev = None
    for r in rows:
        if prev is not None and prev["model"] == r["model"] and r["inp"] > prev["cread"] * threshold:
            events.append(
                {
                    "session_id": r["id"],
                    "at": datetime.fromtimestamp(r["started_at"], timezone.utc).isoformat(),
                    "model": r["model"],
                    "input_tokens": r["inp"],
                    "prev_cache_read": prev["cread"],
                    "system_prompt_changed": prev["system_prompt_hash"] != r["system_prompt_hash"],
                }
            )
        prev = r
    return events


def cmd_cache(args) -> int:
    t0 = time.time()
    start, end, since_iso, until_iso = parse_since(args.since)
    con = open_ro(args.db)
    try:
        by_day = []
        for r in con.execute(
            "SELECT date(started_at,'unixepoch') AS d,"
            " COALESCE(SUM(input_tokens),0) AS inp, COALESCE(SUM(cache_read_tokens),0) AS cread"
            " FROM sessions WHERE started_at >= ? AND started_at < ?"
            " GROUP BY d ORDER BY d",
            (start, end),
        ):
            by_day.append(
                {"date": r["d"], "input": r["inp"], "cache_read": r["cread"],
                 "cache_hit_rate": hit_rate(r["cread"], r["inp"])}
            )

        by_model = []
        for r in con.execute(
            "SELECT COALESCE(model,'(unknown)') AS model,"
            " COALESCE(SUM(input_tokens),0) AS inp, COALESCE(SUM(cache_read_tokens),0) AS cread"
            " FROM sessions WHERE started_at >= ? AND started_at < ?"
            " GROUP BY COALESCE(model,'(unknown)') ORDER BY cread DESC",
            (start, end),
        ):
            by_model.append(
                {"model": r["model"], "input": r["inp"], "cache_read": r["cread"],
                 "cache_hit_rate": hit_rate(r["cread"], r["inp"])}
            )

        events = _invalidations(con, start, end, args.threshold)
        affected = sum(e["input_tokens"] for e in events)

        payload = {
            "window": {"since": since_iso, "until": until_iso},
            "threshold": args.threshold,
            "by_day": by_day,
            "by_model": by_model,
            "invalidations": {"count": len(events), "affected_input_tokens": affected, "events": events},
        }
        lines = [f"窗口 {since_iso} ~ {until_iso}  阈值 {args.threshold:.0%}", ""]
        lines.append("按天命中率:")
        for d in by_day:
            hr = d["cache_hit_rate"]
            lines.append(f"  {d['date']}  {'n/a' if hr is None else f'{hr:.1%}'}  (input {d['input']:,})")
        lines.append("")
        lines.append(f"失效事件: {len(events)} 次，涉及 input {affected:,} tokens")
        for e in events[:10]:
            lines.append(
                f"  {e['at'][:19]}  {e['model']}  input {e['input_tokens']:,}"
                f"  (前次 cache_read {e['prev_cache_read']:,})"
                f"  system_prompt 变化={e['system_prompt_changed']}"
            )
        emit(payload, args.json, lines)
        finish(t0, len(by_day))
        return 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# A-4 reflush（回注放大）
# --------------------------------------------------------------------------- #
def cmd_reflush(args) -> int:
    t0 = time.time()
    start, end, since_iso, until_iso = parse_since(args.since)
    con = open_ro(args.db)
    try:
        sessions = {
            r["id"]: {"calls": r["calls"] or 0, "total": r["n"] or 0}
            for r in con.execute(
                "SELECT id, COALESCE(api_call_count,0) AS calls, COALESCE(message_count,0) AS n"
                " FROM sessions WHERE started_at >= ? AND started_at < ?",
                (start, end),
            ).fetchall()
        }
        if not sessions:
            raise LedgerError("窗口内没有 session")

        raw: dict[str, int] = defaultdict(int)
        amort: dict[str, float] = defaultdict(float)
        pos = defaultdict(int)
        samples: dict[str, dict] = {}
        placeholders = ",".join("?" for _ in sessions)
        sql = (
            "SELECT session_id, id, COALESCE(tool_name,'(none)') AS tool,"
            " LENGTH(COALESCE(content,'')) AS n FROM messages"
            f" WHERE role='tool' AND session_id IN ({placeholders})"
            " ORDER BY session_id, id"
        )
        scanned = 0
        for row in con.execute(sql, list(sessions)):
            sid = row["session_id"]
            info = sessions[sid]
            idx = pos[sid]
            pos[sid] = idx + 1
            n_chars = row["n"] or 0
            total = info["total"] or max(1, idx + 1)
            # 该消息之后剩余比例 × 调用次数 = 回注次数
            factor = max(0.0, info["calls"] * (total - idx) / total)
            raw[row["tool"]] += n_chars
            amort[row["tool"]] += n_chars * factor
            slot = samples.setdefault(sid, {})
            cur = {"tool_name": row["tool"], "idx": idx, "chars": n_chars, "factor": round(factor, 4)}
            slot.setdefault("first", cur)
            slot["last"] = cur
            scanned += 1
            if scanned % PROGRESS_EVERY == 0:
                log_progress(scanned)

        items = []
        for tool, raw_chars in raw.items():
            a = amort[tool]
            items.append(
                {
                    "tool_name": tool,
                    "raw_chars": raw_chars,
                    "amortized_chars": round(a, 1),
                    "ratio": round(a / raw_chars, 2) if raw_chars else None,
                }
            )
        items.sort(key=lambda x: -x["amortized_chars"])

        payload = {
            "window": {"since": since_iso, "until": until_iso},
            "note": "摊销系数 = api_call_count * (n - i) / n，i 为该消息在 session 内的序号",
            "tools": items,
            "samples": samples,
        }
        lines = [f"窗口 {since_iso} ~ {until_iso}  回注放大（真实账单权重）", ""]
        lines.append(f"{'tool':<20}{'raw chars':>15}{'amortized':>16}{'ratio':>8}")
        for it in items[: args.top or 20]:
            ratio = "" if it["ratio"] is None else f"{it['ratio']:>8.2f}"
            lines.append(
                f"{it['tool_name']:<20}{it['raw_chars']:>15,}{it['amortized_chars']:>16,.0f}{ratio}"
            )
        emit(payload, args.json, lines)
        finish(t0, scanned)
        return 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# A-5 loops
# --------------------------------------------------------------------------- #
def _iter_dumps(path: str):
    for fn in sorted(glob.glob(os.path.join(path, "request_dump_*.json"))):
        try:
            with open(fn, encoding="utf-8") as fh:
                yield fn, json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue


def _tool_signature(payload: dict) -> tuple[str, str] | None:
    """尽力从 dump 里提取 (tool_name, params_hash)。样本结构不稳，做多键兜底。"""
    for key in ("tool_calls", "tools", "tool"):
        val = payload.get(key)
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, dict):
                name = first.get("name") or first.get("tool_name") or ""
                args = first.get("arguments") or first.get("input") or {}
                if name:
                    blob = json.dumps(args, sort_keys=True, ensure_ascii=False)
                    return name, hashlib.sha256(blob.encode()).hexdigest()[:16]
    err = payload.get("error")
    if isinstance(err, dict) and err.get("type"):
        return f"error:{err['type']}", ""
    return None


def cmd_loops(args) -> int:
    t0 = time.time()
    if not os.path.isdir(args.dumps):
        raise LedgerError(f"dump 目录不存在: {args.dumps}")

    per_session: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    files = 0
    for fn, payload in _iter_dumps(args.dumps):
        files += 1
        sid = str(payload.get("session_id") or payload.get("session") or os.path.basename(fn))
        sig = _tool_signature(payload)
        if sig:
            per_session[sid].append((sig[0], sig[1], os.path.basename(fn)))
        if files % PROGRESS_EVERY == 0:
            log_progress(files)

    hits = []
    for sid, seq in per_session.items():
        run = 1
        for i in range(1, len(seq)):
            if seq[i][0] == seq[i - 1][0] and seq[i][1] == seq[i - 1][1]:
                run += 1
            else:
                if run >= args.min_repeat:
                    hits.append((sid, seq[i - run][0], run, seq[i - run][2]))
                run = 1
        if run >= args.min_repeat:
            hits.append((sid, seq[len(seq) - run][0], run, seq[len(seq) - run][2]))

    items = [
        {"session_id": sid, "tool_name": tool, "repeats": rep, "first_dump": first}
        for sid, tool, rep, first in sorted(hits, key=lambda x: -x[2])
    ]
    payload = {"dumps_dir": args.dumps, "files_scanned": files, "min_repeat": args.min_repeat, "loops": items}
    lines = [f"扫描 {files} 份 dump（min-repeat={args.min_repeat}）", ""]
    if not items:
        lines.append("未发现重复循环")
    for it in items[: args.top or 20]:
        lines.append(f"  {it['session_id'][:24]:<26} {it['tool_name']:<18} x{it['repeats']}  首现 {it['first_dump']}")
    emit(payload, args.json, lines)
    finish(t0, files)
    return 0


# --------------------------------------------------------------------------- #
# C report
# --------------------------------------------------------------------------- #
REPORT_TEMPLATE = """# Hermes token 账本基线（{since} ~ {until}）

> 由 `scripts/token_ledger.py report` 生成骨架；数字来自 `summary/cache/reflush/loops` 的实际输出。

## 1. 样本口径

- 数据源：`state.db`（只读 `mode=ro&immutable=1`），sessions/messages 聚合。
- **限制**：`request_dump_*.json` 全部是**失败请求**（`error.type` 非空的占满），只能用于「报错循环」分析，
  **不可当成本基线**。
- `messages.token_count` 全为 NULL，字符口径走 `length(content)`。
- 窗口：{since} ~ {until}；sessions {sessions}；api_calls {requests}。

## 2. 三段占比 + 缓存命中率

| 项 | 数值 |
|---|---:|
| input | {input:,} |
| cache_read | {cache_read:,} |
| cache_write | {cache_write:,} |
| output | {output:,} |
| 缓存命中率 | {hit} |

## 3. 回注放大：真实账单权重 Top 10

{reflush_table}

## 4. 缓存失效事件

{invalidation_section}

## 5. 三条改进建议

> 每条都要写「影响哪个指标 + 量级区间」，**不得写倍数**。

1. **（待填）** 影响指标：… 量级：…
2. **（待填）** 影响指标：… 量级：…
3. **（待填）** 影响指标：… 量级：…

---

> 本报告数字来源：沈遥 2026-10-18 云服实测（工单 §0.2）+ 脚本 fixture 自检。未测项标注「未测」。
"""


def cmd_report(args) -> int:
    start, end, since_iso, until_iso = parse_since(args.since)
    con = open_ro(args.db)
    try:
        agg = _sum_sessions(con, start, end)
        hr = hit_rate(agg["tokens"]["cache_read"], agg["tokens"]["input"])
        events = _invalidations(con, start, end, args.threshold)
    finally:
        con.close()

    reflush_rows = ["| tool | 原始字符 | 摊销字符 | 比值 |", "|---|---:|---:|---:|"]
    reflush_rows.append("| （待 `reflush` 实际输出填充） |  |  |  |")

    if events:
        inv = ["| 时间 | model | input | 前次 cache_read | system_prompt 变化 |", "|---|---|---:|---:|---|"]
        for e in events[:20]:
            inv.append(
                f"| {e['at'][:19]} | {e['model']} | {e['input_tokens']:,} | "
                f"{e['prev_cache_read']:,} | {e['system_prompt_changed']} |"
            )
        inv.append(f"\n合计 **{len(events)}** 次失效，涉及 input **{sum(x['input_tokens'] for x in events):,}** tokens。")
    else:
        inv = [f"未检测到失效事件（阈值 {args.threshold:.0%}）。"]

    text = REPORT_TEMPLATE.format(
        since=since_iso,
        until=until_iso,
        sessions=agg["sessions"],
        requests=agg["requests"],
        input=agg["tokens"]["input"],
        cache_read=agg["tokens"]["cache_read"],
        cache_write=agg["tokens"]["cache_write"],
        output=agg["tokens"]["output"],
        hit="n/a" if hr is None else f"{hr:.1%}",
        reflush_table="\n".join(reflush_rows),
        invalidation_section="\n".join(inv),
    )

    out = args.out
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"已写入 {out}（{len(text)} 字符）")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="token_ledger", description="Hermes token 账本审计（只读）")
    p.add_argument("--db", default=DEFAULT_DB, help=f"state.db 路径（默认 {DEFAULT_DB}）")
    p.add_argument("--pricing", default=None, help="单价表 JSON（默认 scripts/token_pricing.json）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("summary", help="三段 token + 命中率 + 按模型 + 成本拆分")
    sp.add_argument("--since", default="30d")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("tools", help="按 tool_name 聚合字符量")
    sp.add_argument("--since", default="30d")
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_tools)

    sp = sub.add_parser("cache", help="命中率时间序 + 失效事件")
    sp.add_argument("--since", default="30d")
    sp.add_argument("--threshold", type=float, default=0.5, help="失效判定阈值（默认 0.5）")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cache)

    sp = sub.add_parser("reflush", help="回注放大（真实账单权重）")
    sp.add_argument("--since", default="30d")
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_reflush)

    sp = sub.add_parser("loops", help="报错/重复循环")
    sp.add_argument("--dumps", default=os.path.expanduser("~/.hermes/sessions"))
    sp.add_argument("--min-repeat", type=int, default=3)
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_loops)

    sp = sub.add_parser("report", help="生成基线报告骨架")
    sp.add_argument("--since", default="30d")
    sp.add_argument("--threshold", type=float, default=0.5)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_report)

    # 允许 --pricing 写在子命令之后（工单写法 `summary ... --pricing <file>`）
    # 用 SUPPRESS 保证子命令未显式给出时不会覆盖全局值
    for sub_parser in sub.choices.values():
        sub_parser.add_argument(
            "--pricing", default=argparse.SUPPRESS, help="单价表 JSON（写在子命令前后均可）"
        )

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
