"""木质素热解 ANN 最小探针（卷101 W101-05 · BSD-2 可借鉴，独立实现）。

设计参考：houghb/lignet（BSD-2）的木质素热解人工神经网络——本模块用 sklearn
MLPRegressor 复刻其「输入→18 隐层→20 隐层→多输出线性」回归骨架及训练实践
（标准化 + 早停 + 验证集划分）。ScaledTanH 以 sklearn tanh 替代、adagrad 以
adam 替代（现代默认），网络层级/规模/早停语义保持一致。
"""
from __future__ import annotations

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

# 源自 lignet learning_curve_full_net.py 的网络结构（隐层 18/20，输出线性）
HIDDEN_UNITS = (18, 20)


def make_lignet_model(x_dim: int, y_dim: int, max_iter: int = 4000,
                      patience: int = 100) -> MLPRegressor:
    """构造复刻 lignet 结构的 MLP 回归器。

    x_dim/y_dim 仅用于保证维度自洽（sklearn 由数据推断形状），保留接口语义。
    """
    return MLPRegressor(
        hidden_layer_sizes=HIDDEN_UNITS,
        activation="tanh",           # 对应源 ScaledTanH（LeCun 指导，scale 2/3 × 1.7159）
        solver="adam",               # 对应源 adagrad，换现代默认
        max_iter=max_iter,
        early_stopping=True,
        n_iter_no_change=patience,
        validation_fraction=0.3,     # 对应源 TrainSplit(eval_size=0.3)
        random_state=0,
    )


def train_lig_ann(x: np.ndarray, y: np.ndarray, max_iter: int = 4000):
    """标准化后训练，返回 (model, x_scaler, y_scaler)。

    对应源 gen_train_test 中 x_scaler/y_scaler 的训练集拟合语义。
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    x_scaler = StandardScaler().fit(x)
    y_scaler = StandardScaler().fit(y)
    model = make_lignet_model(x.shape[1], y.shape[1], max_iter=max_iter)
    model.fit(x_scaler.transform(x), y_scaler.transform(y))
    return model, x_scaler, y_scaler


def predict_lig_ann(model: MLPRegressor, x_scaler: StandardScaler,
                    y_scaler: StandardScaler, x: np.ndarray) -> np.ndarray:
    """标准化入模预测并反标准化回原目标量纲。"""
    x = np.asarray(x, dtype=float)
    y_pred_scaled = model.predict(x_scaler.transform(x))
    if y_pred_scaled.ndim == 1:  # 单输出回归时 predict 返回 1D，反标准化需要 2D
        y_pred_scaled = y_pred_scaled.reshape(-1, 1)
    return y_scaler.inverse_transform(y_pred_scaled)
