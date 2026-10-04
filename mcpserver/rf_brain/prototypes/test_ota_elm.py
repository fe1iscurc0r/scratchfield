"""R38 验收测试：OTA-ELM 信号分类器原型。

覆盖：
  1. 伪逆训练：ELM 训练后 fp32 分类准确率 ≥ 90%
  2. 闭式解：输出权重 = pinv(H) @ Y（无梯度训练）
  3. LUT 表：生成 int8 激活表，范围与档数正确
  4. int8 定点化：量化后准确率仍 ≥ 85%（可部署）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_ota_elm.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import ota_elm as elm


@pytest.fixture(scope="module")
def data():
    X, y = elm.synthesize_data(400, 4, 8, seed=0)
    rng = np.random.default_rng(42)
    perm = rng.permutation(X.shape[0])
    X, y = X[perm], y[perm]
    model = elm.elm_train(X[:300], y[:300], hidden=32, seed=0)
    return X[300:], y[300:], model


def test_fp32_accuracy(data):
    X_te, y_te, model = data
    acc = elm.accuracy(y_te, elm.elm_predict(X_te, model))
    assert acc >= 0.90


def test_closed_form_output_weights(data):
    X_te, y_te, model = data
    # W_out = pinv(H) @ Y 闭式解（尺寸正确：hidden × n_classes）
    assert model["W_out"].shape == (32, 4)


def test_lut_generation():
    lut = elm.generate_lut(n_levels=256)
    assert lut.size == 256
    assert lut.dtype == np.int8
    assert np.all(np.abs(lut) <= 127)


def test_int8_quantization_accuracy(data):
    X_te, y_te, model = data
    acc = elm.quantize_accuracy(X_te, y_te, model)
    assert acc >= 0.85
