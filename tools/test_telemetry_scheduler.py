"""工单255 任务A 的测试：四策略对比（离线、确定性、不联网）。

跑法（仓库根）：
    python -m pytest tools/test_telemetry_scheduler.py -q
"""
from __future__ import annotations

import pytest

from mcpserver.rf_workflow import telemetry_scheduler as ts


def test_four_policies_simulated() -> None:
    """四条策略都要出现且各自有指标。"""
    results = ts.simulate_all(ts.scarce_scenario())
    assert [m.policy for m in results] == list(ts.Policy.ALL)
    assert len(results) == 4


def test_metrics_complete_and_finite() -> None:
    """指标齐全；除 AoA 在"动作全缺电"时可为 NaN，其余都必须是有限值。"""
    for m in ts.simulate_all(ts.scarce_scenario()):
        d = m.as_dict()
        for key in ("avg_aoi_ticks", "avg_aoa_ticks", "aoii_violation_rate", "tx_count",
                    "total_energy_mj", "dropped_updates", "actions_taken", "energy_depleted_ticks"):
            assert key in d, f"{m.policy} 缺指标 {key}"
        assert d["avg_aoi_ticks"] >= 0
        assert 0.0 <= d["aoii_violation_rate"] <= 1.0
        assert d["tx_count"] >= 0 and d["total_energy_mj"] >= 0


def test_deterministic_bitwise() -> None:
    """固定种子下两次运行结果**逐位一致**（工单硬要求：确定性）。"""
    a = [m.as_dict() for m in ts.simulate_all(ts.scarce_scenario())]
    b = [m.as_dict() for m in ts.simulate_all(ts.scarce_scenario())]
    assert a == b


def test_trace_deterministic_and_bounded() -> None:
    trace = ts.generate_trace(ts.scarce_scenario())
    assert trace == ts.generate_trace(ts.scarce_scenario())
    assert all(0.0 <= v <= 1.0 for v in trace)
    # 事件注入后轨迹必须真的变化（否则"有新数据"恒假，对比无意义）
    assert max(trace) - min(trace) > 0.3


def test_scarce_gated_beats_periodic_and_aoi_threshold_on_aoii() -> None:
    """★ 工单硬断言 1：稀缺能量下 gated 的 AoII 违例率**严格低于** periodic 与 aoi_threshold。

    同时用两套口径都断言（动作侧 / 错误持续时间），避免"换个口径结论就翻"的脆弱性。
    """
    res = {m.policy: m for m in ts.simulate_all(ts.scarce_scenario())}
    gated = res[ts.Policy.AOA_ENERGY_GATED]
    for baseline in (ts.Policy.PERIODIC, ts.Policy.AOI_THRESHOLD):
        base = res[baseline]
        assert gated.aoii_violation_rate < base.aoii_violation_rate, (
            f"动作侧 AoII：gated={gated.aoii_violation_rate:.4f} 未严格低于 {baseline}="
            f"{base.aoii_violation_rate:.4f}")
        assert gated.extra["aoii_error_time_rate"] < base.extra["aoii_error_time_rate"], (
            f"错误持续时间 AoII：gated={gated.extra['aoii_error_time_rate']:.4f} 未严格低于 "
            f"{baseline}={base.extra['aoii_error_time_rate']:.4f}")
    # 机制自证：gated 的电省在"动作"上 —— 它一次动作都没因缺电而错过
    assert gated.extra["missed_actions"] == 0
    assert res[ts.Policy.PERIODIC].extra["missed_actions"] > 0


def test_abundant_aoii_converges() -> None:
    """工单断言 2 的一半（成立）：能量充裕时四策略的 AoII **收敛到同一水平**。"""
    rates = {m.policy: m.aoii_violation_rate for m in ts.simulate_all(ts.abundant_scenario())}
    assert len(set(rates.values())) == 1, f"充裕场景下 AoII 应一致，实测 {rates}"


