"""R05 · Score-based 轻量频谱检测原型（去噪得分匹配）

灵感：digest-g8-3a 授粉点② · 论文 2608.24768（Score-based Ideal Observer，SIO）。

核心思想（免逐调制训练）：
  1. 只在「纯噪声」样本上用 denoising score matching (DSM) 训练一个得分函数
     f(x) ≈ ∇ₓ log p_τ(x)，p_τ 是噪声分布被 N(0,τ²) 平滑后的分布。
     DSM 目标 = -ε/τ²（ε 为加性扰动），最小二乘闭式解即为该得分的最优估计。
  2. 检测统计量 T(x) = ‖ f(x) ‖²（得分模长）：噪声下小，叠加任意调制信号后增大。
  3. 阈值由纯噪声统计量分位数标定（固定虚警率），对**任意调制样式**通用。

一份「仅噪声训练」的得分模型即可检测 BPSK/QPSK/FSK/OOK 等所有加性调制，
无需逐调制训练——训练与推理完全解耦，正是 SIO 的核心卖点。

理论注记：高斯噪声的得分是线性的（f(x) = -x/(σ²+τ²)），故 T(x) 退化为能量
检测；当噪声非高斯（脉冲/重尾）时得分变非线性，score-based 才真正优于能量
检测——本原型的框架对两者通用，仅需把线性回归换成非线性模型。

int8 定点化要点：
  - 得分矩阵 A（n×n）离线量化到 int8（对称量化，scale = max|A|/127），
    推理时用 int8 矩阵乘 + int32 累加，节点端免浮点。
  - 统计量 T = Σ s² 用定点平方 + 移位累加，阈值用定点比较。
  - 输入 x 用 Q7（[-128,127] 表示 [-1,1]）量化，噪声标定表离线生成。

运行：python -m mcpserver.rf_brain.prototypes.score_detector
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------- #
# 信号合成
# --------------------------------------------------------------------------- #

def synthesize_modulations(n: int, mod: str, *, rng: np.random.Generator) -> np.ndarray:
    """合成一条归一化（单位平均能量 = 1）的调制信号样本（长度 n）。"""
    if mod == "BPSK":
        x = 2.0 * (rng.integers(0, 2, n) - 0.5)              # ±1
    elif mod == "QPSK":
        i = (rng.integers(0, 2, n) * 2 - 1).astype(float)
        x = i / np.sqrt(2.0)                                 # I 分量 ±1/√2
    elif mod == "FSK":
        bits = rng.integers(0, 2, n)
        inst = np.where(bits == 0, 0.1, 0.3)                 # 归一化瞬时频率
        x = np.sin(2 * np.pi * np.cumsum(inst))
    elif mod == "OOK":
        x = rng.integers(0, 2, n).astype(float)              # {0,1}
    else:
        raise ValueError(f"未知调制: {mod}")
    e = float(np.mean(x ** 2))
    return x / np.sqrt(e) if e > 0 else x                     # 统一单位平均能量


# --------------------------------------------------------------------------- #
# 去噪得分匹配（DSM）：线性得分的最小二乘闭式解
# --------------------------------------------------------------------------- #

def train_score_model(
    *,
    n: int = 32,
    sigma: float = 1.0,
    tau: float = 0.5,
    n_train: int = 1024,
    reg: float = 1e-3,
    seed: int = 0,
) -> tuple:
    """在纯高斯噪声上训练线性得分 f(x) = A·x。

    DSM 目标 = -ε/τ²；ridge 闭式解 A = (XᵀX + reg·I)⁻¹ Xᵀ T。
    返回 (A, sigma, tau)。高斯噪声下 A ≈ -I/(σ²+τ²)。
    """
    rng = np.random.default_rng(seed)
    X0 = sigma * rng.standard_normal((n_train, n))
    eps = tau * rng.standard_normal((n_train, n))
    Xt = X0 + eps
    target = -eps / (tau ** 2)
    A = np.linalg.solve(Xt.T @ Xt + reg * np.eye(n), Xt.T @ target)  # (n, n)
    return A, float(sigma), float(tau)


def score(x: np.ndarray, params: tuple) -> np.ndarray:
    """得分向量 f(x) = A·x。"""
    A, _, _ = params
    return A @ np.asarray(x, dtype=float).reshape(-1)


def score_statistic(x: np.ndarray, params: tuple) -> float:
    """检测统计量 T(x) = ‖ f(x) ‖²（得分模长）。"""
    s = score(x, params)
    return float(np.mean(s ** 2))


def calibrate_threshold(params: tuple, *, pfa: float = 0.05, n_cal: int = 2000, seed: int = 1) -> float:
    """用纯噪声标定阈值，使虚警率 = pfa。"""
    A, sigma, _ = params
    n = A.shape[0]
    rng = np.random.default_rng(seed)
    stats = np.array([score_statistic(sigma * rng.standard_normal(n), params)
                      for _ in range(n_cal)])
    return float(np.quantile(stats, 1.0 - pfa))


def detection_rate(params: tuple, mod: str, snr_db: float, *, n_test: int = 500, seed: int = 2) -> float:
    """给定调制与 SNR 的检测率（固定 Pfa）。"""
    A, sigma, _ = params
    n = A.shape[0]
    rng = np.random.default_rng(seed)
    thr = calibrate_threshold(params, pfa=0.05, seed=seed + 7)

    snr_lin = 10.0 ** (snr_db / 10.0)
    hits = 0
    for _ in range(n_test):
        s = synthesize_modulations(n, mod, rng=rng) * np.sqrt(snr_lin) * sigma
        x = s + sigma * rng.standard_normal(n)
        if score_statistic(x, params) > thr:
            hits += 1
    return hits / n_test


def detection_table(params: tuple, snr_db_list=(-10.0, -5.0, 0.0, 5.0)) -> dict:
    """多调制 × 多 SNR 检测率对比表。"""
    mods = ("BPSK", "QPSK", "FSK", "OOK")
    return {m: [detection_rate(params, m, s) for s in snr_db_list] for m in mods}


def main() -> None:
    params = train_score_model(n=32, n_train=2048)
    snrs = (-10.0, -5.0, 0.0, 5.0)
    table = detection_table(params, snrs)
    header = "mod  " + "  ".join(f"{s:>6.1f}dB" for s in snrs)
    print(header)
    for m, rates in table.items():
        print(f"{m:<6}" + "  ".join(f"{r*100:6.1f}%" for r in rates))
    print("\n（同一份仅噪声训练的得分模型，跨 4 种调制免重训练）")


if __name__ == "__main__":
    main()
