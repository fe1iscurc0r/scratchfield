"""longpi_bench 测试（S24 验收：≥4 场景 + 防御真实成功率报告）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from longpi_bench import (
    DEFENSES,
    INJECTIONS,
    SCENARIOS,
    make_context,
    run_benchmark,
    summarize,
)


def test_at_least_four_scenarios():
    assert len(SCENARIOS) >= 4


def test_direct_injection_detected_high():
    """直接注入应被关键词/模式防御高检出。"""
    ctx = make_context(INJECTIONS["direct"], "mid")
    assert DEFENSES["keyword_blacklist"](ctx) is True
    assert DEFENSES["imperative_pattern"](ctx) is True


def test_paraphrased_injection_evades():
    """语义改写注入绕过关键词/模式防御——LongPIBench 的核心发现。"""
    ctx = make_context(INJECTIONS["paraphrased"], "mid")
    assert DEFENSES["keyword_blacklist"](ctx) is False
    assert DEFENSES["imperative_pattern"](ctx) is False


def test_benchmark_report_shows_defense_degradation():
    """聚合报告：改写注入相对直接注入，检出率应显著下降（防御被高估）。"""
    agg = summarize(run_benchmark(seed=0))
    for d in DEFENSES:
        assert agg[d]["direct"] >= 0.5, f"{d} 对直接注入检出率过低"
        assert agg[d]["paraphrased"] < agg[d]["direct"], f"{d} 对改写注入未退化"
