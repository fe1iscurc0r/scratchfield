"""geometry_kan 测试（K21 验收：参数/精度对比 + 可解释性示例）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from geometry_kan import (
    compare,
    hat_basis,
    kan_fit,
    kan_predict,
    pava_monotone,
)


def test_hat_basis_partition_of_unity():
    x = np.linspace(0, 1, 50)
    knots = np.linspace(0, 1, 9)
    H = hat_basis(x, knots)
    assert np.allclose(H.sum(axis=1), 1.0)


def test_pava_monotone_non_decreasing():
    c = np.array([0.3, 0.1, 0.5, 0.2, 0.9])
    cm = pava_monotone(c)
    assert np.all(np.diff(cm) >= -1e-12)
    assert cm.shape == c.shape


def test_geometry_constraint_improves_and_enforces_monotone():
    r = compare(seed=0)
    # 无约束拟合在噪声下非单调（过拟合）
    assert r["kan_free"]["monotone"] is False
    # 几何约束：保证单调，且 MSE 更低（抑制过拟合）
    assert r["kan_geo"]["monotone"] is True
    assert r["kan_geo"]["mse"] < r["kan_free"]["mse"]


def test_params_and_accuracy_vs_elm():
    r = compare(seed=0)
    # KAN 参数量更少，且几何约束版精度不劣于 ELM
    assert r["kan_geo"]["params"] < r["elm"]["params"]
    assert r["kan_geo"]["mse"] <= r["elm"]["mse"] + 0.001


def test_explainability_coefficients_are_knot_values():
    """可解释性示例：hat 基下系数即函数在结点处的值，可直接读出形状。"""
    knots = np.linspace(0, 1, 9)
    x = np.linspace(0, 1, 200)
    y = np.log(1.0 + 3.0 * x)
    c = kan_fit(x, y, knots)
    # 在结点处，预测值 ≈ 系数（基在结点处取值 1）
    yhat = kan_predict(c, knots, knots)
    assert np.allclose(yhat, c, atol=1e-9)
    # 目标单调 → 系数应大致非递减（形状可读）
    assert c[-1] > c[0]
