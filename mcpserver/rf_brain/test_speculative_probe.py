"""R65 验收测试：推测探针式信号分类（复用感知 pipeline 中间特征）。

覆盖：
  1. pipeline_spectrum：感知 pipeline 既有频谱（正频功率谱）
  2. ProbeClassifier：复用频谱分类（窄带信号 vs 宽带干扰），准确率 ≥85%
  3. 额外开销 ≤5%（探针只做 M 维点积，不再算 FFT）
  4. 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/test_speculative_probe.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import speculative_probe as sp

SR, N = 4000.0, 512


def _tone(n: int, f: float, sr: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(n) / sr
    return amp * np.sin(2.0 * np.pi * f * t)


def _make_data(n_per_class: int, seed: int = 0) -> tuple[list[np.ndarray], np.ndarray]:
    """2 类：窄带单音（class 0）vs 宽带干扰（class 1）。"""
    rng = np.random.default_rng(seed)
    spectra, labels = [], []
    for _ in range(n_per_class):
        f = float(rng.uniform(200, 800))
        x = _tone(N, f, SR, amp=1.0) + 0.02 * rng.standard_normal(N)
        spectra.append(sp.pipeline_spectrum(x, n_fft=N))
        labels.append(0)
        x = 0.5 * rng.standard_normal(N)
        spectra.append(sp.pipeline_spectrum(x, n_fft=N))
        labels.append(1)
    return spectra, np.asarray(labels, dtype=int)


def test_pipeline_spectrum_shape():
    x = _tone(N, 500.0, SR)
    spec = sp.pipeline_spectrum(x, n_fft=N)
    assert spec.shape == (N // 2 + 1,)


def test_probe_accuracy_above_85pct():
    """复用既有频谱的探针分类准确率 ≥85%。"""
    train_spec, train_y = _make_data(120, seed=0)
    test_spec, test_y = _make_data(60, seed=1)
    probe = sp.fit_probe(train_spec, train_y, probe_bins=32)
    acc = probe.accuracy(test_spec, test_y)
    assert acc >= 0.85, f"准确率 {acc:.3f} < 0.85"


def test_overhead_below_5pct():
    """探针额外开销（点积 MAC / 既有 FFT MAC）≤5%。"""
    ratio = sp.overhead_ratio(N, probe_bins=32)
    assert ratio <= 0.05, f"开销比 {ratio:.4f} 超过 5%"


def test_rejects_bad_probe_bins():
    with pytest.raises(ValueError):
        sp.ProbeClassifier(probe_bins=0)
