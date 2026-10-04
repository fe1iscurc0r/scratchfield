"""comm_degradation_curriculum 测试（A22 验收：50% 丢包下课程提升 ≥20%）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from comm_degradation_curriculum import (
    RedundancyAgent,
    curriculum_train,
    evaluate,
    train,
)


def test_curriculum_improves_at_50pct_dropout():
    baseline = RedundancyAgent()
    train(baseline, 0.0, steps=6000, seed=0)

    curriculum = RedundancyAgent()
    curriculum_train(curriculum, seed=0)

    base_sr = evaluate(baseline, 0.5)
    cur_sr = evaluate(curriculum, 0.5)
    assert cur_sr - base_sr >= 0.20, (
        f"课程提升不足：{cur_sr:.3f} - {base_sr:.3f} = {cur_sr - base_sr:.3f}（要求 ≥0.20）"
    )


def test_curriculum_learns_higher_redundancy():
    baseline = RedundancyAgent()
    train(baseline, 0.0, steps=6000, seed=0)
    curriculum = RedundancyAgent()
    curriculum_train(curriculum, seed=0)
    assert curriculum.greedy() > baseline.greedy()
