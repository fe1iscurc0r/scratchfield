"""工具链 · Geo-LoRA 几何感知 LoRA 子空间持续学习（R99）

授粉自 26960v1（Geo-LoRA）：几何感知 LoRA 子空间持续学习——子空间投影保持 +
核-松弛对齐 + 中值校准块重叠。核心：把新任务的 LoRA 更新投影到「与旧任务梯度
正交的子空间」，避免灾难性遗忘（与 R58 Omega-S 同族，但用几何投影替代弹性惩罚）。

原型（纯 numpy）：线性分类器两任务持续学习，Geo-LoRA 把 ΔW 投影到旧任务梯度
的正交补，保留旧任务；对比无投影 LoRA。
"""
from __future__ import annotations

import numpy as np

__all__ = ["overlapping_tasks", "train_linear", "accuracy", "geo_lora_finetune", "retention_experiment"]


def _logistic_grad(W: np.ndarray, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    z = X @ W
    return -(X.T @ (y / (1.0 + np.exp(y * z)))) / y.size


def train_linear(X: np.ndarray, y: np.ndarray, *, lr: float = 0.1, steps: int = 300) -> np.ndarray:
    W = np.zeros(X.shape[1])
    for _ in range(steps):
        W -= lr * _logistic_grad(W, X, y)
    return W


def accuracy(W: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.sign(X @ W) == y))


def overlapping_tasks(d: int = 8, n: int = 800, seed: int = 0) -> tuple:
    """两个部分重叠任务：A 用特征 0,1；B 翻转特征 1 保留特征 0（灾难性遗忘场景）。"""
    rng = np.random.default_rng(seed)
    wa = np.zeros(d); wa[0] = 1.0; wa[1] = 1.0
    wb = np.zeros(d); wb[0] = 1.0; wb[1] = -1.0
    Xa = rng.standard_normal((n, d)); ya = np.sign(Xa @ wa)
    Xb = rng.standard_normal((n, d)); yb = np.sign(Xb @ wb)
    return Xa, ya, Xb, yb


def geo_lora_finetune(W0: np.ndarray, X_b: np.ndarray, y_b: np.ndarray,
                      task_a_grad: np.ndarray, *, lr: float = 0.1, steps: int = 300) -> np.ndarray:
    """Geo-LoRA：每步把 LoRA 增量投影到旧任务梯度的正交补（不破坏旧任务）。"""
    W = W0.copy()
    g_old = task_a_grad / (np.linalg.norm(task_a_grad) + 1e-12)   # 旧任务梯度方向
    for _ in range(steps):
        g = _logistic_grad(W, X_b, y_b)
        dW = -lr * g
        dW = dW - (dW @ g_old) * g_old                             # 投影到正交补
        W += dW
    return W


def retention_experiment(Xa, ya, Xb, yb, *, seed: int = 0) -> dict:
    W0 = train_linear(Xa, ya, steps=300)
    # 旧任务梯度（在任务 A 数据上的平均梯度）
    gA = _logistic_grad(W0, Xa, ya)
    # 无投影 LoRA：直接在 B 上全量微调（会遗忘 A）
    W_plain = W0.copy()
    for _ in range(300):
        W_plain -= 0.1 * _logistic_grad(W_plain, Xb, yb)
    W_geo = geo_lora_finetune(W0, Xb, yb, gA, steps=300)
    return {
        "plain_retention": accuracy(W_plain, Xa, ya),
        "geo_retention": accuracy(W_geo, Xa, ya),
        "improvement_pp": (accuracy(W_geo, Xa, ya) - accuracy(W_plain, Xa, ya)) * 100.0,
        "task_b_acc": accuracy(W_geo, Xb, yb),
    }
