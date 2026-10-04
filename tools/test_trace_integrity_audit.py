"""W60-01 验收测试：Trace Integrity 数据 Agent 审计（CAIT Rate）。"""
from __future__ import annotations

from tools.trace_integrity_audit import (
    AuditEvent,
    cait_rate,
    is_answer_correct,
    is_trace_valid,
    lineage_ancestors,
)


def _scenario() -> tuple[list[AuditEvent], list[AuditEvent], dict]:
    """构造血缘：read×2 → transform → aggregate → 三个答案（含一个 CAIT 案例）。"""
    e1 = AuditEvent("e1", "read", output_ref="data://a", value=10)
    e2 = AuditEvent("e2", "read", output_ref="data://b", value=20)
    e3 = AuditEvent("e3", "transform", inputs=["e1"], output_ref="data://c", value=11)
    e4 = AuditEvent("e4", "aggregate", inputs=["e1", "e2"], output_ref="data://d", value=30)
    # 答案1：正确 + 有效轨迹（引用真实祖先 c）
    a1 = AuditEvent("a1", "output", inputs=["e3"], cited_refs=["data://c"], value=11)
    # 答案2：正确 + 无效轨迹（引用不存在的 data://ghost）→ CAIT 案例
    a2 = AuditEvent("a2", "output", inputs=["e4"], cited_refs=["data://ghost"], value=30)
    # 答案3：错误（值 999 ≠ 真值 11）+ 有效轨迹 → 非 CAIT
    a3 = AuditEvent("a3", "output", inputs=["e3"], cited_refs=["data://c"], value=999)
    events = [e1, e2, e3, e4, a1, a2, a3]
    answers = [a1, a2, a3]
    ground_truth = {"a1": 11, "a2": 30, "a3": 11}
    return events, answers, ground_truth


def test_lineage_ancestors():
    events, _, _ = _scenario()
    anc = lineage_ancestors(events)
    by_id = {e.id: e for e in events}
    assert anc["e3"] == {"e3", "e1"}              # transform 祖先含 read e1
    assert anc["a1"] == {"a1", "e3", "e1"}        # answer1 祖先链
    assert "data://ghost" not in anc["a2"]


def test_is_trace_valid_true_and_false():
    events, _, _ = _scenario()
    by_id = {e.id: e for e in events}
    anc = lineage_ancestors(events)
    assert is_trace_valid(by_id["a1"], by_id, anc) is True    # 引用真实祖先
    assert is_trace_valid(by_id["a2"], by_id, anc) is False   # 引用幽灵数据


def test_is_answer_correct():
    _, answers, gt = _scenario()
    assert is_answer_correct(answers[0], gt) is True
    assert is_answer_correct(answers[2], gt) is False   # 值 999 ≠ 真值 11


def test_cait_rate_flags_correct_but_invalid():
    events, answers, gt = _scenario()
    r = cait_rate(answers, events, gt)
    assert r["total_answers"] == 3
    assert r["cait_count"] == 1
    assert r["invalid_trace_ids"] == ["a2"]        # 只有答案2是 CAIT
    assert abs(r["cait_rate"] - 1 / 3) < 1e-9


def test_cait_rate_empty_answers():
    assert cait_rate([], [], {})["cait_rate"] == 0.0
