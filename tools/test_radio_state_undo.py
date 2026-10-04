"""radio_state_undo 测试（A31 验收：模拟参数变更回滚正确率 ≥95%）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from radio_state_undo import RadioController, build_radio, simulate


def test_undo_restores_tracked_params_exactly():
    radio = build_radio(10, seed=0)
    snapshot = dict(radio.state)
    radio.set("p0", 123.0)
    radio.set("p1", 456.0)
    radio.undo(2)
    assert radio.state["p0"] == snapshot["p0"]
    assert radio.state["p1"] == snapshot["p1"]


def test_rollback_correctness_meets_95pct():
    result = simulate(n_params=40, n_changes=30, seed=0)
    assert result["correctness"] >= 0.95


def test_blind_param_not_restored():
    """盲点参数（未接地）旧值丢失，回滚后残留不精确——对应 EvoUndo 非 100% 恢复。"""
    result = simulate(n_params=10, n_changes=5, seed=0)
    bad = [k for k, v in result["snapshot"].items() if result["state"].get(k) != v]
    assert bad == ["p9"]  # 唯一的盲点参数


def test_snapshot_restore_exact():
    """精确状态接地：快照 + 直接恢复应完全一致（区别于盲点的日志回滚）。"""
    radio = build_radio(10, seed=0)
    snap = radio.snapshot()
    radio.set("p0", 999.0)
    radio.set("p1", 888.0)
    radio.set("p9", 777.0)  # 盲点参数也改
    radio.restore(snap)
    assert radio.state == snap  # 快照恢复连盲点参数也精确恢复
    assert radio.undo_log == []
