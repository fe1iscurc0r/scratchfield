"""Reservoir Computing（Echo State Network 简化版，D-02 · 漂移补偿前端）

固定随机 reservoir（输入投影 + 循环矩阵，谱半径 < 1）+ 可训练读出层
（岭回归闭式解）。计算量小（numpy 矩阵乘），固定随机种子可复现，
适合 ESP32-S3 MCU 移植。

状态更新:
    h_t = (1 - leak) * h_{t-1} + leak * tanh(W @ h_{t-1} + W_in @ u_t)

读出层（岭回归）:
    W_out = (S^T S + λ I)^{-1} S^T Y   （S = 状态矩阵 + bias 列）
"""
from __future__ import annotations

import numpy as np


def _augment(states: np.ndarray) -> np.ndarray:
    """状态矩阵右侧追加 bias 列。"""
    states = np.asarray(states, dtype=float)
    if states.ndim == 1:
        states = states[:, None]
    return np.hstack([states, np.ones((states.shape[0], 1))])


class Reservoir:
    """固定随机 reservoir + 可训练读出层的简化 ESN。"""

    def __init__(self, n_units: int = 64, input_dim: int = 1,
                 spectral_radius: float = 0.9, input_scaling: float = 1.0,
                 leaking_rate: float = 0.3, seed: int = 0) -> None:
        if int(n_units) <= 0 or int(input_dim) <= 0:
            raise ValueError("n_units / input_dim 必须为正整数")
        if not (0.0 < float(spectral_radius) < 1.0):
            raise ValueError(f"spectral_radius 必须在 (0,1)，实际 {spectral_radius}")
        if not (0.0 < float(leaking_rate) <= 1.0):
            raise ValueError(f"leaking_rate 必须在 (0,1]，实际 {leaking_rate}")
        self.n_units = int(n_units)
        self.input_dim = int(input_dim)
        self.spectral_radius = float(spectral_radius)
        self.input_scaling = float(input_scaling)
        self.leaking_rate = float(leaking_rate)
        rng = np.random.default_rng(seed)
        self.W_in = rng.uniform(-1.0, 1.0, (self.n_units, self.input_dim)) * self.input_scaling
        w = rng.uniform(-1.0, 1.0, (self.n_units, self.n_units))
        rho = float(np.max(np.abs(np.linalg.eigvals(w))))
        if rho < 1e-12:
            rho = 1.0
        self.W = w * (self.spectral_radius / rho)  # 谱半径归一
        self.state = np.zeros(self.n_units)
        self.W_out: np.ndarray | None = None
        self._precision: np.ndarray | None = None  # (S^T S + λI)^-1，供在线 RLS 更新

    def reset(self) -> None:
        self.state = np.zeros(self.n_units)

    def _step(self, u: np.ndarray) -> np.ndarray:
        pre = self.W @ self.state + self.W_in @ u
        new = np.tanh(pre)
        self.state = (1.0 - self.leaking_rate) * self.state + self.leaking_rate * new
        return self.state.copy()

    def run(self, inputs, warmup: int = 0) -> np.ndarray:
        """逐样本驱动 reservoir，返回状态矩阵 (T, n_units)，丢弃前 warmup 个瞬态。"""
        inputs = np.asarray(inputs, dtype=float)
        if inputs.ndim == 1:
            inputs = inputs[:, None]
        if inputs.shape[1] != self.input_dim:
            raise ValueError(f"输入维度 {inputs.shape[1]} != input_dim {self.input_dim}")
        self.reset()
        t_len = inputs.shape[0]
        states = np.zeros((t_len, self.n_units))
        for t in range(t_len):
            states[t] = self._step(inputs[t])
        return states[int(warmup):]

    def train_readout(self, states, targets, ridge: float = 1e-6) -> np.ndarray:
        """岭回归训练读出层，返回 W_out（形状 (n_units+1, out_dim)）。"""
        states = np.asarray(states, dtype=float)
        targets = np.asarray(targets, dtype=float)
        if targets.ndim == 1:
            targets = targets[:, None]
        if states.shape[0] != targets.shape[0]:
            raise ValueError(f"状态/目标长度不一致: {states.shape[0]} vs {targets.shape[0]}")
        s = _augment(states)
        a = s.T @ s + float(ridge) * np.eye(s.shape[1])
        b = s.T @ targets
        self.W_out = np.linalg.solve(a, b)
        self._precision = np.linalg.inv(a)
        return self.W_out

    def predict(self, states) -> np.ndarray:
        """读出层前向：状态 → 输出（单输出列时返回一维）。"""
        if self.W_out is None:
            raise RuntimeError("读出层未训练，先调用 train_readout")
        out = _augment(np.asarray(states, dtype=float)) @ self.W_out
        return out[:, 0] if out.shape[1] == 1 else out
