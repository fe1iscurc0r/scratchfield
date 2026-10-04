"""LoRaCanary 模块管理器 Python 镜像自测（pytest，与 C++ 测试同语义）。

运行：python -m pytest tools/test_loracanary_module_manager.py -q
镜像 tools/loracanary_module_manager.py 对应 firmware/.../module_manager.{h,cpp}；
覆盖 5 场景（含回滚后隔离 QUARANTINED）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from loracanary_module_manager import (
    ACTIVE,
    FAILED,
    QUARANTINED,
    ROLLED_BACK,
    HardwareFeedback,
    ModuleDescriptor,
    ModuleManager,
    ModuleVersion,
)


def _rf_check(fb: HardwareFeedback) -> int:
    score = 100
    if not fb.power_ok:
        score -= 40
    if not fb.spi_ok:
        score -= 30
    if fb.rssi_dbm < -110:
        score -= 40
    return score


def _bme_check(fb: HardwareFeedback) -> int:
    return 90 if fb.i2c_ok else 10


def _bad_fb() -> HardwareFeedback:
    return HardwareFeedback(power_ok=False, spi_ok=False, rssi_dbm=-120)


def test_scenario1_rollback_on_consecutive_fail():
    mgr = ModuleManager()
    mgr.register_module(ModuleDescriptor(
        id="rf", active=ModuleVersion(1, 5, 0), prev=ModuleVersion(1, 4, 1),
        self_check=_rf_check, fail_threshold=3))
    for _ in range(2):
        mgr.run_health_check(_bad_fb())
        assert mgr.evaluate_and_rollback().rolled == []
    mgr.run_health_check(_bad_fb())
    d = mgr.evaluate_and_rollback()
    assert d.rolled == ["rf"]
    m = mgr.find("rf")
    assert m.state == ROLLED_BACK
    assert m.active == ModuleVersion(1, 4, 1)
    assert m.prev == ModuleVersion(1, 5, 0)
    assert m.consecutive_fails == 0 and m.epoch == 1


def test_scenario2_healthy_clears_fail_count():
    mgr = ModuleManager()
    mgr.register_module(ModuleDescriptor(
        id="bme", active=ModuleVersion(2, 0, 0), prev=ModuleVersion(1, 9, 1),
        self_check=_bme_check, fail_threshold=3))
    bad = HardwareFeedback(i2c_ok=False)
    mgr.run_health_check(bad)
    mgr.run_health_check(bad)
    mgr.run_health_check(HardwareFeedback())  # 一次合格清零
    mgr.run_health_check(bad)
    mgr.run_health_check(bad)
    d = mgr.evaluate_and_rollback()
    assert d.rolled == [] and d.quarantined == []
    m = mgr.find("bme")
    assert m.state == ACTIVE and m.consecutive_fails == 2


def test_scenario3_single_version_no_rollback():
    mgr = ModuleManager()
    v = ModuleVersion(1, 5, 0)
    mgr.register_module(ModuleDescriptor(
        id="rf", active=v, prev=v, self_check=_rf_check, fail_threshold=2))
    mgr.run_health_check(_bad_fb())
    mgr.run_health_check(_bad_fb())
    d = mgr.evaluate_and_rollback()
    assert d.rolled == []
    assert mgr.find("rf").state == FAILED


def test_scenario4_duplicate_register_no_overwrite():
    mgr = ModuleManager()
    mgr.register_module(ModuleDescriptor(
        id="rf", active=ModuleVersion(1, 5, 0), prev=ModuleVersion(1, 4, 1),
        self_check=_rf_check, fail_threshold=1))
    mgr.run_health_check(_bad_fb())
    mgr.evaluate_and_rollback()
    assert mgr.find("rf").state == ROLLED_BACK
    mgr.register_module(ModuleDescriptor(
        id="rf", active=ModuleVersion(9, 9, 0), prev=ModuleVersion(9, 8, 1),
        self_check=_rf_check))
    assert mgr.find("rf").active == ModuleVersion(1, 4, 1)  # 未被覆盖


def test_scenario5_rollback_then_quarantine():
    mgr = ModuleManager()
    mgr.register_module(ModuleDescriptor(
        id="rf", active=ModuleVersion(1, 5, 0), prev=ModuleVersion(1, 4, 1),
        self_check=_rf_check, fail_threshold=2))
    # 第一次失败 → 回滚
    mgr.run_health_check(_bad_fb())
    mgr.run_health_check(_bad_fb())
    first = mgr.evaluate_and_rollback()
    assert first.rolled == ["rf"] and first.quarantined == []
    assert mgr.find("rf").state == ROLLED_BACK
    # 回滚后仍失败 → 隔离
    mgr.run_health_check(_bad_fb())
    mgr.run_health_check(_bad_fb())
    second = mgr.evaluate_and_rollback()
    assert second.rolled == [] and second.quarantined == ["rf"]
    assert mgr.find("rf").state == QUARANTINED
    # 隔离后停止体检
    mgr.run_health_check(HardwareFeedback())
    assert mgr.find("rf").state == QUARANTINED
