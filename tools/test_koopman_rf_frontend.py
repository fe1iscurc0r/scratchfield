"""计算型射频前传 · Koopman 前端原型测试（K16 验收）。

运行：python -m pytest tools/test_koopman_rf_frontend.py -q
验收断言：
  - Koopman 前端分类精度 ≥ 全基带 FFT 精度的 90%；
  - 计算量（每帧乘法）较全基带降 ≥ 3×。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from koopman_rf_frontend import (
    LinearClassifier,
    fft_features,
    gen_cw,
    gen_fsk,
    gen_noise,
    gen_ook,
    koopman_features,
    macs_full_baseband,
    macs_koopman,
)


def _build_dataset():
    rng = np.random.default_rng(7)
    fs, f0, f1, snr, n = 100_000.0, 5_000.0, 15_000.0, 15.0, 1024
    per = 300
    Xf, Xk, y = [], [], []
    gens = [
        lambda: gen_ook(n, fs, f0, snr, rng),
        lambda: gen_fsk(n, fs, f0, f1, snr, rng),
        lambda: gen_cw(n, fs, f0, snr, rng),
        lambda: gen_noise(n, rng),
    ]
    for c, g in enumerate(gens):
        for _ in range(per):
            s = g()
            Xf.append(fft_features(s))
            Xk.append(koopman_features(s))
            y.append(c)
    Xf, Xk = np.array(Xf), np.array(Xk)
    y = np.array(y)

    idx = np.arange(len(y))
    rng.shuffle(idx)
    split = int(len(idx) * 0.7)
    tr, te = idx[:split], idx[split:]
    return Xf[tr], Xf[te], Xk[tr], Xk[te], y[tr], y[te]


def test_accuracy_within_90_percent():
    Xf_tr, Xf_te, Xk_tr, Xk_te, y_tr, y_te = _build_dataset()
    clf_f = LinearClassifier(Xf_tr.shape[1], 4, seed=0)
    clf_k = LinearClassifier(Xk_tr.shape[1], 4, seed=0)
    clf_f.fit(Xf_tr, y_tr)
    clf_k.fit(Xk_tr, y_tr)
    acc_f = clf_f.accuracy(Xf_te, y_te)
    acc_k = clf_k.accuracy(Xk_te, y_te)
    # 验收：Koopman 前端精度 ≥ 全基带的 90%
    assert acc_k >= 0.9 * acc_f, f"acc_koop={acc_k:.3f} < 0.9*acc_full={0.9 * acc_f:.3f}"


def test_compute_reduction_at_least_3x():
    n = 1024
    m_full = macs_full_baseband(n)
    m_koop = macs_koopman(n, decim=4, n_obs=6)
    # 验收：计算量降 ≥ 3×
    assert m_full / m_koop >= 3.0, f"reduction={m_full / m_koop:.2f}× < 3×"
