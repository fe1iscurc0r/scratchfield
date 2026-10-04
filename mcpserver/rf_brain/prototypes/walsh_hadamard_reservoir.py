"""R66 · Walsh-Hadamard 储层时序建模（无乘法正交算子）

授粉自 round3 digest-g1b Memristive Hadamard RC（2608.28295）：用「符号对角 +
置换 + 快速 Walsh-Hadamard 变换（FWHT）」替代储层计算的密集矩阵乘法——WHT 是
±1 正交矩阵，FWHT 只做加法/减法（无乘法器），O(N) 参数、O(N log N) 运算，
论文实测硬件 50× 加速、内存缩减 4 个数量级。

原型（纯 numpy，无新依赖）：
  - fwht                      快速 Walsh-Hadamard 变换（仅 +/−，无乘法）
  - WalshHadamardReservoir    储层递归算子 = 符号对角 ∘ 置换 ∘ FWHT ∘ tanh，
                              信道状态预测读出层 ridge（离线一次性，含乘法）

对比基线：R08 的 LinearReservoir（密集随机矩阵，谱约束）。
验收口径：信道预测精度较基线 ≥80%，储层递归算子无乘法指令（仅 +/− 与移位）。
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.prototypes.spectral_constrained_predictor import (
    LinearReservoir,
    synthesize_csi,
)

__all__ = ["fwht", "WalshHadamardReservoir", "synthesize_csi", "rollout_corr"]


def fwht(x: np.ndarray) -> np.ndarray:
    """快速 Walsh-Hadamard 变换（蝶形，仅 +/− 运算，无乘法）。

    要求长度 n 为 2 的幂。WHT 是 ±1 正交矩阵，故变换只用加法与减法。
    每层用 numpy 向量化：reshape 成 (n/(2h), 2h) 后一次算完所有蝶形。
    """
    x = np.asarray(x, dtype=float).copy()
    n = x.size
    if n < 1 or (n & (n - 1)) != 0:
        raise ValueError(f"WHT 长度必须为 2 的幂，收到 {n}")
    h = 1
    while h < n:
        x = x.reshape(-1, 2 * h)
        a = x[:, :h].copy()
        b = x[:, h:].copy()
        x[:, :h] = a + b
        x[:, h:] = a - b
        x = x.ravel()
        h *= 2
    return x


class WalshHadamardReservoir:
    """Walsh-Hadamard 储层：递归算子无乘法（符号对角 + 置换 + FWHT）。

    状态更新 h_{t+1} = tanh( (1/√N)·FWHT(D∘P(h_t)) + γ·x_t )：
      - D（符号对角）与 P（置换）只做取负/重排，FWHT 只做 +/−；
      - 1/√N 与 γ 是标量缩放（MCU 上用定点移位近似），tanh 用查表。
    读出层 W_out 由 ridge 回归离线拟合（一次性，含乘法，不参与递归）。
    """

    def __init__(self, hidden: int = 64, input_scale: float = 0.5, seed: int = 0) -> None:
        if hidden < 1 or (hidden & (hidden - 1)) != 0:
            raise ValueError(f"hidden 必须为 2 的幂，收到 {hidden}")
        rng = np.random.default_rng(seed)
        self.hidden = int(hidden)
        self.sign = rng.choice([-1.0, 1.0], size=hidden)          # 符号对角
        self.perm = rng.permutation(hidden)                        # 置换
        self.gamma = float(input_scale)
        self.inv_norm = 1.0 / np.sqrt(hidden)                      # 1/√N 归一化
        self.W_out: np.ndarray | None = None

    def _recurrent(self, h: np.ndarray) -> np.ndarray:
        """储层递归算子：符号对角 ∘ 置换 ∘ FWHT（仅 +/− 与重排）。"""
        return fwht(self.sign * h[self.perm]) * self.inv_norm

    def _drive(self, seq: np.ndarray, h0: np.ndarray | None = None) -> np.ndarray:
        """驱动储层，返回每个时步隐藏状态 (T, H)。"""
        T = seq.size
        H = np.zeros((T, self.hidden))
        h = np.zeros(self.hidden) if h0 is None else h0.copy()
        for t in range(T):
            h = np.tanh(self._recurrent(h) + self.gamma * seq[t])
            H[t] = h
        return H

    def train(self, seq: np.ndarray, *, reg: float = 1e-6, washout: int = 10) -> None:
        """ridge 拟合读出层 W_out：从 h_t 预测 seq[t+1]。"""
        H = self._drive(np.asarray(seq, dtype=float))
        X = H[washout:-1]
        y = seq[washout + 1:]
        self.W_out = np.linalg.solve(X.T @ X + reg * np.eye(self.hidden), X.T @ y)

    def rollout(self, init_seq: np.ndarray, n_steps: int) -> np.ndarray:
        """自回归多步预测（feedback 自己的预测）。返回预测序列（含首值）。"""
        H = self._drive(np.asarray(init_seq, dtype=float))
        h = H[-1]
        x = init_seq[-1]
        preds = [x]
        for _ in range(n_steps):
            h = np.tanh(self._recurrent(h) + self.gamma * x)
            x = float(self.W_out @ h)
            preds.append(x)
        return np.array(preds)


def rollout_corr(preds: np.ndarray, truth: np.ndarray) -> float:
    """预测与真值的皮尔逊相关系数（精度度量，越接近 1 越好）。"""
    p = np.asarray(preds, dtype=float)
    t = np.asarray(truth, dtype=float)
    m = min(p.size, t.size)
    p, t = p[:m], t[:m]
    if p.std() < 1e-12 or t.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(p, t)[0, 1])
