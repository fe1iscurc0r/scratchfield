"""U-04 验收：feature_extractor 去噪前置（denoise_mode）测试。

验收点（工单）：
1. denoise_mode 默认 off，不改变现有行为（与不传参逐字段一致）
2. static（N2N）/ reservoir（漂移补偿）模式可跑通，FeatureVector schema 不变
3. 降级：未知模式 / denoise 模块不可用时自动 off 不崩
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from mcpserver.rf_brain import feature_extractor as fx
from mcpserver.rf_brain.denoise.drift import DriftCompensator
from mcpserver.rf_brain.denoise.n2n import N2NDenoiser
from mcpserver.rf_brain.denoise.reservoir import Reservoir
from mcpserver.rf_brain.schemas import FeatureVector


def _noisy_tone(n: int = 1024, fs: float = 1_000_000.0,
                offset: float = 100_000.0, snr_db: float = 10.0,
                seed: int = 3) -> np.ndarray:
    """带噪单音复信号（特征提取的最小可用输入）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    sig = np.exp(2j * np.pi * offset * t)
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)
    return sig + noise * (10 ** (-snr_db / 20))


def test_default_off_unchanged():
    """默认 off：与不传 denoise 参数逐字段一致（不破坏现状）。"""
    iq = _noisy_tone()
    base = fx.extract_features(iq, sample_rate=1_000_000.0)
    explicit = fx.extract_features(iq, sample_rate=1_000_000.0, denoise_mode="off")
    assert dataclasses.asdict(base) == dataclasses.asdict(explicit)
    assert isinstance(base, FeatureVector) and base.n_samples == len(iq)


def test_static_mode_runs_and_schema_kept():
    """static：N2N 前置去噪跑通，输出仍是完整 FeatureVector（schema 不变）。"""
    iq = _noisy_tone(n=512)
    d = N2NDenoiser(window=15, seed=0)
    fv = fx.extract_features(iq, sample_rate=1_000_000.0,
                             denoise_mode="static", denoiser=d)
    assert isinstance(fv, FeatureVector)
    # n2n 滑窗输出略短于输入，但必须为正且特征字段齐全
    assert 0 < fv.n_samples <= len(iq)
    assert set(dataclasses.asdict(fv)) == set(dataclasses.asdict(
        fx.extract_features(iq, sample_rate=1_000_000.0)))


def test_reservoir_mode_with_fitted_compensator():
    """reservoir：已 fit 的漂移补偿器前置跑通。"""
    iq = _noisy_tone(n=512)
    comp = DriftCompensator(Reservoir(n_units=16, seed=0))
    comp.fit(np.real(iq).astype(float))  # 自关联拟合
    fv = fx.extract_features(iq, sample_rate=1_000_000.0,
                             denoise_mode="reservoir", compensator=comp)
    assert isinstance(fv, FeatureVector) and 0 < fv.n_samples <= len(iq)


def test_unknown_mode_degrades_to_off():
    """未知模式 → 降级 off（结果与 off 一致，不抛异常）。"""
    iq = _noisy_tone()
    base = fx.extract_features(iq, sample_rate=1_000_000.0)
    degraded = fx.extract_features(iq, sample_rate=1_000_000.0,
                                   denoise_mode="bogus_mode")
    assert dataclasses.asdict(base) == dataclasses.asdict(degraded)


def test_denoise_unavailable_degrades_to_off(monkeypatch):
    """denoise 模块不可用（模拟 import 失败）→ 自动 off 不崩。"""
    monkeypatch.setattr(fx, "_DENOISE_AVAILABLE", False)
    iq = _noisy_tone()
    base = fx.extract_features(iq, sample_rate=1_000_000.0)
    degraded = fx.extract_features(iq, sample_rate=1_000_000.0,
                                   denoise_mode="static")
    assert dataclasses.asdict(base) == dataclasses.asdict(degraded)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
