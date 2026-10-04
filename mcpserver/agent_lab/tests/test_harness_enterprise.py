"""A48 Harness 企业级凭证授权测试：决策矩阵 / 审计留痕 / 最小权限。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.harness_enterprise import (
    Credential,
    Harness,
    PolicyEngine,
    evaluate,
)


def test_decision_matrix_all_correct():
    r = evaluate()
    assert r["wrong"] == 0
    assert r["n_cases"] == 6
    assert r["audit_len"] == 6  # 每次决策必留审计


def test_least_privilege_denies_overreach():
    h = Harness(PolicyEngine())
    cred = Credential("agent-x", frozenset({"docs.read"}))
    out = h.invoke(cred, "deploy")
    assert out["blocked"] and out["reason"] == "作用域不足"


def test_expired_credential_denied_even_with_scope():
    h = Harness(PolicyEngine())
    cred = Credential("agent-y", frozenset({"ops.deploy"}), expires_at=5.0)
    assert h.invoke(cred, "deploy", now=6.0)["blocked"]
    assert not h.invoke(cred, "deploy", now=4.0)["blocked"]


def test_unknown_action_denied():
    h = Harness(PolicyEngine())
    cred = Credential("agent-z", frozenset({"docs.read", "ops.deploy"}))
    out = h.invoke(cred, "drop_table")
    assert out["blocked"] and out["reason"] == "未知动作"