def test_abundant_aoi_does_not_converge_tradeoff_is_real() -> None:
    """⚠️ 工单断言 2 的另一半（**不成立，如实锁定**）。

    工单原文写「能量充裕场景下三者的 **AoI** 差距收敛」。实测**不收敛**：
    充裕能量下 gated 依然只在"有新数据"时才发，AoI 明显高于 periodic ——
    这是该策略用 AoI 换能效的**取舍**，不是缺陷。

    本用例把这个事实钉住：任何人想靠调参让 AoI "看起来收敛"，都会在这里红。
    报告里已注明「未达标 + 差异 + 归属建议」（工单 §4 允许，禁止改断言变绿）。
    """
    res = {m.policy: m for m in ts.simulate_all(ts.abundant_scenario())}
    gated = res[ts.Policy.AOA_ENERGY_GATED]
    periodic = res[ts.Policy.PERIODIC]
    aoi_thresh = res[ts.Policy.AOI_THRESHOLD]
    assert gated.avg_aoi_ticks > periodic.avg_aoi_ticks * 2, "gated 的 AoI 取舍应当显著（>2×）"
    assert gated.avg_aoi_ticks > aoi_thresh.avg_aoi_ticks * 2
    assert periodic.avg_aoi_ticks < aoi_thresh.avg_aoi_ticks * 2   # 两条基线彼此接近


def test_should_send_policy_semantics() -> None:
    """决策函数的语义单测（纯函数，不走仿真）。"""
    sc = ts.scarce_scenario()
    # periodic：按周期
    assert ts._should_send(ts.Policy.PERIODIC, sc, sc.periodic_ticks, last_tx_t=0,
                           last_sent_value=0.0, current_value=0.0, has_new_data=False,
                           energy_ok=False) is True
    assert ts._should_send(ts.Policy.PERIODIC, sc, 1, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.0, has_new_data=False, energy_ok=False) is False
    # aoi_threshold：本地年龄超阈值
    assert ts._should_send(ts.Policy.AOI_THRESHOLD, sc, sc.aoi_threshold_ticks, last_tx_t=0,
                           last_sent_value=0.0, current_value=0.0, has_new_data=False,
                           energy_ok=False) is True
    assert ts._should_send(ts.Policy.AOI_THRESHOLD, sc, 1, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.0, has_new_data=False, energy_ok=False) is False
    # gated：新数据 **且** 有能量（任一不满足都不发）
    assert ts._should_send(ts.Policy.AOA_ENERGY_GATED, sc, 5, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.5, has_new_data=True, energy_ok=True) is True
    assert ts._should_send(ts.Policy.AOA_ENERGY_GATED, sc, 5, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.5, has_new_data=True, energy_ok=False) is False
    assert ts._should_send(ts.Policy.AOA_ENERGY_GATED, sc, 5, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.5, has_new_data=False, energy_ok=True) is False
    # event_triggered：静默窗 + 变化量
    assert ts._should_send(ts.Policy.EVENT_TRIGGERED, sc, 5, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.9, has_new_data=True, energy_ok=True) is False  # 静默窗内
    assert ts._should_send(ts.Policy.EVENT_TRIGGERED, sc, 100, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.9, has_new_data=True, energy_ok=True) is True
    assert ts._should_send(ts.Policy.EVENT_TRIGGERED, sc, 100, last_tx_t=0, last_sent_value=0.0,
                           current_value=0.01, has_new_data=False, energy_ok=True) is False


def test_unknown_policy_rejected() -> None:
    with pytest.raises(ValueError):
        ts.simulate(ts.scarce_scenario(), "no_such_policy")


def test_cli_demo_renders_table(capsys) -> None:
    """--demo 必须能把四条策略名打进表里（工单验收 1 的口径）。"""
    assert ts.main(["--demo"]) == 0
    out = capsys.readouterr().out
    for name in ts.Policy.ALL:
        assert name in out
    assert "AoII" in out
