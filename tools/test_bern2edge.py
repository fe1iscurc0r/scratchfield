"""bern2edge 测试（K19 验收：参数量/精度/部署预算对比）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from bern2edge import (
    bernstein_basis,
    bernstein_fit,
    bernstein_lut,
    bernstein_predict,
    compare,
    elm_fit,
    elm_predict,
)


def _target(x):
    return 0.8 * np.exp(-((x - 0.4) ** 2) / 0.02) + 0.3 * x


def test_bernstein_basis_partition_of_unity():
    x = np.linspace(0, 1, 50)
    B = bernstein_basis(8, x)
    assert np.allclose(B.sum(axis=0), 1.0)


def test_bernstein_fits_target():
    x = np.linspace(0, 1, 200)
    y = _target(x)
    beta = bernstein_fit(x, y, 10)
    yhat = bernstein_predict(beta, 10, x)
    assert np.mean((yhat - y) ** 2) < 0.001


def test_bernstein_lut_shape():
    lut = bernstein_lut(10, bins=256)
    assert lut.shape == (11, 256)
    assert np.all((lut >= 0.0) & (lut <= 1.0))


def test_comparison_params_and_macs_favor_bernstein():
    c = compare()
    b, e = c["bernstein"], c["elm"]
    # 两者精度都达标
    assert b["mse"] < 0.001
    assert e["mse"] < 0.001
    # Bernstein 参数更少、每推理 MACs 更少（部署预算优势）
    assert b["params"] < e["params"]
    assert b["macs"] < e["macs"]
