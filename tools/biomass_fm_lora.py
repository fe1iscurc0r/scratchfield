"""M34 Foundation Model + LoRA 生物质边缘部署 · 最小原型。

授粉源：round3 digest-g2a-2026-08-31.md 2608.28207/2608.28161（DINOv2-LoRA 糖尿病
视网膜分类、芒果品种识别：预训练大模型 + LoRA 微调可在 4M 参数级低成本获得实用精度）。

本原型演示「冻结 FM 主干 + LoRA 低秩适配」范式（numpy，无 torch 依赖）：
  - 主干（FM 编码器）= 冻结，输出特征（真实场景为 DINOv2 的冻结特征）；
  - 分类头 W0 = 冻结随机初始化；LoRA 适配 = 低秩更新 ΔW = B @ A（r ≪ 维度）；
  - 只训练 LoRA 的 B/A，对比「零样本 / 全量微调头 / LoRA 微调」的参数量与精度。

验收：含模型选型 + 参数/内存预算 + 精度评估（见 test_biomass_fm_lora.py 与方案文档）。
"""
from __future__ import annotations

import numpy as np

D_FEAT = 512      # 冻结主干输出特征维（真实场景 = DINOv2 特征维）
N_CLASSES = 8     # 材料成分类别数


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def make_dataset(n_per_class: int = 60, seed: int = 0):
    """合成「冻结主干输出特征 + 材料类别」（8 类高斯簇，模拟 FM 特征空间）。"""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for c in range(N_CLASSES):
        mean = rng.normal(0.0, 1.0, size=D_FEAT)
        for _ in range(n_per_class):
            X.append(mean + rng.normal(0.0, 0.6, size=D_FEAT))
            y.append(c)
    return np.asarray(X), np.asarray(y)


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def accuracy(logits: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.argmax(logits, axis=1) == y))


def train_full_head(X: np.ndarray, y: np.ndarray, iters: int = 2000,
                    lr: float = 0.2, seed: int = 0) -> np.ndarray:
    """全量微调分类头 W0（n_classes × d_feat），返回 W0。"""
    rng = np.random.default_rng(seed)
    W0 = rng.normal(0.0, 0.02, size=(N_CLASSES, D_FEAT))
    n = X.shape[0]
    onehot = np.zeros((n, N_CLASSES))
    onehot[np.arange(n), y] = 1.0
    for _ in range(iters):
        logits = X @ W0.T
        grad = (_softmax(logits) - onehot) / n
        W0 -= lr * (grad.T @ X)
    return W0


def train_lora_head(X: np.ndarray, y: np.ndarray, W0: np.ndarray, r: int = 4,
                    iters: int = 2000, lr: float = 0.2, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """LoRA 微调：冻结 W0，训练低秩 B（n_classes × r）、A（r × d_feat），W = W0 + B@A。"""
    rng = np.random.default_rng(seed)
    B = rng.normal(0.0, 0.02, size=(N_CLASSES, r))
    A = rng.normal(0.0, 0.02, size=(r, D_FEAT))
    n = X.shape[0]
    onehot = np.zeros((n, N_CLASSES))
    onehot[np.arange(n), y] = 1.0
    for _ in range(iters):
        dW = B @ A                                   # 低秩增量
        logits = X @ (W0 + dW).T
        grad = (_softmax(logits) - onehot) / n       # (n, n_classes)
        # 反传：dB = grad^T @ (A @ X^T)^T = grad^T @ X @ A^T ; dA = B^T @ grad^T @ X
        dB = grad.T @ X @ A.T
        dA = B.T @ grad.T @ X
        B -= lr * dB
        A -= lr * dA
    return B, A


def loRA_param_count(r: int) -> int:
    return N_CLASSES * r + r * D_FEAT


def rank_ablation(X_tr, y_tr, X_te, y_te, W0, ranks=(2, 4, 8, 16)) -> list[tuple[int, int, float]]:
    """LoRA rank 消融：不同 rank 下的可训练参数量与精度（展示紧凑部署权衡）。"""
    out = []
    for r in ranks:
        B, A = train_lora_head(X_tr, y_tr, W0, r=r)
        acc = accuracy(X_te @ (W0 + B @ A).T, y_te)
        out.append((r, loRA_param_count(r), acc))
    return out


def run_demo() -> None:
    X, y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    rng = np.random.default_rng(99)
    W0_zero = rng.normal(0.0, 0.02, size=(N_CLASSES, D_FEAT))  # 零样本（随机头）
    acc_zero = accuracy(X[te] @ W0_zero.T, y[te])

    W0 = train_full_head(X[tr], y[tr])
    acc_full = accuracy(X[te] @ W0.T, y[te])

    B, A = train_lora_head(X[tr], y[tr], W0_zero, r=4)
    acc_lora = accuracy(X[te] @ (W0_zero + B @ A).T, y[te])

    full_params = N_CLASSES * D_FEAT
    lora_params = loRA_param_count(4)
    print(f"[M34] 零样本(随机头)精度 = {acc_zero:.3f}")
    print(f"[M34] 全量微调头精度 = {acc_full:.3f}（可训练 {full_params:,} 参数）")
    print(f"[M34] LoRA(r=4) 精度 = {acc_lora:.3f}（可训练 {lora_params:,} 参数，"
          f"仅全量的 {lora_params / full_params:.2f}）")
    print("[M34] LoRA rank 消融（r → 参数/精度）：")
    for r, n_p, a in rank_ablation(X[tr], y[tr], X[te], y[te], W0_zero):
        print(f"      r={r:2d}  可训练参数={n_p:5d}（全量 {full_params / n_p:4.1f}×） 精度={a:.3f}")


if __name__ == "__main__":
    run_demo()
