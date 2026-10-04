"""A57 意图条件上下文压缩测试：召回超头部截断 / 预算约束 / 空块安全。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.intent_conditioned_compression import (
    compress,
    evaluate,
    head_baseline,
    mock_context,
    score_chunks,
)


def test_intent_compression_beats_head_truncation():
    r = evaluate(seed=9, budget=0.3)
    assert r["recall_intent"] > r["recall_head"]
    assert r["recall_intent"] >= 0.8


def test_budget_respected_and_ordered():
    chunks, _ = mock_context(seed=9, n=40)
    kept = compress(chunks, "find deadlock", budget=0.3)
    assert len(kept) == 12
    assert kept == sorted(kept)  # 保持原顺序


def test_empty_chunk_safe():
    scores = score_chunks(["", "deadlock wait"], "deadlock")
    assert scores[0] == 0.0
    assert scores[1] > 0.0


def test_head_baseline_is_prefix():
    assert head_baseline(["a"] * 10, budget=0.3) == [0, 1, 2]
