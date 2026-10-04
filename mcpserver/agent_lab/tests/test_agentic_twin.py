"""A46 AgenticTwin 数字孪生异常检测测试：F1 门限 / 查询解析 / 确定性。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.agentic_twin import (
    answer_query,
    evaluate,
    ewma_detect,
    synthesize_telemetry,
)


def test_detection_f1_above_threshold():
    r = evaluate(n=600, seed=5)
    assert r["f1"] >= 0.8


def test_query_parsing_hits_metrics():
    r = evaluate(n=600, seed=5)
    assert "温度" in r["q_temp"] and "°C" in r["q_temp"]
    assert "异常" in r["q_anom"]
    assert answer_query(None, None, "unknown metric query") == "不支持的查询指标"  # type: ignore[arg-type]


def test_detect_flags_injected_spikes():
    x, truth = synthesize_telemetry(n=400, seed=1)
    flags = ewma_detect(x)
    assert flags[truth].sum() >= truth.sum() * 0.7  # 至少召回七成注入异常（相邻尖峰会抬高方差基线）


def test_telemetry_deterministic():
    x1, t1 = synthesize_telemetry(n=200, seed=9)
    x2, t2 = synthesize_telemetry(n=200, seed=9)
    assert (x1 == x2).all() and (t1 == t2).all()
