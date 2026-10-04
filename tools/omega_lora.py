"""工具链 · Omega-S 弹性惩罚 LoRA（R58）

授粉自 digest-g1-2 2608.03887v1（Omega-S：无需先前数据 / Fisher 信息的弹性惩罚，
把 LoRA 微调保留率从 62.9% 提到 84.1%）。核心：用「弹性加权惩罚」保护重要权重，
抑制微调新任务时的灾难性遗忘——重要性代理只用**权重本身的量级**（|W|），不依赖
Fisher 信息（Fisher 需要先前数据或额外 Hessian 计算，端侧/无先验场景不可用）。

原型（纯 numpy，无新依赖）：
  - 线性分类器 + 低秩 LoRA 适配器 W = W0 + B·A（B∈R^{1×r}, A∈R^{r×D}）
  - Omega-S 弹性惩罚 Ω = λ·Σ_j |W0_j|·(ΔW_j)²，ΔW=B·A
  - 两任务持续学习：先训任务 A，再 LoRA 微调任务 B，对比「无惩罚」vs「Omega-S」
    对任务 A 的保留率

验收口径：Omega-S 较无惩罚 LoRA 的旧任务保留率提升 ≥10pp，且不引入新依赖。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "logistic_loss_and_grad",
    "accuracy",
    "train_linear",
    "LoRAModel",
    "retention_experiment",
]


def logistic_loss_and_grad(W: np.ndarray, X: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    """逻辑损失 + 梯度。W:(D,)，X:(N,D)，y:(N,)∈{-1,+1}。返回 (loss, grad(W))。"""
    z = X @ W
    loss = float(np.mean(np.log1p(np.exp(-y * z))))
    grad = -(X.T @ (y / (1.0 + np.exp(y * z)))) / y.size
    return loss, grad


def accuracy(W: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    """二分类准确率（sign(W·x) vs y）。"""
    return float(np.mean(np.sign(X @ W) == y))


def train_linear(X: np.ndarray, y: np.ndarray, *, lr: float = 0.1, steps: int = 300,
                 w0: np.ndarray | None = None) -> np.ndarray:
    """逻辑回归训练线性分类器（返回权重向量）。"""
    d = X.shape[1]
    W = np.zeros(d, dtype=float) if w0 is None else np.asarray(w0, dtype=float).copy()
    for _ in range(steps):
        _, g = logistic_loss_and_grad(W, X, y)
        W -= lr * g
    return W


class LoRAModel:
    """线性分类器 + 低秩 LoRA 适配器，可选 Omega-S 弹性惩罚。

    W = W0 + B·A（B∈R^{1×r}, A∈R^{r×D}）。fine_tune 在任务 B 上更新 (B,A)；
    omega_lambda>0 时加弹性惩罚 Ω=λ·Σ_j |W0_j|·(B·A)_j²，保护 |W0_j| 大的权重。
    """

    def __init__(self, w0: np.ndarray, *, rank: int = 2, omega_lambda: float = 0.0,
                 seed: int = 0) -> None:
        self.w0 = np.asarray(w0, dtype=float)
        d = self.w0.size
        if rank < 1 or rank > d:
            raise ValueError(f"rank 须在 [1, {d}]")
        rng = np.random.default_rng(seed)
        self.B = rng.standard_normal((1, rank)) * 0.01   # 小初始化，避免扰动 W0
        self.A = rng.standard_normal((rank, d)) * 0.01
        self.omega_lambda = float(omega_lambda)
        self.importance = np.abs(self.w0)                 # 重要性代理（无 Fisher）

    def delta(self) -> np.ndarray:
        """LoRA 增量 ΔW = B·A（1×D）。"""
        return self.B @ self.A

    def weights(self) -> np.ndarray:
        """当前有效权重 W0 + ΔW。"""
        return self.w0 + self.delta()

    def fine_tune(self, X: np.ndarray, y: np.ndarray, *, lr: float = 0.1,
                  steps: int = 300) -> "LoRAModel":
        """在任务 B 上微调 (B,A)，带可选弹性惩罚。"""
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        lam = self.omega_lambda
        for _ in range(steps):
            W = self.weights().ravel()
            z = X @ W
            g = -(X.T @ (y / (1.0 + np.exp(y * z)))) / y.size   # (D,)
            dW = self.delta().ravel()
            if lam > 0.0:
                g = g + 2.0 * lam * self.importance * dW       # 弹性惩罚梯度
            g = g.reshape(1, -1)                               # (1,D)
            # 反向传播到 B, A：dL/dB = g @ A^T，dL/dA = B^T @ g
            self.B -= lr * (g @ self.A.T)
            self.A -= lr * (self.B.T @ g)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.sign(X @ self.weights().ravel())


@dataclass
class RetentionResult:
    """保留率对比结果。"""
    plain_retention: float      # 无惩罚 LoRA 微调后任务 A 准确率
    omega_retention: float      # Omega-S 弹性惩罚后任务 A 准确率
    improvement_pp: float       # 保留率提升（percentage points）
    omega_task_b_acc: float     # Omega-S 下任务 B 准确率（记录 plasticity）


def retention_experiment(
    X_a: np.ndarray, y_a: np.ndarray,
    X_b: np.ndarray, y_b: np.ndarray,
    *,
    rank: int = 2,
    omega_lambda: float = 0.05,
    lr: float = 0.1,
    steps: int = 300,
    seed: int = 0,
) -> RetentionResult:
    """跑一次保留率对比：先训任务 A，再 LoRA 微调 B，测任务 A 保留率。"""
    w0 = train_linear(X_a, y_a, lr=lr, steps=steps)

    plain = LoRAModel(w0, rank=rank, omega_lambda=0.0, seed=seed).fine_tune(X_b, y_b, lr=lr, steps=steps)
    omega = LoRAModel(w0, rank=rank, omega_lambda=omega_lambda, seed=seed).fine_tune(X_b, y_b, lr=lr, steps=steps)

    plain_ret = accuracy(plain.weights().ravel(), X_a, y_a)
    omega_ret = accuracy(omega.weights().ravel(), X_a, y_a)
    return RetentionResult(
        plain_retention=plain_ret,
        omega_retention=omega_ret,
        improvement_pp=(omega_ret - plain_ret) * 100.0,
        omega_task_b_acc=accuracy(omega.weights().ravel(), X_b, y_b),
    )


def overlapping_tasks(d: int = 8, n: int = 800, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """构造两个「部分重叠」的二分类任务：任务 A 用特征 0,1，任务 B 翻转特征 1、
    保留特征 0——微调 B 会系统性破坏 A（灾难性遗忘），Omega-S 应保护被破坏的权重。
    """
    rng = np.random.default_rng(seed)
    w_a = np.zeros(d); w_a[0] = 1.0; w_a[1] = 1.0
    w_b = np.zeros(d); w_b[0] = 1.0; w_b[1] = -1.0
    X_a = rng.standard_normal((n, d)); y_a = np.sign(X_a @ w_a)
    X_b = rng.standard_normal((n, d)); y_b = np.sign(X_b @ w_b)
    return X_a, y_a, X_b, y_b
