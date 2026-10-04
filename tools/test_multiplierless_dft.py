"""multiplierless_dft 测试（W73-11 原型）。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from multiplierless_dft import _quant, approximation_error, dft, multiplierless_dft


def test_quant_maps_to_pow2():
    assert _quant(0.51) in (0.5,)
    assert _quant(0.0) == 0.0
    assert _quant(-0.49) in (-0.5,)


def test_dft_deterministic():
    x = np.array([1.0, 0.0, 0.0, 0.0])
    assert np.allclose(dft(x), np.ones(4))


def test_multiplierless_approximates_dft():
    rng = np.random.default_rng(0)
    x = rng.normal(size=16)
    err = approximation_error(x)
    assert err < 0.5, f"量化 DFT 误差过大：{err:.3f}"


def test_multiplierless_is_cheaper_than_full():
    # 概念验证：量化旋转因子只落在 2 的幂集合（无全精度乘法）
    vals = {_quant(math.cos(a)) for a in np.linspace(0, 2 * math.pi, 100)}
    assert vals <= {1.0, 0.5, 0.25, 0.125, 0.0625, 0.0, -1.0, -0.5, -0.25, -0.125, -0.0625}
