"""工单256 任务B 的测试：RFI 相关监测（离线、确定性）。

跑法（仓库根）：
    python -m pytest mcpserver/rf_brain/test_rfi_correlated_monitor.py -q

纪律：本模块只**扩**既有 rfi 能力，不得重写 —— 见 `test_existing_api_untouched`。
"""
from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from mcpserver.rf_brain import rfi_correlated_monitor as cm
from mcpserver.rf_brain import rfi_mitigation, rfi_statistical


def test_mixed_false_alarm_strictly_lower_than_energy_baseline() -> None:
    """★ 硬断言：混合场景下，相关判据的误报率**严格低于**单通道能量判据。"""
    mixed = next(r for r in cm.run_all() if r.name == "mixed")
    assert mixed.correlation.false_alarm_rate < mixed.energy_baseline.false_alarm_rate, (
        f"相关误报 {mixed.correlation.false_alarm_rate:.3f} 未严格低于 "
        f"能量基线 {mixed.energy_baseline.false_alarm_rate:.3f}")
    # 同时要求检测率不塌（不能靠"什么都不报"换低误报）
    assert mixed.correlation.detection_rate == pytest.approx(1.0)


def test_signal_only_coherence_protects_real_signal() -> None:
    """纯真信号场景：相关判据不报（误报 0），单通道能量判据把真信号当干扰（误报 100%）。"""
    res = next(r for r in cm.run_all() if r.name == "signal_only")
    assert res.correlation.false_alarm_rate == 0.0
    assert res.energy_baseline.false_alarm_rate == 1.0
    # γ² 在同源信号处应接近 1
    assert res.extra["gamma2_at_signal"][0] > 0.9


def test_local_only_detected_by_both() -> None:
    """纯本地干扰：两种判据都该抓到（相关判据靠 γ² 低，不靠能量差）。"""
    res = next(r for r in cm.run_all() if r.name == "local_only")
    assert res.correlation.detection_rate == 1.0
    assert res.energy_baseline.detection_rate == 1.0
    assert res.extra["gamma2_at_rfi"][0] < 0.5


def test_deterministic() -> None:
    a = [r.as_dict() for r in cm.run_all()]
    b = [r.as_dict() for r in cm.run_all()]
    assert a == b


def test_coherence_bounds_and_shape() -> None:
    name, a, b, _rfi, _sig = cm.build_scenarios()[2]
    freqs, gamma2, total = cm.coherence_spectrum(a, b, cm.DEMO_SAMPLE_RATE)
    assert freqs.size == gamma2.size == total.size == cm.DEFAULT_FRAME_LEN // 2 + 1
    assert float(np.min(gamma2)) >= 0.0 and float(np.max(gamma2)) <= 1.0
    assert np.all(np.diff(freqs) > 0)


def test_incoherent_channels_give_low_coherence() -> None:
    """两路独立白噪声 ⇒ 平均相干应落在 1/K 量级，远低于阈值。"""
    rng = np.random.default_rng(7)
    a = rng.normal(0.0, 1.0, 4096)
    b = rng.normal(0.0, 1.0, 4096)
    _f, gamma2, _t = cm.coherence_spectrum(a, b, cm.DEMO_SAMPLE_RATE)
    assert float(np.median(gamma2)) < 0.3


def test_existing_api_untouched() -> None:
    """既有 rfi 模块的公开函数/类必须仍在且**参数名不变**（工单不变量）。"""
    need = {
        "power_spectrum": ["signal", "sample_rate"],
        "detect_rfi_narrowband": ["signal", "sample_rate", "prominence_db"],
        "detect_rfi_dual_channel": ["ch_a", "ch_b", "sample_rate", "imbalance_db"],
        "mitigate_rfi": None,
    }
    for name, params in need.items():
        fn = getattr(rfi_mitigation, name, None)
        assert callable(fn), f"rfi_mitigation.{name} 丢失"
        if params is not None:
            got = list(inspect.signature(fn).parameters)
            assert got[: len(params)] == params, f"{name} 参数被改：{got}"
    for cls in ("StatisticalRFIDetector", "StreamingRFIDetector", "ResourceEstimate"):
        assert hasattr(rfi_statistical, cls), f"rfi_statistical.{cls} 丢失"


def test_evaluate_scenario_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        cm.coherence_spectrum(np.zeros(512), np.zeros(256), 1000.0)


def test_short_signal_raises() -> None:
    with pytest.raises(ValueError):
        cm.coherence_spectrum(np.zeros(10), np.zeros(10), 1000.0,
                              frame_len=256, hop=128)


def test_cli_demo_prints_required_keys(capsys) -> None:
    """验收 2 的口径：--demo 里必须有 confusion / detection_rate / false_alarm。"""
    assert cm.main(["--demo"]) == 0
    out = capsys.readouterr().out
    for key in ("confusion", "detection_rate", "false_alarm"):
        assert key in out, f"缺少 {key}"


def test_cli_json(capsys) -> None:
    import json
    assert cm.main(["--demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {p["scenario"] for p in payload} == {"local_only", "signal_only", "mixed"}
    for p in payload:
        assert set(p["correlation"]) == {"tp", "fp", "fn", "tn", "detection_rate", "false_alarm_rate"}


def test_rates_are_finite_or_nan_not_crash() -> None:
    """没有正类/负类时，比率应为 NaN 而不是崩（local_only 无负类、signal_only 无正类）。"""
    for r in cm.run_all():
        for cmx in (r.correlation, r.energy_baseline):
            for v in (cmx.detection_rate, cmx.false_alarm_rate):
                assert math.isnan(v) or 0.0 <= v <= 1.0
