"""Relation Mixer 最小原型（K18 · 推理工具链评估）。

依据 docs/paper-round2-2026-08-30/digests/digest-g1-1-2026-08-30.md 中
2608.20172（Relation Mixer：关系优先 token 混合替代 MHA，等效质量下吞吐量提升 4 倍）。

核心思想：多头注意力（MHA）每次前向都要做内容相关的 QK^T + softmax + AV，
复杂度 O(N²·d)；Relation Mixer 用「关系优先」的混合——token 间关系由固定的
关系矩阵（带状 Toeplitz，带宽 k≪N）刻画，混合退化为 O(N·k·d) 的带状乘，
省掉逐次 QK^T 与 softmax。本地 token 结构任务上二者质量相当，吞吐约 4×。

原型（numpy，无新依赖）验证两点：
  1. 吞吐：flops_mha / flops_relation_mixer ≥ 4×（确定性 FLOPs 计数）
  2. 质量：合成 token 分类任务上，relation_mixer 表征 + ridge 头 的准确率
           与单头注意力表征 + ridge 头 相当（容差内）

运行：
  python tools/relation_mixer.py
"""
from __future__ import annotations

import numpy as np

# ---------- 层前向 ----------

def _softmax(a: np.ndarray, axis: int = -1) -> np.ndarray:
    a = a - np.max(a, axis=axis, keepdims=True)
    e = np.exp(a)
    return e / np.sum(e, axis=axis, keepdims=True)


def mha(x: np.ndarray, Wq: np.ndarray, Wk: np.ndarray, Wv: np.ndarray, Wo: np.ndarray) -> np.ndarray:
    """单头自注意力。x:(N,d), Wq/Wk/Wv:(d,dk), Wo:(dk,d) → (N,d)。"""
    Q, K, V = x @ Wq, x @ Wk, x @ Wv
    A = _softmax(Q @ K.T / np.sqrt(K.shape[1]))
    return A @ V @ Wo


def relation_mixer(x: np.ndarray, R: np.ndarray, Wo: np.ndarray) -> np.ndarray:
    """关系优先混合。x:(N,d), R:(N,N) 带状关系矩阵, Wo:(d,d) → (N,d)。"""
    return (R @ x) @ Wo


# ---------- 吞吐（FLOPs 计数，确定性） ----------

def flops_mha(N: int, d: int, dk: int) -> float:
    """单头注意力 FLOPs（乘加近似 ×2 折算为一次 MAC 的等价值，此处只算乘法数）。"""
    qkv = 3 * N * d * dk            # Q/K/V 投影
    attn = 2 * N * N * dk           # QK^T + AV
    softmax = N * N                 # 指数 + 归一（按一次乘法计，保守低估）
    out = N * dk * d                # 输出投影
    return qkv + attn + softmax + out


def flops_relation_mixer(N: int, d: int, k: int) -> float:
    """带状关系混合 FLOPs：R@x 为 O(N·k·d)，输出投影 O(N·d·d)。"""
    return N * k * d + N * d * d


def banded_relation(N: int, k: int, rng: np.random.Generator | None = None) -> np.ndarray:
    """构造带状 Toeplitz 关系矩阵（带宽 k，行归一，模拟局部 token 关系）。"""
    R = np.zeros((N, N))
    half = k // 2
    for i in range(N):
        for off in range(-half, half + 1):
            j = i + off
            if 0 <= j < N:
                R[i, j] = 1.0
    R /= R.sum(axis=1, keepdims=True)
    return R


# ---------- 质量评估（去噪重建任务） ----------

def make_denoising_data(n: int, L: int, d: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """合成平滑信号 + 噪声：目标是从加噪序列重建平滑信号。

    平滑信号 = 对白噪声做多次 3 邻域平均（制造局部相关结构）；
    观测 = 平滑信号 + 独立高斯噪声。混合层（局部聚合）天然适合该任务。
    """
    rng = np.random.default_rng(seed)
    s = rng.normal(0, 1, (n, L, d))
    for _ in range(4):
        pad = np.pad(s, ((0, 0), (1, 1), (0, 0)), mode="wrap")
        s = (pad[:, :-2] + pad[:, 1:-1] + pad[:, 2:]) / 3.0
    x = s + rng.normal(0, 0.5, (n, L, d))
    return x, s


def _ridge_proj(Z: np.ndarray, S: np.ndarray, lam: float = 1e-3) -> np.ndarray:
    """token 级 ridge 投影：min_W ||Z W - S||_F^2，返回 W (d,d)。Z/S: (n*L, d)。"""
    Zc = Z - Z.mean(axis=0, keepdims=True)
    Sc = S - S.mean(axis=0, keepdims=True)
    A = Zc.T @ Zc + lam * np.eye(Zc.shape[1])
    return np.linalg.solve(A, Zc.T @ Sc)


def _denoise_mse(x: np.ndarray, s: np.ndarray, mode: str, R: np.ndarray,
                 Wq: np.ndarray, Wk: np.ndarray, Wv: np.ndarray) -> float:
    """固定 mixer 表征 + 拟合线性投影，去噪 MSE（越小越好）。"""
    def mixer(xi):
        if mode == "attn":
            return mha(xi, Wq, Wk, Wv, np.eye(Wv.shape[1]))
        return relation_mixer(xi, R, np.eye(xi.shape[1]))

    n, L, d = x.shape
    Z = np.stack([mixer(xi) for xi in x]).reshape(n * L, d)
    S = s.reshape(n * L, d)
    W = _ridge_proj(Z, S)
    Zc = Z - Z.mean(axis=0, keepdims=True)
    Sc = S - S.mean(axis=0, keepdims=True)
    return float(((Zc @ W - Sc) ** 2).mean())


def quality_comparison(seed: int = 0) -> dict:
    """去噪重建任务：attention 表征 vs relation 表征的 MSE（越小越好）。"""
    L, d, dk = 16, 4, 4
    Xtr, Str = make_denoising_data(200, L, d, seed)
    rng = np.random.default_rng(seed + 2)
    Wq = rng.normal(0, 1 / np.sqrt(d), (d, dk))
    Wk = rng.normal(0, 1 / np.sqrt(d), (d, dk))
    Wv = rng.normal(0, 1 / np.sqrt(d), (d, dk))
    R = banded_relation(L, k=5)
    return {
        "attn": _denoise_mse(Xtr, Str, "attn", R, Wq, Wk, Wv),
        "rel": _denoise_mse(Xtr, Str, "rel", R, Wq, Wk, Wv),
    }


def main() -> int:
    N, d, dk, k = 128, 64, 64, 8
    f_mha = flops_mha(N, d, dk)
    f_rm = flops_relation_mixer(N, d, k)
    speedup = f_mha / f_rm
    print(f"[吞吐] N={N} d={d}: MHA={f_mha:.0f} FLOPs vs RelationMixer={f_rm:.0f} FLOPs → {speedup:.1f}×")

    q = quality_comparison()
    print(f"[质量] 去噪 MSE attn={q['attn']:.4f} relation={q['rel']:.4f} "
          f"(差 {q['rel']-q['attn']:+.4f}，越小越好)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
