"""工单 262 任务 D 验收：POD 曲线。"""
from __future__ import annotations

import pytest

from mcpserver.integrity_pod import PODCurve, a90, pod_curve, sobol_indices
from mcpserver.integrity_pod.kriging import kriging_pod_surface

SAMPLE = [(1.0, False), (2.0, False), (3.0, True), (4.0, True), (5.0, True)]


def test_pod_is_monotonic_non_decreasing() -> None:
    curve = pod_curve([1, 2, 3, 4, 5], SAMPLE)
    values = [curve.pod(a) for a in (0.5, 1, 2, 3, 4, 5, 8, 20)]
    for prev, cur in zip(values, values[1:]):
        assert cur >= prev - 1e-12, f"POD 应单调不减，实际 {values}"


def test_a90_within_sample_range() -> None:
    curve = pod_curve([1, 2, 3, 4, 5], SAMPLE)
    value = a90(curve)
    assert curve.a_min <= value <= curve.a_max, (
        f"a90={value} 应落在样本区间 [{curve.a_min}, {curve.a_max}]"
    )


def test_pod_at_a90_matches_curve_definition() -> None:
    curve = pod_curve([1, 2, 3, 4, 5], SAMPLE)
    assert curve.pod(curve.a90_scale) == pytest.approx(1 - 2.718281828 ** -1, rel=1e-6)


def test_sobol_returns_empty_dict_phase1() -> None:
    assert sobol_indices(object(), n_samples=16) == {}
    with pytest.raises(ValueError):
        sobol_indices(object(), n_samples=0)


def test_kriging_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="二期"):
        kriging_pod_surface(object())


def test_rejects_degenerate_input() -> None:
    with pytest.raises(ValueError):
        pod_curve([1, 2], [])
    with pytest.raises(ValueError):
        pod_curve([1, 2], [(1.0, True), (2.0, True)])
    with pytest.raises(ValueError):
        pod_curve([1, 2], [(1.0, False), (2.0, False)])


def test_curve_is_dataclass_with_cov() -> None:
    curve = pod_curve([1, 2, 3, 4, 5], SAMPLE)
    assert isinstance(curve, PODCurve)
    assert curve.hit_rate == pytest.approx(3 / 5)
