"""lig_ann_probe 验收硬线（卷101 W101-05）。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lig_ann_probe import (  # noqa: E402
    HIDDEN_UNITS,
    make_lignet_model,
    predict_lig_ann,
    train_lig_ann,
)


def test_model_architecture_matches_lignet():
    """网络结构复刻：18/20 隐层 + tanh + 0.3 验证划分 + 早停。"""
    m = make_lignet_model(5, 2)
    assert m.hidden_layer_sizes == HIDDEN_UNITS
    assert m.activation == "tanh"
    assert m.validation_fraction == 0.3
    assert m.early_stopping is True and m.n_iter_no_change == 100


def test_train_predict_roundtrip():
    """合成热解数据上训练→预测回原量纲，R² 达标。"""
    rng = np.random.default_rng(7)
    x = rng.uniform(0, 1, size=(400, 3))
    y = (2.5 * x[:, 0] - 1.8 * x[:, 1] + 0.7 * x[:, 2] + 1.0
         + rng.normal(0, 0.05, size=400))
    model, x_scaler, y_scaler = train_lig_ann(x, y, max_iter=800)
    y_pred = predict_lig_ann(model, x_scaler, y_scaler, x).ravel()
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot
    assert r2 > 0.9


def test_predict_shapes_consistent():
    """预测输出形状与目标一致（多输出情形）。"""
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 1, size=(200, 4))
    y = np.column_stack([x[:, 0] * 3, x[:, 1] - x[:, 2]])
    model, x_scaler, y_scaler = train_lig_ann(x, y, max_iter=800)
    y_pred = predict_lig_ann(model, x_scaler, y_scaler, x[:10])
    assert y_pred.shape == (10, 2)
