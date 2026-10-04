"""W58-01 验收测试：ESP32 无源唤醒节点模拟（≥5 用例）。

运行：python -m pytest tools/test_wur_node.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from wur_node import WurNode, energy_budget_ok, simulate, survival_days


def test_phase_drift_compensation_restores_sync():
    """相位漂移 → 补偿后残余误差大幅缩小（保持同步）。"""
    node = WurNode(rtc_drift_ppm=20.0, comp_accuracy=0.95)
    drift = node.phase_drift_s(3600.0)  # 1 小时漂移
    residual = node.compensate(drift)
    assert residual < drift
    assert residual < 0.1 * drift  # 补偿掉 >90% 漂移


def test_residual_after_cycle_small():
    """一个唤醒周期后残余同步误差足够小（µs 量级）。"""
    node = WurNode()
    residual = node.residual_after_cycle()
    assert residual < 1e-3  # < 1 ms


def test_energy_accounting_scales_with_wakeups():
    """能耗随唤醒次数线性增长。"""
    node = WurNode()
    node.wake(100)
    e100 = node.energy_used_j()
    node.wake(100)
    e200 = node.energy_used_j()
    assert e200 > e100
    assert abs(e200 / e100 - 2.0) < 1e-9


def test_survival_days_positive_and_finite():
    """mock 电池容量下能算出理论存活天数（正、有限、合理量级）。"""
    node = WurNode(battery_mah=220.0)
    days = survival_days(node)
    assert days > 0 and np_isfinite(days)
    assert days > 30  # 低占空比节点至少存活数月


def test_energy_budget_within_battery():
    """30 天模拟能耗不超电池容量（能量预算成立）。"""
    node = WurNode(battery_mah=220.0)
    simulate(node, days=30.0)
    assert energy_budget_ok(node)


def test_higher_wake_rate_shorter_survival():
    """唤醒越频繁，存活天数越短。"""
    slow = WurNode(wake_interval_s=60.0)
    fast = WurNode(wake_interval_s=10.0)
    assert survival_days(slow) > survival_days(fast)


def np_isfinite(x):
    import numpy as np
    return bool(np.isfinite(x))
