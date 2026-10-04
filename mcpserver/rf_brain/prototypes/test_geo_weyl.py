"""R99/R122 验收测试：Geo-LoRA 子空间持续学习 + Weyl 信道容量。"""
from __future__ import annotations

import numpy as np

from tools.geo_lora import overlapping_tasks, retention_experiment

from . import weyl_channel as wc


def test_geo_lora_improves_retention():
    Xa, ya, Xb, yb = overlapping_tasks(seed=0)
    r = retention_experiment(Xa, ya, Xb, yb, seed=0)
    assert r["geo_retention"] > r["plain_retention"]
    assert r["improvement_pp"] >= 10.0, f"保留率提升 {r['improvement_pp']:.1f}pp 未达 10pp"


def test_weyl_capacity_positive_and_monotonic():
    # 差集移位集：{(a, a² mod 7)} 是 Z7 的差集（Singer 差集）
    d = 7
    shift_set = [(a, (a * a) % d) for a in range(1, d)]
    H = wc.weyl_channel_matrix(d, shift_set)
    c_low = wc.channel_capacity(H, snr=1.0)
    c_high = wc.channel_capacity(H, snr=10.0)
    assert c_low > 0.0
    assert c_high > c_low                        # 容量随 SNR 单调增


def test_weyl_operators_commute_relation():
    d = 4
    X, Z = wc.weyl_operators(d)
    # Weyl 对易关系：X Z = ω^{-1} Z X（等价 ω·X Z = Z X），ω = e^{2πi/d}
    omega = np.exp(2j * np.pi / d)
    assert np.allclose(omega * (X @ Z), Z @ X)
