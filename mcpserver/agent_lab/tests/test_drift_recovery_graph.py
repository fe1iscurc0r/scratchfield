"""A45 漂移恢复图测试：小模型决策表胜过随机 / 映射正确 / 未知回退。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.drift_recovery_graph import (
    evaluate,
    slm_decide,
)


def test_slm_beats_random_policy():
    r = evaluate(seed=3, n_episodes=400)
    assert r["better"]
    assert r["slm_recovery"] > r["random_recovery"]
    assert r["slm_recovery"] >= 0.8  # 决策表接近各签名最优动作


def test_slm_mapping_correct():
    assert slm_decide("auth_expired") == "renew_token"
    assert slm_decide("rate_limited") == "backoff_wait"


def test_unknown_signature_falls_back_to_retry():
    assert slm_decide("totally_new_error") == "retry"


def test_evaluate_reproducible():
    assert evaluate(seed=8)["slm_recovery"] == evaluate(seed=8)["slm_recovery"]
