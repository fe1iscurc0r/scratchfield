"""R38 · OTA-ELM 信号分类器原型（ESP32-S3 零梯度轻量推理）

灵感：POLLINATION-2026-08-29-round10（OTA-ELM 空中训练极限学习机）。

ELM（极限学习机）零梯度训练：随机隐层投影固定，输出层用**伪逆闭式解**一次求出，
无需反向传播——极适合 MCU 端部署（训练在 PC 完成，节点只跑前向）。

原型：
  - elm_train：随机输入权重 + 隐层激活 → 输出层伪逆闭式解（one-hot 标签）
  - elm_predict：前向 + argmax
  - generate_lut：隐层激活的 int8 查表（LUT 激活，替代逐元素非线性）
  - int8 定点化要点（文档）

运行：python -m mcpserver.rf_brain.prototypes.ota_elm
"""
from __future__ import annotations

import numpy as np


def synthesize_data(n: int, n_classes: int, d: int, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """合成信号特征：K 类各成高斯簇。"""
    rng = np.random.default_rng(seed)
    centers = rng.standard_normal((n_classes, d)) * 3.0
    X, y = [], []
    for c in range(n_classes):
        X.append(centers[c] + 0.5 * rng.standard_normal((n // n_classes, d)))
        y.append(np.full(n // n_classes, c))
    return np.vstack(X), np.concatenate(y)


def _activation(z: np.ndarray) -> np.ndarray:
    return np.tanh(z)


def elm_train(X: np.ndarray, y: np.ndarray, hidden: int, *, seed: int = 0) -> dict:
    """ELM 训练：随机隐层投影 + 输出层伪逆闭式解。"""
    rng = np.random.default_rng(seed)
    d = X.shape[1]
    n_classes = int(np.unique(y).size)               # 用实际类别数（鲁棒）
    W_in = rng.standard_normal((hidden, d)) * 0.5
    b = rng.standard_normal(hidden) * 0.5
    H = _activation(X @ W_in.T + b)                 # 隐层输出 (N, hidden)
    Y_onehot = np.eye(n_classes)[y.astype(int)]
    W_out = np.linalg.pinv(H) @ Y_onehot            # 伪逆闭式解
    return {"W_in": W_in, "b": b, "W_out": W_out}


def elm_predict(X: np.ndarray, model: dict) -> np.ndarray:
    """前向推理：返回预测类别。"""
    H = _activation(X @ model["W_in"].T + model["b"])
    return (H @ model["W_out"]).argmax(axis=1)


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(y_true == y_pred))


def generate_lut(n_levels: int = 256, vmax: float = 4.0) -> np.ndarray:
    """隐层激活（tanh）的 int8 LUT：把浮点激活查表替代。

    输入范围 [-vmax, vmax] 均分为 n_levels 档，预存 tanh 值（int8 量化）。
    """
    z = np.linspace(-vmax, vmax, n_levels)
    lut_fp = _activation(z)
    lut_i8 = np.round(lut_fp * 127).astype(np.int8)   # int8 量化到 [-127,127]
    return lut_i8


def quantize_accuracy(X: np.ndarray, y: np.ndarray, model: dict, n_levels: int = 256) -> float:
    """int8 定点化后的分类准确率（隐层激活走 LUT，权重 int8 量化）。"""
    lut = generate_lut(n_levels)
    vmax = 4.0
    step = 2 * vmax / n_levels
    # 隐层输入量化 + 激活查表 + 输出层 int8 权重
    W_out_q = np.round(model["W_out"] * 127 / (np.abs(model["W_out"]).max() + 1e-12)).astype(np.int8)
    z = X @ model["W_in"].T + model["b"]
    idx = np.clip(((z + vmax) / step).astype(int), 0, n_levels - 1)
    H_q = lut[idx].astype(np.float32) / 127.0
    return accuracy(y, (H_q @ W_out_q.astype(np.float32)).argmax(axis=1))


def main() -> None:
    X, y = synthesize_data(400, 4, 8, seed=0)
    # 打乱后按 3:1 划分（保证各类均衡出现在训练/测试）
    rng = np.random.default_rng(42)
    perm = rng.permutation(X.shape[0])
    X, y = X[perm], y[perm]
    X_tr, y_tr, X_te, y_te = X[:300], y[:300], X[300:], y[300:]
    model = elm_train(X_tr, y_tr, hidden=32, seed=0)
    acc_fp = accuracy(y_te, elm_predict(X_te, model))
    acc_i8 = quantize_accuracy(X_te, y_te, model)
    print(f"ELM 分类准确率：fp32 = {acc_fp*100:.1f}%   int8 定点 = {acc_i8*100:.1f}%")
    print(f"LUT 表大小 = {generate_lut().nbytes} 字节（{256} 档 int8）")


if __name__ == "__main__":
    main()
