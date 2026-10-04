"""R37 验收测试：OT 正则频谱去卷积原型。

覆盖：
  1. 时序连贯：TV/OT 的时序相关系数高于 L1（正则保时序）
  2. 去卷积降噪：TV 重建 MSE 低于模糊观测
  3. OT 优于 L1：OT 时序相关性高于 L1（运输式正则优于纯稀疏）
  4. 三种正则均收敛到有限结果

运行：python -m pytest mcpserver/rf_brain/prototypes/test_ot_deconvolution.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import ot_deconvolution as od


@pytest.fixture(scope="module")
def data():
    kernel = np.array([0.05, 0.2, 0.5, 0.2, 0.05])
    X, Y = od.synthesize(32, 20, kernel=kernel, noise=0.2, seed=0)
    return kernel, X, Y


def test_tv_ot_preserve_coherence(data):
    kernel, X, Y = data
    corr_l1 = od.metrics(od.deconvolve(Y, kernel, "l1", 1.0), X)["temporal_corr"]
    corr_tv = od.metrics(od.deconvolve(Y, kernel, "tv", 1.0), X)["temporal_corr"]
    corr_ot = od.metrics(od.deconvolve(Y, kernel, "ot", 1.0), X)["temporal_corr"]
    assert corr_tv > corr_l1
    assert corr_ot > corr_l1


def test_tv_denoises(data):
    kernel, X, Y = data
    mse_obs = od.metrics(Y, X)["mse"]
    mse_tv = od.metrics(od.deconvolve(Y, kernel, "tv", 1.0), X)["mse"]
    assert mse_tv < mse_obs


def test_ot_beats_l1(data):
    kernel, X, Y = data
    corr_l1 = od.metrics(od.deconvolve(Y, kernel, "l1", 1.0), X)["temporal_corr"]
    corr_ot = od.metrics(od.deconvolve(Y, kernel, "ot", 1.0), X)["temporal_corr"]
    assert corr_ot > corr_l1


def test_finite_results(data):
    kernel, X, Y = data
    for reg in ("l1", "tv", "ot"):
        Xh = od.deconvolve(Y, kernel, reg, 1.0)
        assert np.all(np.isfinite(Xh))
        assert Xh.shape == X.shape
