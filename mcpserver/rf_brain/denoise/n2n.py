"""Noise2Noise 自监督盲去噪（D-01 · 训练 + 推理）

核心洞察（授粉点）：噪声独立且零均值时，用「两次带噪观测互为目标」训练
去噪网络，MSE 损失最小化等价于逼近干净信号——网络无法预测另一观测里的
独立噪声，只能学到其条件期望 = 干净信号。

实现为纯 numpy 小 MLP（滑窗 → 中心样本），参数量 < 100K，为 MCU 移植留余地。

用法:
    from mcpserver.rf_brain.denoise import n2n
    model = n2n.N2NDenoiser(window=15, hidden=(48, 48), seed=0)
    history = model.train(y1, y2, epochs=40)   # y1/y2 = 两次独立带噪观测
    clean_hat = model.denoise(noisy)            # 对任意带噪信号去噪
"""
from __future__ import annotations

import numpy as np


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _sliding_windows(x: np.ndarray, window: int) -> np.ndarray:
    """返回 (n, window) 滑窗矩阵，每行以样本 i 为中心（边缘填充）。"""
    half = window // 2
    if x.size <= half:
        padded = np.pad(x, (half, half), mode="edge")
    else:
        padded = np.pad(x, (half, half), mode="reflect")
    idx = np.arange(x.size)[:, None] + np.arange(window)
    return padded[idx]


class N2NDenoiser:
    """两层隐藏的窗口 MLP 去噪器（Noise2Noise 训练目标）。"""

    def __init__(self, window: int = 15, hidden: tuple[int, ...] = (48, 48),
                 lr: float = 0.01, momentum: float = 0.9, seed: int = 0) -> None:
        if int(window) < 3 or int(window) % 2 == 0:
            raise ValueError(f"window 必须为 >=3 的奇数（便于中心对齐），实际 {window}")
        if len(hidden) != 2 or min(hidden) <= 0:
            raise ValueError(f"hidden 必须为两个正整数（两层隐藏），实际 {hidden}")
        self.window = int(window)
        self.hidden = tuple(int(h) for h in hidden)
        self.lr = float(lr)
        self.momentum = float(momentum)
        self.rng = np.random.default_rng(seed)
        h1, h2 = self.hidden
        w = self.window
        self.W1 = self.rng.normal(0.0, np.sqrt(2.0 / w), (h1, w))
        self.b1 = np.zeros(h1)
        self.W2 = self.rng.normal(0.0, np.sqrt(2.0 / h1), (h2, h1))
        self.b2 = np.zeros(h2)
        self.W3 = self.rng.normal(0.0, np.sqrt(1.0 / h2), (1, h2))
        self.b3 = np.zeros(1)
        self._vW1 = np.zeros_like(self.W1)
        self._vb1 = np.zeros_like(self.b1)
        self._vW2 = np.zeros_like(self.W2)
        self._vb2 = np.zeros_like(self.b2)
        self._vW3 = np.zeros_like(self.W3)
        self._vb3 = np.zeros_like(self.b3)

    def parameter_count(self) -> int:
        """总参数量（含 bias），验收硬约束 < 100K。"""
        return int(self.W1.size + self.b1.size + self.W2.size + self.b2.size
                   + self.W3.size + self.b3.size)

    def _forward(self, a0: np.ndarray):
        z1 = a0 @ self.W1.T + self.b1
        a1 = _relu(z1)
        z2 = a1 @ self.W2.T + self.b2
        a2 = _relu(z2)
        yhat = a2 @ self.W3.T + self.b3
        return z1, a1, z2, a2, yhat

    def _backward(self, a0, z1, a1, z2, a2, yhat, y):
        b = a0.shape[0]
        dyhat = 2.0 * (yhat - y) / b
        dw3 = dyhat.T @ a2
        db3 = dyhat.sum(axis=0)
        da2 = dyhat @ self.W3
        dz2 = da2 * (z2 > 0)
        dw2 = dz2.T @ a1
        db2 = dz2.sum(axis=0)
        da1 = dz2 @ self.W2
        dz1 = da1 * (z1 > 0)
        dw1 = dz1.T @ a0
        db1 = dz1.sum(axis=0)
        return dw1, db1, dw2, db2, dw3, db3

    def _sgd_step(self, grads) -> None:
        dw1, db1, dw2, db2, dw3, db3 = grads
        m = self.momentum
        self._vW1 = m * self._vW1 - self.lr * dw1
        self.W1 += self._vW1
        self._vb1 = m * self._vb1 - self.lr * db1
        self.b1 += self._vb1
        self._vW2 = m * self._vW2 - self.lr * dw2
        self.W2 += self._vW2
        self._vb2 = m * self._vb2 - self.lr * db2
        self.b2 += self._vb2
        self._vW3 = m * self._vW3 - self.lr * dw3
        self.W3 += self._vW3
        self._vb3 = m * self._vb3 - self.lr * db3
        self.b3 += self._vb3

    def train(self, y1, y2, epochs: int = 40, batch_size: int = 128) -> list[float]:
        """用两次带噪观测训练去噪网络，返回每 epoch 平均 MSE 损失。

        y1/y2 为同长一维数组（同一干净信号 x 的两次独立带噪观测）。
        """
        y1 = np.asarray(y1, dtype=float)
        y2 = np.asarray(y2, dtype=float)
        if y1.ndim != 1 or y2.ndim != 1:
            raise ValueError("y1/y2 必须为一维数组")
        if y1.shape != y2.shape:
            raise ValueError(f"两次观测长度不一致: {y1.shape} vs {y2.shape}")
        if y1.size < self.window:
            raise ValueError(f"样本过短 ({y1.size})，需 >= window ({self.window})")
        x = _sliding_windows(y1, self.window)
        y = y2[:, None]
        n = x.shape[0]
        history: list[float] = []
        for _ in range(int(epochs)):
            perm = self.rng.permutation(n)
            losses: list[float] = []
            for start in range(0, n, int(batch_size)):
                idx = perm[start:start + int(batch_size)]
                xb, yb = x[idx], y[idx]
                z1, a1, z2, a2, yhat = self._forward(xb)
                losses.append(float(np.mean((yhat - yb) ** 2)))
                self._sgd_step(self._backward(xb, z1, a1, z2, a2, yhat, yb))
            history.append(float(np.mean(losses)))
        return history

    def denoise(self, x) -> np.ndarray:
        """对一维信号去噪，返回干净估计。空/过短输入原样返回（容错）。"""
        x = np.asarray(x, dtype=float)
        if x.ndim != 1:
            raise ValueError("输入必须为一维")
        if x.size == 0:
            return np.zeros(0, dtype=float)
        if x.size < self.window:
            return x.copy()
        xw = _sliding_windows(x, self.window)
        _, _, _, _, yhat = self._forward(xw)
        return yhat[:, 0]
