"""R08 · 谱约束信道预测原型（构造性自回归稳定）

灵感：digest-g1-4 授粉点① · 论文 2608.25744（MPNO）。核心：把「谱半径 ≤ 1」
作为**架构设计约束**（构造性编码进网络），而非训练时的软正则，从而保证
递归展开的自回归稳定性——CSI 多步预测不随时间发散。

本原型用一个线性储层（linear reservoir）作为信道预测器：
  h_{t+1} = W h_t + W_in·x_t
  ŷ_{t+1} = W_out h_t
  - W 为递归权重，构造性谱归一化使 ρ(W)=target_radius；
  - W_out 由 ridge 回归离线拟合（只训读出层，储层随机但谱受控）。

稳定性判据：线性递归 h_{t+1}=W h_t + … 的齐次解按 ρ(W)^t 演化——ρ(W)≤1 有界，
ρ(W)>1 指数发散。tanh-RNN 会因激活饱和掩盖发散，故此处用线性激活让谱约束的
作用清晰可见（与 MPNO 处理强不连续 PDE 的自回归不稳定同一机制）。

运行：python -m mcpserver.rf_brain.prototypes.spectral_constrained_predictor
"""
from __future__ import annotations

import numpy as np


def spectral_radius(W: np.ndarray) -> float:
    """谱半径 ρ(W) = max|λ(W)|。"""
    return float(np.max(np.abs(np.linalg.eigvals(W))))


def spectral_normalize(W: np.ndarray, target_radius: float) -> np.ndarray:
    """构造性谱归一化：W ← W·target/ρ(W)，使 ρ(W)=target。"""
    r = spectral_radius(W)
    if r <= 0.0:
        return W
    return W * (target_radius / r)


def synthesize_csi(n: int, *, num_paths: int = 2, seed: int = 0) -> np.ndarray:
    """合成多径衰落 CSI（多正弦叠加，归一化到 [-1,1]，模拟带限慢衰落信道）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    h = np.zeros(n)
    for _ in range(num_paths):
        f = rng.uniform(0.01, 0.04)           # 归一化多普勒频偏
        phi = rng.uniform(0.0, 2.0 * np.pi)
        a = rng.uniform(0.5, 1.0)
        h += a * np.sin(2.0 * np.pi * f * t + phi)
    return h / np.max(np.abs(h))


class LinearReservoir:
    """线性储层信道预测器（谱半径可构造性控制）。"""

    def __init__(self, hidden: int = 32, spectral_radius: float = 0.9,
                 input_scale: float = 0.5, seed: int = 0) -> None:
        rng = np.random.default_rng(seed)
        W = rng.standard_normal((hidden, hidden))
        self.W = spectral_normalize(W, spectral_radius)
        self.W_in = rng.standard_normal((hidden, 1)) * input_scale
        self.W_out = None
        self.hidden = hidden

    def _drive(self, seq: np.ndarray, h0: np.ndarray | None = None) -> np.ndarray:
        """驱动储层，返回每个时步的隐藏状态 (T, H)。"""
        T = seq.size
        H = np.zeros((T, self.hidden))
        h = np.zeros(self.hidden) if h0 is None else h0
        for t in range(T):
            h = self.W @ h + self.W_in[:, 0] * seq[t]
            H[t] = h
        return H

    def train(self, seq: np.ndarray, *, reg: float = 1e-6, washout: int = 10) -> None:
        """ridge 拟合读出层 W_out：从 h_t 预测 seq[t+1]。"""
        H = self._drive(seq)
        X = H[washout:-1]
        y = seq[washout + 1:]
        self.W_out = np.linalg.solve(X.T @ X + reg * np.eye(self.hidden), X.T @ y)

    def rollout(self, init_seq: np.ndarray, n_steps: int) -> np.ndarray:
        """自回归多步预测（feedback 自己的预测）。返回预测序列。"""
        H = self._drive(init_seq)
        h = H[-1]
        preds = [init_seq[-1]]
        x = init_seq[-1]
        for _ in range(n_steps):
            h = self.W @ h + self.W_in[:, 0] * x
            x = float(self.W_out @ h)
            preds.append(x)
        return np.array(preds)

    def hidden_norm_curve(self, init_seq: np.ndarray, n_steps: int) -> np.ndarray:
        """多步 rollout 的隐藏状态范数曲线（稳定性判据）。"""
        H = self._drive(init_seq)
        h = H[-1]
        norms = [float(np.linalg.norm(h))]
        x = init_seq[-1]
        for _ in range(n_steps):
            h = self.W @ h + self.W_in[:, 0] * x
            x = float(self.W_out @ h)
            norms.append(float(np.linalg.norm(h)))
        return np.array(norms)


def rollout_mse(preds: np.ndarray, truth: np.ndarray) -> float:
    """预测与真值的均方误差。"""
    m = min(preds.size, truth.size)
    return float(np.mean((preds[:m] - truth[:m]) ** 2))


def main() -> None:
    n = 400
    csi = synthesize_csi(n)
    train, test = csi[:300], csi[300:]
    init = test[:10]

    for rho in (0.95, 1.3):
        model = LinearReservoir(hidden=32, spectral_radius=rho)
        model.train(train)
        preds = model.rollout(init, len(test) - 10)
        err = rollout_mse(preds, test[9:])
        tag = "谱约束(ρ=0.95)" if rho < 1 else "无约束(ρ=1.30)"
        print(f"{tag:<16} 多步预测 MSE = {err:.3f}  末隐藏范数 = "
              f"{model.hidden_norm_curve(init, len(test)-10)[-1]:.1f}")


if __name__ == "__main__":
    main()
