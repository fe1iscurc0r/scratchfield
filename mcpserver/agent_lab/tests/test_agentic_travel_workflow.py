"""A40 三 Agent 旅行行为工作流测试：闭环准确率 / 特征维 / 可复现。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.agentic_travel_workflow import (
    CollectionAgent,
    StructuringAgent,
    evaluate,
)


def test_pipeline_beats_majority_baseline():
    r = evaluate(n_per_mode=60, seed=7)
    assert r["accuracy"] > r["majority_baseline"] + 0.3  # 显著超越多数类基线
    assert r["accuracy"] >= 0.9


def test_structuring_feature_dim():
    s = StructuringAgent()
    v = s.transform("航班 登机 3小时")
    assert v.shape[0] == s.dim == 23  # 4 方式×5 词 + 3 类辅助词


def test_collection_deterministic():
    a = CollectionAgent(n_per_mode=10, seed=4).collect()
    b = CollectionAgent(n_per_mode=10, seed=4).collect()
    assert a == b
    assert len(a) == 40


def test_evaluate_reproducible():
    assert evaluate(seed=3)["accuracy"] == evaluate(seed=3)["accuracy"]
