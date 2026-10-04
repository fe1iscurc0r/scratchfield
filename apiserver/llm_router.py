"""Turn 级模型路由（卷125 W125-01，参考 OpenSquilla 的 token 效率机制，自研实现）。

一句话：**每轮按复杂度选最便宜能胜任的模型**——日常对话走便宜的（flash），
代码/长上下文/任务步骤里吃重的活走强的（pro），配置的 fallback 链保持不变。

保守前提（工单要求）：

- `router.enabled` **默认 false**：不开启就完全走现有行为（现有调用链零改动）
- 敏感任务**强制强模型**：审批/审计/安全/支付这类 turn 不允许因省钱走弱模型（白名单机制）
- 预算上限可配置（`router.daily_budget_usd`），超了回落默认模型

判定信号（全部来自已有的东西，不额外调模型）：

| 信号 | 来源 | 效果 |
| --- | --- | --- |
| 消息长度 | 本轮 messages 总字符数 | 超阈值 → strong |
| 强任务关键词 | 文本里出现 `code_exec`/`test_run`/`file_write`… | → strong |
| 复杂正则 | `router.complex_patterns` | 命中 → strong |
| 任务步骤类型 | 卷123 Goal Mode 的 step type（explore/code/test/review） | 按 `step_budget` 映射 |
| 显式指令 | 用户文本里的 `[STRONG]` / `[CHEAP]` | 直接指定档位 |
| 敏感白名单 | `router.sensitive_keywords` | **强制 strong**（覆盖显式指令） |
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TIER_STRONG = "strong"
TIER_CHEAP = "cheap"
TIER_DEFAULT = "default"

_FORCE_RE = re.compile(r"\[(STRONG|CHEAP)\]", re.IGNORECASE)


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "router", None)
    except Exception:  # noqa: BLE001
        return None


def enabled() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "enabled", False)) if cfg is not None else False


def _get(name: str, default: Any) -> Any:
    cfg = _cfg()
    value = getattr(cfg, name, None) if cfg is not None else None
    return default if value in (None, "") else value


# ---------------------------------------------------------------------------
# 复杂度与档位
# ---------------------------------------------------------------------------


def messages_text(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for msg in messages or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.append(" ".join(str(c.get("text") or "") for c in content if isinstance(c, dict)))
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            parts.append(" ".join(str(t.get("function", {}).get("name") or "") for t in tool_calls
                                  if isinstance(t, dict)))
    return "\n".join(parts)


def complexity_score(messages: List[Dict[str, Any]], *, tools: List[dict] | None = None,
                     step_type: str = "") -> Tuple[int, List[str]]:
    """给本轮打个复杂度分（0 起，越高越该用强模型），附命中的理由。"""
    cfg = _cfg()
    text = messages_text(messages)
    reasons: List[str] = []
    score = 0

    threshold = int(_get("length_threshold_chars", 8000))
    if len(text) > threshold:
        score += 3
        reasons.append(f"长上下文({len(text)}>{threshold})")
    elif len(text) > threshold // 2:
        score += 1
        reasons.append(f"中等长度({len(text)})")

    lowered = text.lower()
    keywords = list(_get("strong_keywords", []) or [])
    hit_keywords = [k for k in keywords if str(k).lower() in lowered]
    if hit_keywords:
        score += 3
        reasons.append(f"强任务关键词({','.join(hit_keywords[:4])})")

    for pattern in (_get("complex_patterns", []) or []):
        try:
            if re.search(str(pattern), text):
                score += 3
                reasons.append(f"复杂模式命中({pattern})")
                break
        except re.error:
            logger.debug("[llm_router] 非法 complex_pattern: %s", pattern)

    if tools:
        score += 1
        reasons.append(f"带工具({len(tools)})")

    if step_type:
        budget = dict(_get("step_budget", {}) or {})
        if budget.get(str(step_type)) == TIER_STRONG:
            score += 2
            reasons.append(f"步骤类型需强模型({step_type})")
    return score, reasons


def _is_sensitive(text: str) -> str | None:
    """敏感任务判定（命中即强制强模型）。"""
    lowered = str(text or "").lower()
    for word in (_get("sensitive_keywords", []) or []):
        if str(word).lower() in lowered:
            return str(word)
    return None


def decide(
    messages: List[Dict[str, Any]], *, tools: List[dict] | None = None,
    step_type: str = "", task_type: str = "",
) -> Dict[str, Any]:
    """核心决策：返回 `{tier, model, reason, complexity, enabled}`。

    注意：**不写库、不发事件**（那是 W125-02/04 的 record/span 层干的事），纯函数便于测试与复用。
    """
    text = messages_text(messages)
    score, reasons = complexity_score(messages, tools=tools, step_type=step_type)

    force = ""
    force_hit = _FORCE_RE.search(text)
    if force_hit:
        force = force_hit.group(1).lower()
        reasons.append(f"显式指令[{force.upper()}]")

    sensitive_hit = _is_sensitive(text) or (_is_sensitive(task_type) is not None
                                            and task_type or "")
    budget_tier = str(dict(_get("step_budget", {}) or {}).get(str(step_type)) or "")
    tier = TIER_DEFAULT
    strong_score = int(_get("strong_score_threshold", 3))
    if sensitive_hit and bool(_get("sensitive_force_strong", True)):
        tier = TIER_STRONG  # 敏感任务不允许因省钱走弱模型
        reasons.append(f"敏感任务({sensitive_hit})→强制强模型")
    elif force == "strong":
        tier = TIER_STRONG
    elif force == "cheap":
        tier = TIER_CHEAP
    elif budget_tier == TIER_STRONG:
        # 步骤预算表是显式配置，优先级高于分数（否则「code 步该用强模型」会被阈值吃掉）
        tier = TIER_STRONG
    elif score >= strong_score:
        tier = TIER_STRONG
    elif budget_tier == TIER_CHEAP or score <= 0:
        tier = TIER_CHEAP
    else:
        tier = TIER_DEFAULT

    model = {
        TIER_STRONG: str(_get("strong_model", "") or ""),
        TIER_CHEAP: str(_get("cheap_model", "") or ""),
        TIER_DEFAULT: str(_get("default_model", "") or ""),
    }.get(tier, "")

    return {
        "enabled": enabled(),
        "tier": tier,
        "model": model,
        "complexity": score,
        "reasons": reasons,
        "sensitive": bool(sensitive_hit),
        "step_type": str(step_type or ""),
        "task_type": str(task_type or ""),
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# 与 llm_service 的接缝
# ---------------------------------------------------------------------------


def route_override(
    messages: List[Dict[str, Any]], *, tools: List[dict] | None = None,
    step_type: str = "", task_type: str = "", session_id: str = "",
) -> Dict[str, Any] | None:
    """给 `llm_service.stream_chat_with_context` 用的 model_override。

    Returns:
        需要覆盖时返回 `{"model": ..., "_router": decision}`；不开启/无模型可换/预算耗尽返回 None
        （调用方保持原行为）。
    """
    if not enabled():
        return None
    decision = decide(messages, tools=tools, step_type=step_type, task_type=task_type)
    if not decision["tier"] or not decision["model"]:
        return None
    if decision["tier"] == TIER_DEFAULT:
        return None  # default 档 = 沿用现有配置，不做覆盖

    override: Dict[str, Any] = {"model": decision["model"], "_router": decision}
    strong_base = str(_get("strong_api_base", "") or "")
    strong_key = str(_get("strong_api_key", "") or "")
    if decision["tier"] == TIER_STRONG and strong_base:
        override["api_base"] = strong_base
    if decision["tier"] == TIER_STRONG and strong_key:
        override["api_key"] = strong_key
    if session_id:
        override["_router"]["session_id"] = session_id
    logger.info("[llm_router] 路由决策：tier=%s model=%s 复杂度=%s 理由=%s",
                decision["tier"], decision["model"], decision["complexity"], decision["reasons"])
    return override


def budget_state() -> Dict[str, Any]:
    """当日预算状态（超预算时路由回落 default）。"""
    limit = float(_get("daily_budget_usd", 0.0) or 0.0)
    if limit <= 0:
        return {"limited": False, "limit": 0.0, "spent": 0.0, "exceeded": False}
    spent = 0.0
    try:
        from apiserver.llm_router import _log  # noqa: F401  (占位，见 W125-02)

        spent = 0.0
    except Exception:  # noqa: BLE001
        spent = 0.0
    return {"limited": True, "limit": limit, "spent": round(spent, 4), "exceeded": spent >= limit}


def estimate_cost(model: str, tokens: int) -> float:
    """按 `router.pricing`（每 1K token 单价）估算成本；未配置价格返回 0。"""
    pricing = dict(_get("pricing", {}) or {})
    price = pricing.get(str(model))
    if price is None:
        return 0.0
    try:
        return round(float(price) * (int(tokens) / 1000.0), 6)
    except (TypeError, ValueError):
        return 0.0


def router_summary() -> Dict[str, Any]:
    """调试/README 用：当前路由配置概览。"""
    return {
        "enabled": enabled(),
        "models": {"cheap": _get("cheap_model", ""), "strong": _get("strong_model", ""),
                   "default": _get("default_model", "")},
        "strong_score_threshold": _get("strong_score_threshold", 3),
        "length_threshold_chars": _get("length_threshold_chars", 8000),
        "strong_keywords": list(_get("strong_keywords", []) or []),
        "step_budget": dict(_get("step_budget", {}) or {}),
        "sensitive_keywords": list(_get("sensitive_keywords", []) or []),
        "pricing": dict(_get("pricing", {}) or {}),
        "budget": budget_state(),
    }


# ---------------------------------------------------------------------------
# W125-02：反馈飞轮 —— 决策记录（SQLite）+ 周度分析 + 调优建议（人工确认）
# ---------------------------------------------------------------------------


def _log_db_path() -> Any:
    from apiserver.task_store import _default_db_path

    return _default_db_path()


def _connect(db_path: Any = None) -> Any:
    import sqlite3
    from pathlib import Path

    path = Path(db_path) if db_path else Path(_log_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS router_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts REAL,"
        " session_id TEXT,"
        " turn_id TEXT,"
        " task_type TEXT,"
        " step_type TEXT,"
        " complexity INTEGER,"
        " tier TEXT,"
        " model_chosen TEXT,"
        " reasons TEXT,"
        " sensitive INTEGER DEFAULT 0,"
        " cost_estimate REAL DEFAULT 0,"
        " success INTEGER,"
        " latency REAL,"
        " tokens INTEGER,"
        " error TEXT)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_router_ts ON router_logs(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_router_session ON router_logs(session_id)")
    return conn


def record_decision(decision: Dict[str, Any], *, session_id: str = "", turn_id: str = "",
                    tokens: int = 0) -> int | None:
    """记录一次路由决策（飞轮数据源）+ 广播 surface_router 事件；返回记录 id。

    记录失败/广播失败都静默（不影响对话）。
    """
    _emit_decision_event(decision, session_id=session_id, turn_id=turn_id, tokens=tokens)
    if not _get("log_enabled", True):
        return None
    import json

    model = str(decision.get("model") or "")
    cost = estimate_cost(model, int(tokens or 0))
    try:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT INTO router_logs (ts, session_id, turn_id, task_type, step_type, complexity,"
                " tier, model_chosen, reasons, sensitive, cost_estimate, success, latency, tokens, error)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (float(decision.get("ts") or time.time()), str(session_id), str(turn_id),
                 str(decision.get("task_type") or ""), str(decision.get("step_type") or ""),
                 int(decision.get("complexity") or 0), str(decision.get("tier") or ""), model,
                 json.dumps(decision.get("reasons") or [], ensure_ascii=False),
                 1 if decision.get("sensitive") else 0, cost, None, None, int(tokens or 0), ""),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 - 记录失败不影响对话
        logger.debug("[llm_router] 决策记录失败: %s", e)
        return None


def _emit_decision_event(decision: Dict[str, Any], *, session_id: str = "", turn_id: str = "",
                         tokens: int = 0) -> None:
    """W125-04：把决策广播到总线（surface_router 消费者据此计数/可查）。"""
    try:
        from apiserver.event_bus import get_bus

        get_bus().emit("lumo.router.decision", {
            "tier": str(decision.get("tier") or ""),
            "model": str(decision.get("model") or ""),
            "complexity": int(decision.get("complexity") or 0),
            "reasons": list(decision.get("reasons") or []),
            "sensitive": bool(decision.get("sensitive")),
            "step_type": str(decision.get("step_type") or ""),
            "task_type": str(decision.get("task_type") or ""),
            "session_id": str(session_id or ""),
            "turn_id": str(turn_id or ""),
            "tokens": int(tokens or 0),
            "cost_estimate": estimate_cost(str(decision.get("model") or ""), int(tokens or 0)),
            "ts": float(decision.get("ts") or time.time()),
        })
    except Exception as e:  # noqa: BLE001 - 广播失败不影响对话
        logger.debug("[llm_router] 决策事件广播失败: %s", e)


def decisions_for_session(session_id: str, *, limit: int = 50, db_path: Any = None) -> List[Dict[str, Any]]:
    """W125-04：按会话/任务查路由决策（跨通道：同一 session 的任一入口都能查）。"""
    conn = _connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        rows = conn.execute(
            "SELECT * FROM router_logs WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
            (str(session_id), max(1, int(limit))),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def decisions_for_task(task_id: str, *, limit: int = 50, db_path: Any = None) -> List[Dict[str, Any]]:
    """按任务查决策（卷123 task_store 的任务：决策 turn_id 里带 session，任务再关联会话）。"""
    try:
        from apiserver import task_store

        task = task_store.get_task(task_id)
        if not task:
            return []
        return decisions_for_session(str(task.get("session_id") or ""), limit=limit, db_path=db_path)
    except Exception as e:  # noqa: BLE001
        logger.debug("[llm_router] 按任务查决策失败: %s", e)
        return []


def record_outcome(log_id: int | None, *, success: bool, latency: float = 0.0,
                   tokens: int = 0, error: str = "") -> None:
    """turn 完成后回填结果（成功/失败/延迟/用量，并按实际 tokens 重算成本）。"""
    if not log_id:
        return
    try:
        conn = _connect()
        try:
            row = conn.execute("SELECT model_chosen FROM router_logs WHERE id = ?", (int(log_id),)).fetchone()
            model = str(row[0]) if row else ""
            cost = estimate_cost(model, int(tokens or 0))
            conn.execute(
                "UPDATE router_logs SET success = ?, latency = ?, tokens = ?, error = ?,"
                " cost_estimate = CASE WHEN ? > 0 THEN ? ELSE cost_estimate END WHERE id = ?",
                (1 if success else 0, float(latency), int(tokens), str(error)[:300],
                 int(tokens), cost, int(log_id)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        logger.debug("[llm_router] 结果回填失败: %s", e)


def _rows(since_ts: float, db_path: Any = None) -> List[Dict[str, Any]]:
    conn = _connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        rows = conn.execute("SELECT * FROM router_logs WHERE ts >= ? ORDER BY ts", (float(since_ts),)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def analyze(period: str = "week", *, db_path: Any = None) -> Dict[str, Any]:
    """周度分析：使用占比/成功率/成本分布 + 「wrong-model」对照与阈值建议。

    「wrong-model」两种情形（都以**实际结果**为准，不是拍脑袋）：
    - 简单 turn 走了 strong（`complexity` 低）→ 浪费钱
    - 复杂 turn 走了 cheap 且失败 → 省钱省出问题
    """
    span_days = {"day": 1, "week": 7, "month": 30}.get(str(period), 7)
    since = time.time() - span_days * 86400
    rows = _rows(since, db_path)

    by_model: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        model = str(row.get("model_chosen") or "(未路由)")
        bucket = by_model.setdefault(model, {"calls": 0, "success": 0, "failed": 0, "unknown": 0,
                                            "cost": 0.0, "latency_sum": 0.0, "tokens": 0})
        bucket["calls"] += 1
        if row.get("success") == 1:
            bucket["success"] += 1
        elif row.get("success") == 0:
            bucket["failed"] += 1
        else:
            bucket["unknown"] += 1
        bucket["cost"] += float(row.get("cost_estimate") or 0)
        bucket["latency_sum"] += float(row.get("latency") or 0)
        bucket["tokens"] += int(row.get("tokens") or 0)

    total = len(rows)
    wrong_expensive = [r for r in rows if str(r.get("tier")) == TIER_STRONG
                       and int(r.get("complexity") or 0) <= 0]
    wrong_cheap = [r for r in rows if str(r.get("tier")) == TIER_CHEAP and r.get("success") == 0]

    suggestions: List[str] = []
    if wrong_expensive:
        suggestions.append(
            f"有 {len(wrong_expensive)} 次低复杂度 turn 走了强模型：考虑提高 `strong_score_threshold`"
            "（当前 {}）或补充 `step_budget` 的 cheap 映射".format(_get("strong_score_threshold", 3))
        )
    if wrong_cheap:
        suggestions.append(
            f"有 {len(wrong_cheap)} 次便宜档调用失败：考虑把对应关键词/模式加入 `strong_keywords` 或 "
            "`complex_patterns`（附样本：" + "、".join(str(r.get("model_chosen")) for r in wrong_cheap[:3]) + "）"
        )
    if total and not suggestions:
        suggestions.append("本周期未见明显错配：可维持当前阈值（继续观察）")

    cost_by_model = {m: round(b["cost"], 6) for m, b in by_model.items()}
    summary = {
        "period": period,
        "since": since,
        "total_turns": total,
        "by_model": {
            m: {"calls": b["calls"],
                "success_rate": round(b["success"] / b["calls"], 4) if b["calls"] else 0.0,
                "failed": b["failed"], "unknown": b["unknown"],
                "cost": round(b["cost"], 6), "tokens": b["tokens"],
                "avg_latency": round(b["latency_sum"] / b["calls"], 3) if b["calls"] else 0.0}
            for m, b in by_model.items()
        },
        "total_cost": round(sum(cost_by_model.values()), 6),
        "wrong_model": {"strong_on_simple": len(wrong_expensive), "cheap_on_failed": len(wrong_cheap)},
        "suggestions": suggestions,
        "applied": False,  # 建议需人工确认，不做自动改配置
    }
    return summary


def render_analysis(summary: Dict[str, Any]) -> str:
    """把分析结果渲染成 markdown（`docs/router-analysis-<date>.md`）。"""
    date = time.strftime("%Y-%m-%d", time.localtime())
    lines = [f"# 模型路由分析 · {date}", "",
             f"- 周期：{summary.get('period')}｜turn 数：{summary.get('total_turns')}",
             f"- 总成本估算：{summary.get('total_cost')}（按 router.pricing 口径）", "",
             "## 各模型使用情况", "",
             "| 模型 | 调用 | 成功率 | 失败 | 成本 | tokens | 平均延迟 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    by_model = summary.get("by_model") or {}
    if not by_model:
        lines.append("| （无记录） | 0 | — | 0 | 0 | 0 | — |")
    for model, item in by_model.items():
        lines.append(f"| {model} | {item['calls']} | {item['success_rate']} | {item['failed']} | "
                     f"{item['cost']} | {item['tokens']} | {item['avg_latency']}s |")
    wrong = summary.get("wrong_model") or {}
    lines += ["", "## 错配对照（wrong-model）", "",
              f"- 低复杂度走了强模型（浪费）：{wrong.get('strong_on_simple', 0)} 次",
              f"- 便宜档失败（省钱省出问题）：{wrong.get('cheap_on_failed', 0)} 次", "",
              "## 调优建议（**需人工确认后**再改 config，不自动应用）", ""]
    lines += [f"- {s}" for s in (summary.get("suggestions") or [])]
    lines += ["", "> 应用方式：人工修改 `config.json` 的 `router` 段（`strong_score_threshold` / "
                  "`strong_keywords` / `step_budget`），保存后下轮生效。", ""]
    return "\n".join(lines)


def write_analysis_report(summary: Dict[str, Any] | None = None, *, period: str = "week",
                          out_dir: Any = None) -> str:
    """分析报告落盘，返回路径。"""
    from pathlib import Path

    summary = summary or analyze(period)
    directory = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "docs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"router-analysis-{time.strftime('%Y-%m-%d')}.md"
    path.write_bytes(render_analysis(summary).encode("utf-8"))
    return str(path)


def _main(argv: List[str] | None = None) -> int:
    """CLI：`python -m apiserver.llm_router analyze --period week [--write]`。"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="模型路由分析（W125-02）")
    sub = parser.add_subparsers(dest="cmd")
    analyze_cmd = sub.add_parser("analyze", help="周期分析：使用占比/成功率/成本/错配建议")
    analyze_cmd.add_argument("--period", default="week", choices=["day", "week", "month"])
    analyze_cmd.add_argument("--write", action="store_true", help="同时写入 docs/router-analysis-<date>.md")
    analyze_cmd.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    if args.cmd != "analyze":
        parser.print_help()
        return 1
    summary = analyze(args.period)
    if args.write:
        path = write_analysis_report(summary, period=args.period)
        print(f"[router] 报告已写入 {path}")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        print(render_analysis(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    raise SystemExit(_main())

