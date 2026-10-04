"""R36 验收测试：LQG/积分器混合 AGC 原型。

覆盖：
  1. 混合 LQG 输出误差方差低于纯积分器（去噪收益）
  2. 混合 LQG 跟踪目标（误差均值 ≈ 0）
  3. 稳态误差：后段误差接近 0（收敛）
  4. 噪声越大混合收益越明显（鲁棒性）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_hybrid_agc.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import hybrid_agc as agc


@pytest.fixture(scope="module")
def data():
    return agc.synthesize(2000, seed=0)


def test_hybrid_lower_variance(data):
    e_pure = agc.pure_integrator(data["s"], data["noise"])
    e_hyb = agc.hybrid_lqg(data["s"], data["noise"])
    assert np.var(e_hyb) < np.var(e_pure) * 0.5


def test_hybrid_tracks_target(data):
    e_hyb = agc.hybrid_lqg(data["s"], data["noise"])
    assert abs(np.mean(e_hyb[-500:])) < 0.1  # 稳态误差接近 0


def test_hybrid_filters_noise(data):
    e_hyb = agc.hybrid_lqg(data["s"], data["noise"])
    # 测量噪声方差 0.25；混合 LQG 的误差方差应远小于它（卡尔曼滤波去噪）
    assert np.var(e_hyb) < 0.25


def test_higher_noise_more_benefit():
    d_low = agc.synthesize(2000, noise_std=0.2, seed=1)
    d_high = agc.synthesize(2000, noise_std=1.0, seed=1)
    gain_low = np.var(agc.pure_integrator(d_low["s"], d_low["noise"])) / \
               np.var(agc.hybrid_lqg(d_low["s"], d_low["noise"]))
    gain_high = np.var(agc.pure_integrator(d_high["s"], d_high["noise"])) / \
                np.var(agc.hybrid_lqg(d_high["s"], d_high["noise"]))
    assert gain_high > gain_low  # 噪声越大，混合收益越大
