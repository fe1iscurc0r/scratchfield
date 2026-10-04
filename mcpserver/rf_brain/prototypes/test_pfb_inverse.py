"""R13 验收测试：PFB 逆重建原型。

覆盖：
  1. 分析滤波器组输出 K 个子带
  2. 冲激重建：δ → δ（结构正确，峰值≈1）
  3. 稳态重建 SNR 高于总体（暂态被排除）
  4. 稳态 SNR 达到可用阈值（近完美重建的量级）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_pfb_inverse.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import pfb_inverse as pf


@pytest.fixture(scope="module")
def setup():
    K, P = 8, 16
    h = pf.prototype_filter(K, P)
    return K, P, h


def test_analysis_channel_count(setup):
    K, P, h = setup
    x = np.random.default_rng(0).standard_normal(1024)
    sub = pf.pfb_analyze(x, h, K, P)
    assert sub.shape[0] == K
    assert sub.shape[1] == len(x) // K


def test_impulse_reconstruction(setup):
    K, P, h = setup
    x = np.zeros(2048)
    x[1024] = 1.0
    x_hat = pf.pfb_synthesize(pf.pfb_analyze(x, h, K, P), h, K, P)
    assert np.max(np.abs(x_hat)) == pytest.approx(1.0, abs=1e-3)
    assert np.argmax(np.abs(x_hat)) == 1024


def test_steady_state_snr_higher_than_overall(setup):
    K, P, h = setup
    x = np.random.default_rng(0).standard_normal(4096)
    x_hat = pf.pfb_synthesize(pf.pfb_analyze(x, h, K, P), h, K, P)
    overall = pf.reconstruction_snr_db(x, x_hat)
    steady = pf.reconstruction_snr_db(x, x_hat, skip=K * P)
    assert steady > overall


def test_steady_state_snr_threshold(setup):
    K, P, h = setup
    x = np.random.default_rng(0).standard_normal(8192)
    x_hat = pf.pfb_synthesize(pf.pfb_analyze(x, h, K, P), h, K, P)
    assert pf.reconstruction_snr_db(x, x_hat, skip=K * P) > 12.0
