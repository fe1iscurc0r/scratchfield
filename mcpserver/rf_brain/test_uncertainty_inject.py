"""uncertainty_inject 测试（A23 验收：输出含置信区间的频谱感知结果 + 覆盖校准）。"""
from __future__ import annotations

import numpy as np

from .uncertainty_inject import Z_95, SpectrumSensor, sense_with_ci


def _grid(n: int = 401):
    return np.linspace(800.0, 1200.0, n)


def test_result_has_mean_and_ci():
    result = sense_with_ci(SpectrumSensor(), _grid())
    assert set(result) == {"f", "mean", "std", "lower", "upper"}
    assert result["mean"].shape == result["f"].shape
    assert np.all(np.isfinite(result["mean"]))
    assert np.all(result["std"] >= 0.0)
    # CI 以 mean 为中心
    assert np.allclose(result["upper"] - result["mean"], Z_95 * result["std"])
    assert np.allclose(result["mean"] - result["lower"], Z_95 * result["std"])


def test_uncertainty_wider_at_peak_than_baseline():
    """增益/频偏不确定性在信号峰处被放大，底噪处只受噪声底影响。"""
    sensor = SpectrumSensor()
    f = _grid()
    mean, std = sensor.inject_uncertainty(f)
    peak_idx = int(np.argmax(mean))
    base_idx = 0
    assert std[peak_idx] > std[base_idx]


def test_confidence_interval_coverage():
    """边缘化 CI 应贴合 95% 名义值（蒙特卡洛，实测 ~0.946）。"""
    sensor = SpectrumSensor()
    f = _grid()
    result = sense_with_ci(sensor, f)

    rng = np.random.default_rng(7)
    covered = 0
    trials = 4000
    for _ in range(trials):
        obs = sensor.sense(f, rng)
        within = (obs >= result["lower"]) & (obs <= result["upper"])
        covered += float(np.mean(within))
    coverage = covered / trials
    # 线性代理 + 高斯先验在 10Hz 频偏容差/50Hz 峰宽下校准良好（实测 0.946）。
    # 允许线性化带来的轻微保守偏差，但不接受明显失准。
    assert 0.90 <= coverage <= 0.98, f"覆盖 {coverage:.3f} 偏离 95% CI 名义值"


def test_offset_nuisance_shifts_but_mean_is_nominal():
    """频偏 nuisance 只放大不确定性，不改变标称均值。"""
    sensor = SpectrumSensor()
    f = _grid()
    mean, _ = sensor.inject_uncertainty(f)
    expected = sensor.forward(f, (sensor.gain_nom, sensor.noise_nom, sensor.offset_nom))
    assert np.allclose(mean, expected)
