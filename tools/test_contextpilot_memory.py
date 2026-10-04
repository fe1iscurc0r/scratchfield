"""contextpilot_memory 测试（A32 验收：内存占用降 ≥40%，决策质量不降）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from contextpilot_memory import ContextPilotAgent, FullHistoryAgent, compare


def test_memory_reduction_at_least_40pct():
    c = compare(stream_len=100, n_streams=50, seed=0)
    assert c["reduction"] >= 0.40, f"内存降 {c['reduction']*100:.1f}% 不达标"


def test_decision_quality_not_degraded():
    c = compare(stream_len=100, n_streams=50, seed=0)
    assert c["agreement"] == 1.0


def test_agents_agree_on_single_stream():
    stream = [0.1, 0.2, 0.95, 0.3, 0.8]
    fh, cp = FullHistoryAgent(), ContextPilotAgent()
    for x in stream:
        fh.observe(x)
        cp.observe(x)
    assert fh.decide(0.5, 0.9) == cp.decide(0.5, 0.9)


def test_contextpilot_memory_is_constant_ish():
    cp = ContextPilotAgent()
    for x in [0.5, 0.9, 0.3, 0.7, 0.2, 0.99, 0.1, 0.6]:
        cp.observe(x)
    assert cp.memory_usage() <= 3 + ContextPilotAgent.BRANCH_LIMIT
