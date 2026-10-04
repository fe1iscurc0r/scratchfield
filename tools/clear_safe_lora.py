"""工具链 · CLEAR 安全 LoRA（R73）

授粉自 2608.21278v1（CLEAR）：连续潜在适配器路由的安全对齐——不用单一安全
分类器，而是用「隐藏状态门控」在安全适配器与基础适配器之间做连续路由，把不安全
输入导向安全 LoRA，攻击成功率（ASR）从 32.3% 降到 0.5%。

原型（纯 numpy，无新依赖，机制清晰版）：
  - W_base   未对齐基础模型（对恶意输入 ASR 高）
  - W_aligned 对齐模型（正确拒掉恶意）
  - 安全适配器 ΔW = W_aligned − W_base（低秩校正，可用 SVD 截断）
  - 门控 g(x) = sigmoid(a_g·x + b_g)（P(恶意)，连续路由）
  - 输出 logit = (W_base + g(x)·ΔW)·x：安全输入 g≈0 保持基础行为，恶意输入 g→1 拒掉

验收口径：gated 安全 LoRA 把 ASR 显著压低（原型合成场景 < 5%），同时保留安全输入效用。
"""
from __future__ import annotations

import numpy as np

__all__ = ["synthesize_safety_data", "asr", "fit_clear", "ClearSafeLoRA"]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50.0, 50.0)))


def synthesize_safety_data(n: int = 800, d: int = 8, seed: int = 0) -> tuple:
    """合成：安全输入（y=+1，应响应）+ 恶意输入（y=-1，应拒绝，正交方向）。"""
    rng = np.random.default_rng(seed)
    mu_safe = np.zeros(d)
    mu_safe[0] = 3.0
    X_safe = rng.standard_normal((n, d)) + mu_safe
    y_safe = np.ones(n)
    # 恶意簇：正交方向、良分离（对齐模型可近零 ASR 拒掉）
    mu_harm = np.zeros(d)
    mu_harm[1] = 3.0
    X_harm = rng.standard_normal((n, d)) + mu_harm
    y_harm = -np.ones(n)
    return np.vstack([X_safe, X_harm]), np.concatenate([y_safe, y_harm])


def asr(W: np.ndarray, X_harm: np.ndarray) -> float:
    """攻击成功率：恶意输入被标成「安全」（logit>0）的比例。"""
    return float(np.mean((X_harm @ W) > 0.0))


def _logistic_reg(X: np.ndarray, y: np.ndarray, *, lr: float = 0.05, steps: int = 500) -> np.ndarray:
    W = np.zeros(X.shape[1])
    for _ in range(steps):
        z = X @ W
        W -= lr * (-(X.T @ (y / (1.0 + np.exp(y * z)))) / y.size)
    return W


class ClearSafeLoRA:
    """连续门控安全 LoRA：logit = (W_base + g(x)·ΔW)·x。"""

    def __init__(self, W_base: np.ndarray, W_aligned: np.ndarray,
                 a_g: np.ndarray, b_g: float, *, rank: int | None = None) -> None:
        self.W = np.asarray(W_base, dtype=float)
        dW = np.asarray(W_aligned, dtype=float) - self.W
        if rank is not None:
            dW = _low_rank(dW, rank)                    # 可选 SVD 低秩截断（LoRA 语义）
        self.dW = dW
        self.a_g = np.asarray(a_g, dtype=float)
        self.b_g = float(b_g)

    def gate(self, X: np.ndarray) -> np.ndarray:
        return _sigmoid(X @ self.a_g + self.b_g)

    def logits(self, X: np.ndarray) -> np.ndarray:
        return X @ self.W + self.gate(X) * (X @ self.dW)


def _low_rank(w: np.ndarray, rank: int) -> np.ndarray:
    """SVD 低秩截断（保留 rank 个最大奇异值，返回同形状 (d,)）。"""
    U, s, Vt = np.linalg.svd(w.reshape(1, -1), full_matrices=False)
    s = s.copy()
    s[rank:] = 0.0
    return ((U * s) @ Vt).ravel()


def fit_clear(X: np.ndarray, y: np.ndarray, *, seed: int = 0, flip_ratio: float = 0.32,
              rank: int | None = None) -> tuple[ClearSafeLoRA, np.ndarray, np.ndarray]:
    """拟合：W_base（翻转部分恶意标签模拟未对齐）+ W_aligned（拒恶意）+ 门控。

    返回 (模型, W_base, W_aligned)。翻转 flip_ratio 比例的恶意样本标签为「安全」，
    使 W_base 在恶意上留下约 flip_ratio 的 ASR（模拟未对齐模型）。
    """
    rng = np.random.default_rng(seed)
    y_flip = y.copy()
    harm_idx = np.flatnonzero(y < 0)
    n_flip = int(len(harm_idx) * flip_ratio)
    flip = rng.choice(harm_idx, size=n_flip, replace=False)
    y_flip[flip] = 1.0                                     # 部分恶意被当成安全 → 未对齐
    W_base = _logistic_reg(X, y_flip)
    W_aligned = _logistic_reg(X, y)                        # 全量正确标签 → 对齐
    # 门控 = 逻辑回归预测 P(恶意)：标签 1=恶意（y<0），0=安全
    y_gate = (y < 0).astype(float)
    a_g = _logistic_reg(X, 2.0 * y_gate - 1.0)            # 门控权重（sigmoid 形式）
    model = ClearSafeLoRA(W_base, W_aligned, a_g, 0.0, rank=rank)
    return model, W_base, W_aligned
