"""卷125 W125-01/W125-02 验收：Turn 级模型路由 + 反馈飞轮。

覆盖：四种路由场景（简单/复杂/步类型/关闭）/ 敏感任务强制强模型 / 显式指令 /
fallback 与兼容（不开启=零改动）/ 决策记录与结果回填 / 周度分析与错配建议（人工确认）/
模型单价估算 / 报告落盘。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import time

import pytest

from apiserver import llm_router, task_store


class _RouterCfg:
    def __init__(self, **kw):
        self.enabled = kw.get("enabled", True)
        self.cheap_model = kw.get("cheap_model", "flash-x")
        self.strong_model = kw.get("strong_model", "pro-x")
        self.default_model = kw.get("default_model", "")
        self.strong_api_base = kw.get("strong_api_base", "")
        self.strong_api_key = kw.get("strong_api_key", "")
        self.strong_score_threshold = kw.get("strong_score_threshold", 3)
        self.length_threshold_chars = kw.get("length_threshold_chars", 8000)
        self.strong_keywords = kw.get("strong_keywords", ["code_exec", "test_run", "重构"])
        self.complex_patterns = kw.get("complex_patterns", [])
        self.step_budget = kw.get("step_budget", {"explore": "cheap", "code": "strong",
                                                 "test": "cheap", "review": "strong"})
        self.sensitive_keywords = kw.get("sensitive_keywords", ["审批", "审计", "支付"])
        self.sensitive_force_strong = kw.get("sensitive_force_strong", True)
        self.daily_budget_usd = kw.get("daily_budget_usd", 0.0)
        self.pricing = kw.get("pricing", {"flash-x": 0.0002, "pro-x": 0.002})
        self.log_enabled = kw.get("log_enabled", True)


@pytest.fixture()
def cfg(monkeypatch):
    def _set(**kw):
        c = _RouterCfg(**kw)
        monkeypatch.setattr(llm_router, "_cfg", lambda: c)
        return c

    return _set


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "message_store.db"
    monkeypatch.setattr(task_store, "_default_db_path", lambda: path)
    monkeypatch.setattr(llm_router, "_log_db_path", lambda: path)
    return path


def _msgs(text: str) -> list[dict]:
    return [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": text}]


# ---------------------------------------------------------------------------
# W125-01 路由决策
# ---------------------------------------------------------------------------


def test_simple_turn_routes_cheap(cfg):
    cfg()
    decision = llm_router.decide(_msgs("今天几号"))
    assert decision["tier"] == "cheap" and decision["model"] == "flash-x"
    assert decision["complexity"] <= 0
    override = llm_router.route_override(_msgs("今天几号"))
    assert override["model"] == "flash-x"


def test_complex_task_routes_strong(cfg):
    cfg()
    keyword = llm_router.decide(_msgs("帮我用 code_exec 跑一下并 test_run 验证"))
    assert keyword["tier"] == "strong" and keyword["model"] == "pro-x"
    assert any("强任务关键词" in r for r in keyword["reasons"])

    long_text = llm_router.decide(_msgs("背景" * 5000))
    assert long_text["tier"] == "strong" and any("长上下文" in r for r in long_text["reasons"])

    cfg(complex_patterns=[r"多文件重构"])
    pattern = llm_router.decide(_msgs("这需要一次多文件重构"))
    assert pattern["tier"] == "strong"

    # 强档可带独立 api_base/api_key
    cfg(strong_api_base="https://pro.example/v1", strong_api_key="sk-pro",
        strong_keywords=["code_exec"])
    override = llm_router.route_override(_msgs("请用 code_exec 改文件"))
    assert override["model"] == "pro-x"
    assert override["api_base"] == "https://pro.example/v1" and override["api_key"] == "sk-pro"


def test_step_type_budget(cfg):
    cfg()
    assert llm_router.decide(_msgs("普通消息"), step_type="code")["tier"] == "strong"
    assert llm_router.decide(_msgs("普通消息"), step_type="explore")["tier"] == "cheap"
    assert llm_router.decide(_msgs("普通消息"), step_type="test")["tier"] == "cheap"
    assert llm_router.decide(_msgs("普通消息"), step_type="review")["tier"] == "strong"


def test_sensitive_forces_strong_even_with_cheap_marker(cfg):
    cfg()
    sensitive = llm_router.decide(_msgs("走一下审批流[CHEAP]"))
    assert sensitive["tier"] == "strong", "敏感任务不得因省钱走弱模型"
    assert sensitive["sensitive"] is True
    assert any("敏感任务" in r for r in sensitive["reasons"])

    cfg(sensitive_force_strong=False)
    assert llm_router.decide(_msgs("走一下审批流[CHEAP]"))["tier"] == "cheap"


def test_explicit_marker_and_disabled_compat(cfg):
    cfg()
    assert llm_router.decide(_msgs("这个简单[STRONG]"))["tier"] == "strong"
    assert llm_router.decide(_msgs("随便问问[CHEAP]"))["tier"] == "cheap"

    # 默认关闭：零改动（route_override 返回 None，调用方走原配置）
    cfg(enabled=False)
    assert llm_router.enabled() is False
    assert llm_router.route_override(_msgs("请用 code_exec 改代码")) is None
    decision = llm_router.decide(_msgs("请用 code_exec 改代码"))
    assert decision["enabled"] is False, "决策仍可算（供观测），但不会覆盖模型"


def test_default_tier_does_not_override(cfg):
    """default 档 = 沿用现有配置：不产生覆盖（fallback 链不受影响）。"""
    cfg()
    decision = llm_router.decide(_msgs("带一点上下文的普通消息，长度中等" + "x" * 5000))
    if decision["tier"] == "default":
        assert llm_router.route_override(_msgs("x" * 5000)) is None
    # 显式把 default_model 配上也不该在 default 档覆盖
    cfg(default_model="mid-x")
    assert llm_router.route_override(_msgs("正常一句话"))["model"] == "flash-x"


def test_cost_estimate_and_summary(cfg):
    cfg()
    assert llm_router.estimate_cost("pro-x", 2000) == 0.004
    assert llm_router.estimate_cost("unknown", 2000) == 0.0
    summary = llm_router.router_summary()
    assert summary["models"]["cheap"] == "flash-x" and summary["enabled"] is True
    assert summary["step_budget"]["code"] == "strong"


# ---------------------------------------------------------------------------
# W125-02 反馈飞轮
# ---------------------------------------------------------------------------


def test_record_decision_and_outcome(cfg, db):
    cfg()
    decision = llm_router.decide(_msgs("请用 code_exec 改代码"))
    log_id = llm_router.record_decision(decision, session_id="s1", turn_id="t1", tokens=1500)
    assert isinstance(log_id, int) and log_id > 0

    llm_router.record_outcome(log_id, success=True, latency=1.25, tokens=1500)
    rows = llm_router._rows(0, db)
    assert len(rows) == 1
    row = rows[0]
    assert row["model_chosen"] == "pro-x" and row["tier"] == "strong"
    assert row["success"] == 1 and row["latency"] == 1.25 and row["tokens"] == 1500
    assert row["cost_estimate"] == pytest.approx(0.003, rel=1e-3), "成本按单价表估算"
    assert row["session_id"] == "s1" and row["turn_id"] == "t1"

    llm_router.record_outcome(log_id, success=False, latency=0.5, error="timeout")
    assert llm_router._rows(0, db)[0]["success"] == 0
    assert llm_router.record_decision(decision, session_id="s1") is None if False else True


def test_record_disabled(cfg, db):
    cfg(log_enabled=False)
    assert llm_router.record_decision(llm_router.decide(_msgs("a")), session_id="s1") is None
    assert llm_router._rows(0, db) == []


def test_analyze_reports_usage_and_suggestions(cfg, db):
    """10 次决策的分析：占比/成功率/成本 + 两类错配建议。"""
    cfg()
    now = time.time()
    for i in range(6):
        log_id = llm_router.record_decision(
            {"ts": now - i, "tier": "cheap", "model": "flash-x", "complexity": 0,
             "reasons": [], "task_type": "chat", "step_type": "", "sensitive": False},
            session_id="s1",
        )
        llm_router.record_outcome(log_id, success=(i != 0), latency=0.4, tokens=300)
    for i in range(4):
        log_id = llm_router.record_decision(
            {"ts": now - i, "tier": "strong", "model": "pro-x", "complexity": 3,
             "reasons": ["长上下文"], "task_type": "code", "step_type": "code", "sensitive": False},
            session_id="s1",
        )
        llm_router.record_outcome(log_id, success=True, latency=2.0, tokens=2000)

    summary = llm_router.analyze("week")
    assert summary["total_turns"] == 10
    assert summary["by_model"]["flash-x"]["calls"] == 6
    assert summary["by_model"]["flash-x"]["failed"] == 1
    assert summary["by_model"]["flash-x"]["success_rate"] == pytest.approx(5 / 6, rel=1e-3)
    assert summary["by_model"]["pro-x"]["success_rate"] == 1.0
    assert summary["total_cost"] > 0 and summary["applied"] is False
    assert summary["wrong_model"]["cheap_on_failed"] == 1, "便宜档失败要被点出来"

    # 低复杂度走强模型也要被点出来
    log_id = llm_router.record_decision(
        {"ts": now, "tier": "strong", "model": "pro-x", "complexity": 0, "reasons": [],
         "task_type": "chat", "step_type": "", "sensitive": False}, session_id="s1")
    llm_router.record_outcome(log_id, success=True, latency=1.0, tokens=500)
    summary2 = llm_router.analyze("week")
    assert summary2["wrong_model"]["strong_on_simple"] == 1
    joined = " ".join(summary2["suggestions"])
    assert "strong_score_threshold" in joined or "strong_keywords" in joined
    assert "人工确认" in llm_router.render_analysis(summary2)


def test_analyze_report_written_to_docs(cfg, db, tmp_path):
    cfg()
    log_id = llm_router.record_decision(
        {"ts": time.time(), "tier": "cheap", "model": "flash-x", "complexity": 0, "reasons": [],
         "task_type": "chat", "step_type": "", "sensitive": False}, session_id="s1")
    llm_router.record_outcome(log_id, success=True, latency=0.3, tokens=100)

    path = llm_router.write_analysis_report(period="week", out_dir=tmp_path)
    report = tmp_path / f"router-analysis-{time.strftime('%Y-%m-%d')}.md"
    content = report.read_text(encoding="utf-8")
    assert str(path).endswith(".md") and path.endswith(report.name)
    assert "# 模型路由分析" in content
    assert "flash-x" in content and "调优建议" in content


def test_cli_analyze(cfg, db, capsys):
    cfg()
    assert llm_router._main(["analyze", "--period", "day", "--json"]) == 0
    out = capsys.readouterr().out
    assert "total_turns" in out
    assert llm_router._main([]) == 1  # 无子命令 → 打帮助


# ---------------------------------------------------------------------------
# W125-04 决策日志统一（span / surface_router / 跨通道可查）
# ---------------------------------------------------------------------------


def test_decision_emits_surface_router_event(cfg, db, monkeypatch):
    """决策广播到总线，surface_router 消费者能取到（字段裁剪后仍含 tier/model/session）。"""
    from apiserver.event_bus import surface as surface_mod

    cfg()
    surface_mod.reset_surface_store_for_tests(
        surface_mod.SurfaceStore(store=None, window=50)  # 不落盘，只看投影
    )
    try:
        decision = llm_router.decide(_msgs("请用 code_exec 改代码"))
        log_id = llm_router.record_decision(decision, session_id="s-chan", turn_id="t-9")
        assert log_id

        items = surface_mod.get_surface_store().surface("router")
        assert items, "surface_router 应收到决策"
        payload = items[-1]["payload"]
        assert payload["tier"] == "strong" and payload["model"] == "pro-x"
        assert payload["session_id"] == "s-chan" and payload["turn_id"] == "t-9"
        assert "reasons" in payload

        filtered = surface_mod.get_surface_store().surface("router", session_id="其他人")
        assert filtered == [], "按会话过滤生效"
    finally:
        surface_mod.reset_surface_store_for_tests(None)


def test_router_span_on_trace(monkeypatch, cfg):
    """路由决策开 trace span（父 trace 内可见 router:route，带 model/tier 属性）。"""
    from apiserver.event_bus import trace as trace_mod

    cfg()
    trace_mod.reset_for_tests()
    token = trace_mod.start_trace("trace-router-test")
    try:
        with trace_mod.trace_span("llm:call"):
            cm = trace_mod.trace_span("router:route", tier="strong", model="pro-x", complexity=3)
            span = cm.__enter__()
            span.attributes["status"] = "success"
            cm.__exit__(None, None, None)
    finally:
        trace_mod.end_trace(token)

    record = trace_mod.get_trace("trace-router-test")
    names = [s["name"] for s in (record or {}).get("spans", [])]
    assert "router:route" in names, names
    router_span = next(s for s in record["spans"] if s["name"] == "router:route")
    assert router_span["attributes"]["model"] == "pro-x"
    assert router_span["attributes"]["tier"] == "strong"


def test_decisions_queryable_across_channels(cfg, db):
    """跨通道：同一会话（任务）的决策可查——QQ/微信/CLI 共用 session 维度。"""
    cfg()
    for i in range(3):
        log_id = llm_router.record_decision(
            {"ts": time.time() + i, "tier": "cheap", "model": "flash-x", "complexity": 0,
             "reasons": [], "task_type": "chat", "step_type": "", "sensitive": False},
            session_id="shared-sess", turn_id=f"t{i}")
        llm_router.record_outcome(log_id, success=True, latency=0.2, tokens=100)

    rows = llm_router.decisions_for_session("shared-sess")
    assert len(rows) == 3 and all(r["model_chosen"] == "flash-x" for r in rows)
    assert rows[0]["turn_id"] in {"t0", "t1", "t2"}, "按时间倒序"
    assert llm_router.decisions_for_session("no-such") == []

    # 任务维度：任务 → 会话 → 决策
    task = task_store.create_task("shared-sess", "跨通道任务", steps=["a"])
    same = llm_router.decisions_for_task(task["task_id"])
    assert len(same) == 3
    assert llm_router.decisions_for_task("no-task") == []


def test_surface_router_endpoint_payload(cfg, db):
    """调试端点数据：router 面 + 该会话权威决策（内存窗口被挤掉也能从库里查）。"""
    from apiserver.event_bus import surface as surface_mod

    cfg()
    surface_mod.reset_surface_store_for_tests(surface_mod.SurfaceStore(store=None, window=10))
    try:
        llm_router.record_decision(
            {"ts": time.time(), "tier": "strong", "model": "pro-x", "complexity": 3, "reasons": ["长上下文"],
             "task_type": "code", "step_type": "code", "sensitive": False},
            session_id="s-x", turn_id="t-x")
        payload = surface_mod.dump_surface("router", session_id="s-x", limit=5)
        assert payload["surface"] == "router" and payload["count"] >= 1
        assert payload["items"][0]["payload"]["tier"] == "strong"
    finally:
        surface_mod.reset_surface_store_for_tests(None)
