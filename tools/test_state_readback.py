"""W63-06 跨层状态读回确认验收测试

验收硬线：
- pytest 全绿 ≥ 4 用例
- 断言：读回确认能检出广播信任漏掉的不一致状态

测试覆盖：
1. 一致状态：A 声明 / B 读回相同 → 确认 ok=True
2. 不一致状态：A 声明 OOK / B 读回 GFSK → 确认 ok=False，广播信任漏检
3. 批量确认：多条状态混合一致/不一致 → 读回确认可识别所有不一致
4. 广播信任盲区：直接读不验证，值错也返回 None（无告警）
5. numpy 数组值：阵列频率计划等 numpy 值也能正确比对
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.rf_brain.state_readback import (
    BroadcastTrustPolicy,
    LayerRole,
    ReadbackConfirm,
    diagnose,
)


# --------------------------------------------------------------------------- #
# 用例 1：一致状态 → ok=True
# --------------------------------------------------------------------------- #
def test_consistent_state_readback_ok():
    """A 层声明调制方式=OOK，B 层读回也是 OOK → 确认 ok=True。"""
    confirm = ReadbackConfirm()
    confirm.declare(LayerRole.DECISION, "modulation", "OOK")
    result = confirm.readback_and_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        key="modulation",
        readback_value="OOK",
    )
    print(f"  一致状态：declared={result.declared_value!r} readback={result.readback_value!r} ok={result.ok}")
    assert result.ok is True, f"一致状态却返回 ok=False: {result.diff_description}"
    assert result.diff_description == ""


# --------------------------------------------------------------------------- #
# 用例 2：不一致状态 → ok=False，且广播信任漏检（关键验收）
# --------------------------------------------------------------------------- #
def test_inconsistent_state_detected_and_broadcast_misses():
    """A 层声明调制方式=OOK，B 层实际读回 GFSK。

    验收硬线：读回确认检出不一致（ok=False），且广播信任会漏掉。
    """
    key = "modulation"
    decision_value = "OOK"
    sensor_readback_value = "GFSK"  # 不一致

    # 读回确认
    confirm = ReadbackConfirm()
    confirm.declare(LayerRole.DECISION, key, decision_value)
    result = confirm.readback_and_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        key=key,
        readback_value=sensor_readback_value,
    )

    # 断言：读回确认能检出不一致
    assert result.ok is False, "不一致状态却返回 ok=True，漏检！"
    assert "OOK" in result.diff_description and "GFSK" in result.diff_description

    # 广播信任：只管写，不管验证，不一致不被发现
    bcast = BroadcastTrustPolicy()
    bcast.declare(LayerRole.DECISION, key, decision_value)
    bcast_value = bcast.read(LayerRole.EXECUTION, key, default=None)

    # 断言：广播信任不报错，不告警——这是它的盲区
    print(f"  广播信任读到: {bcast_value!r}（无告警，不一致被漏掉）")
    assert bcast_value == decision_value, "广播信任不应验证"
    assert result.ok is False, "读回确认应检出不一致"


# --------------------------------------------------------------------------- #
# 用例 3：批量确认——混合一致/不一致
# --------------------------------------------------------------------------- #
def test_bulk_confirm_mixed_consistent_inconsistent():
    """批量读回确认：modulation 一致，frequency 不一致，bandwidth 一致。"""
    confirm = ReadbackConfirm()
    confirm.declare(LayerRole.DECISION, "modulation", "FSK")
    confirm.declare(LayerRole.DECISION, "frequency_hz", 433_920_000)
    confirm.declare(LayerRole.DECISION, "bandwidth_hz", 125_000)

    results = confirm.bulk_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        readback_pairs=[
            ("modulation", "FSK"),          # 一致
            ("frequency_hz", 433_000_000),  # 不一致（偏移）
            ("bandwidth_hz", 125_000),     # 一致
        ],
    )

    assert len(results) == 3
    ok_list = [r.ok for r in results]
    print(f"  批量确认结果 ok=[{ok_list}]")
    assert ok_list == [True, False, True], (
        f"批量确认结果应为 [True, False, True]，实际: {ok_list}"
    )
    assert confirm.has_mismatch(results) is True, "应有至少一条不一致"


# --------------------------------------------------------------------------- #
# 用例 4：广播信任盲区——错误值也被信任，无告警
# --------------------------------------------------------------------------- #
def test_broadcast_trust_no_alert_on_wrong_value():
    """广播信任：即使声明值传错（如 frequency），执行层直接用也不告警。

    这正是需要「读回确认」的原因。
    """
    bcast = BroadcastTrustPolicy()
    key = "frequency_hz"
    wrong_value = 999_000_000  # 错误值

    bcast.declare(LayerRole.DECISION, key, wrong_value)
    read_value = bcast.read(LayerRole.EXECUTION, key, default=None)

    # 广播信任直接返回声明值，不做验证
    print(f"  广播信任：声明={wrong_value} 读回={read_value}（无告警）")
    assert read_value == wrong_value, "广播信任应直接返回声明值"


# --------------------------------------------------------------------------- #
# 用例 5：numpy 数组值比对
# --------------------------------------------------------------------------- #
def test_numpy_array_readback():
    """阵列频率计划（numpy 数组）也能正确比对。"""
    confirm = ReadbackConfirm()
    plan = np.array([433.92e6, 915.0e6, 2450.0e6])

    confirm.declare(LayerRole.DECISION, "freq_plan", plan)
    # 执行层读回时有一项偏移
    wrong_plan = np.array([433.0e6, 915.0e6, 2450.0e6])

    result = confirm.readback_and_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        key="freq_plan",
        readback_value=wrong_plan,
    )

    assert result.ok is False, "numpy 数组不一致应被检出"
    print(f"  numpy 数组比对：declared={plan} readback={wrong_plan} ok={result.ok}")


# --------------------------------------------------------------------------- #
# 用例 6（附加）：diagnose() 工具函数
# --------------------------------------------------------------------------- #
def test_diagnose_function():
    """diagnose() 返回广播信任 vs 读回确认的完整对比报告。"""
    d = diagnose(
        key="modulation",
        decision_value="GFSK",
        sensor_readback_value="OOK",  # 不一致
    )

    assert d["readback_confirm_ok"] is False, "读回确认应检出不一致"
    assert d["broadcast_missed"] is True, "广播信任应漏掉不一致"
    assert d["broadcast_trust_value"] == "GFSK"  # 广播信任返回声明值，无告警
    print(f"  diagnose: {d}")


# --------------------------------------------------------------------------- #
# 用例 7（附加）：多层角色区分
# --------------------------------------------------------------------------- #
def test_decision_vs_execution_role_distinction():
    """DECISION 层和 EXECUTION 层的状态存储严格隔离。"""
    confirm = ReadbackConfirm()

    # 决策层声明两个不同值
    confirm.declare(LayerRole.DECISION, "mode", "HANDOFF")
    confirm.declare(LayerRole.EXECUTION, "mode", "TRACKING")  # 执行层同时有自己的状态

    # 执行层读回决策层的状态
    result = confirm.readback_and_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        key="mode",
        readback_value="HANDOFF",
    )

    assert result.declared_value == "HANDOFF"
    assert result.readback_value == "HANDOFF"
    assert result.ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
