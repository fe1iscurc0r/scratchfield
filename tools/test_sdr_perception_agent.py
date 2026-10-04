"""sdr_perception_agent 测试（A30 验收：决策正确率 ≥75% + 结构化信用可视化）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sdr_perception_agent import (
    SDRPerceptionAgent,
    evaluate,
    make_samples,
    run_training,
    true_band,
    true_mode,
)


def test_decision_accuracy_meets_75pct():
    agent = SDRPerceptionAgent()
    train = make_samples(agent.bw_bins, agent.off_bins, seed=0)
    test = make_samples(agent.bw_bins, agent.off_bins, seed=1)
    run_training(agent, train, seed=2)
    assert evaluate(agent, test) >= 0.75


def test_training_improves_accuracy():
    agent = SDRPerceptionAgent()
    test = make_samples(agent.bw_bins, agent.off_bins, seed=1)
    before = evaluate(agent, test)
    run_training(agent, make_samples(agent.bw_bins, agent.off_bins, seed=0), seed=2)
    after = evaluate(agent, test)
    assert after > before


def test_structured_credit_two_subchecks():
    """VICT 核心：信用按「特征 × 子判决」结构化追溯，含模式与频段两个子判决。"""
    agent = SDRPerceptionAgent()
    run_training(agent, make_samples(agent.bw_bins, agent.off_bins, seed=0), seed=2)
    subchecks = {sc for (_, _, sc) in agent.credit}
    assert {"mode", "band"} <= subchecks
    viz = agent.visualize_credit()
    assert "mode" in viz and "band" in viz


def test_true_rules_deterministic():
    for bw in range(2):
        for off in range(4):
            assert true_mode(bw, off) == true_mode(bw, off)
            assert true_band(off) == true_band(off)
