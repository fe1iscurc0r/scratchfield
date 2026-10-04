"""edge_selfheal_probe 验收硬线（卷102 W102-05）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.edge_selfheal_probe import EdgeSelfHeal  # noqa: E402


def test_healthy_no_recovery():
    """全项健康：保持 NORMAL，不触发任何恢复动作。"""
    heal = EdgeSelfHeal(failure_threshold=3)
    heal.register("cpu", lambda: True)
    heal.register("mem", lambda: True)
    r = heal.evaluate(now=1.0)
    assert r["state"] == "NORMAL" and r["failed_checks"] == []
    assert r["restart_count"] == 0 and heal.summary()["decisions"] == []


def test_threshold_triggers_recovery():
    """连续失败达阈值触发恢复：重启计数 +1、状态入 RECOVERING、决策留痕。"""
    heal = EdgeSelfHeal(failure_threshold=3)
    fail = [False]
    heal.register("uplink", lambda: fail[0])
    for i in range(2):
        r = heal.evaluate(now=float(i))
        assert r["state"] == "UNHEALTHY" and r["restart_count"] == 0
    r = heal.evaluate(now=2.0)   # 第 3 次连续失败 → 触发
    assert r["state"] == "RECOVERING" and r["restart_count"] == 1
    s = heal.summary()
    assert s["decisions"] == [("uplink", "restart_process", 2.0)]


def test_recovery_success_returns_normal():
    """恢复动作生效后回到 NORMAL；恢复成功后再次故障重新计数。"""
    heal = EdgeSelfHeal(failure_threshold=2)
    ok = [False]
    heal.register("disk", lambda: ok[0])
    heal.evaluate(now=1.0)
    heal.evaluate(now=2.0)        # 达到阈值 → RECOVERING（重启磁盘守护）
    assert heal.state == "RECOVERING" and heal.restart_count == 1
    ok[0] = True
    r = heal.evaluate(now=3.0)
    assert r["state"] == "NORMAL" and r["consecutive_failures"] == 0
    # 再次故障：从零开始连续计数，第二次失败再次恢复
    ok[0] = False
    heal.evaluate(now=4.0)
    r = heal.evaluate(now=5.0)
    assert r["state"] == "RECOVERING" and heal.restart_count == 2
    # 异常抛出的检查视同失败
    heal.register("broken", lambda: 1 / 0)
    assert "broken" in heal.evaluate(now=6.0)["failed_checks"]