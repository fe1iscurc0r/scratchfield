"""R28 验收测试：频谱感知物种识别原型。

覆盖：
  1. 物理先验提升：未见条件（θ=4）下识别率高于无先验
  2. 低信噪比仍高于随机：3 类随机基线 1/3
  3. 模板归一化：各物种模板单位范数
  4. 衰减模型：频率越高衰减越大（物理合理性）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_spectrum_species_recognizer.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import spectrum_species_recognizer as ssr


@pytest.fixture(scope="module")
def templates():
    return ssr.make_templates()


def test_physical_prior_beats_without(templates):
    theta = 4.0
    acc_no = ssr.accuracy(lambda y, t: ssr.classify_no_physics(y, t), templates, theta, 0.5, 1000)
    acc_ph = ssr.accuracy(lambda y, t: ssr.classify_with_physics(y, t, theta), templates, theta, 0.5, 1000)
    assert acc_ph > acc_no + 0.02


def test_above_chance_low_snr(templates):
    theta = 4.0
    for cls in (ssr.classify_no_physics,
                lambda y, t: ssr.classify_with_physics(y, t, theta)):
        acc = ssr.accuracy(lambda y, t: cls(y, t), templates, theta, 1.0, 1000)
        assert acc > 1 / 3  # 3 类随机基线


def test_templates_normalized(templates):
    for t in templates:
        assert np.linalg.norm(t) == pytest.approx(1.0, rel=1e-6)


def test_attenuation_monotonic():
    A = ssr.attenuation(32, 2.0)
    assert A[0] > A[-1]  # 高频衰减更大（物理传播）
    assert np.all(A > 0)
