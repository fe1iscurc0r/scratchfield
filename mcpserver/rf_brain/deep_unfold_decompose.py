"""射频大脑 · 深度展开信号分解（R52 · IDSD）

授粉自 digest-g8-3b-2026-08-30.md 授粉点（无窄带假设 + 自适应分量迭代提取，
替代固定阈值 CFAR）：把 ISTA/FISTA 软阈值迭代「深度展开」成固定层数的前向网络，
逐层迭代分离「稀疏信号分量」与「干扰 + 噪声残差」，Nesterov 动量加速收敛。

与 CFAR 的本质区别：
  - CFAR 是**检测器**：固定阈值（或滑动窗局部阈值）给出二值「有无信号」判决，
    恢复分量 = 检测点上的原始幅度（含噪声/干扰，不降噪、不估计）。
  - IDSD 是**估计器**：软阈值把噪声收缩掉（幅度减 λ），在稀疏先验下逼近
    LASSO 解 s* ≈ soft(x, λ)，既检测又降噪——合成干扰场景下分量分离精度更高。

字典 D 默认单位阵（频谱域每 bin 即一分量，天然稀疏，对应「无窄带假设」）；
可传入正交/过完备字典做一般稀疏分解。参数量 = 阈值 λ + 步长 μ 两个标量（或
每层一组 ≈ 2×层数），远小于 100K，ESP32 毫秒级窗口可行。

验收口径：合成干扰场景（稀疏信号 + 宽带干扰底 + 噪声）下，分量分离的
重建 SNR 较 CFAR 提升 ≥20%；参数量 <100K。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def soft_threshold(z: np.ndarray, lambd: float) -> np.ndarray:
    """软阈值（逐元素）：soft(z, λ) = sign(z)·max(|z| - λ, 0)。"""
    z = np.asarray(z, dtype=float)
    return np.sign(z) * np.maximum(np.abs(z) - lambd, 0.0)


def recon_snr(s_true: np.ndarray, s_hat: np.ndarray) -> float:
    """分量重建 SNR（线性比）：||s_true||² / ||s_hat - s_true||²。

    越大越好；无穷大当 s_hat == s_true。用于「分量分离精度」的定量对比。
    """
    s = np.asarray(s_true, dtype=float).ravel()
    h = np.asarray(s_hat, dtype=float).ravel()
    num = float(np.dot(s, s))
    den = float(np.dot(h - s, h - s))
    return num / den if den > 1e-15 else float("inf")


@dataclass
class DecomposeResult:
    """一次分解结果。"""
    signal: np.ndarray      # 恢复的稀疏信号分量
    residual: np.ndarray    # 干扰 + 噪声残差（x - D·signal）
    n_iters: int            # 实际迭代层数（提前收敛）
    converged: bool         # 是否在层数内收敛（层间变化 < tol）


class DeepUnfoldDecomposer:
    """深度展开信号分解（ISTA/FISTA + Nesterov）。

    每层：s_{k+1} = soft( s_k + μ_k·Dᵀ(x - D·s_k), λ_k )
    Nesterov（FISTA）：先用动量外推 y，再从 y 做梯度步，收敛更快。
    字典默认单位阵；identity 时 Dᵀ(x - D·s) = x - s，μ=1 时一层即达 LASSO 解。
    """

    def __init__(self, n_layers: int = 8, lambd: float = 1.0, mu: float = 1.0,
                 nesterov: bool = True, dictionary: np.ndarray | None = None,
                 tol: float = 1e-6) -> None:
        if n_layers < 1:
            raise ValueError("n_layers 必须 >= 1")
        if lambd < 0 or mu <= 0:
            raise ValueError("lambd 必须 >= 0，mu 必须 > 0")
        self.n_layers = int(n_layers)
        self.lambd = lambd
        self.mu = mu
        self.nesterov = bool(nesterov)
        self.tol = float(tol)
        if dictionary is None:
            self._dict = None  # 单位阵哨兵（省矩阵乘法）
        else:
            d = np.asarray(dictionary, dtype=float)
            if d.ndim != 2:
                raise ValueError("dictionary 必须为 2D 矩阵")
            self._dict = d

    @property
    def num_params(self) -> int:
        """可学习参数量：阈值 λ + 步长 μ（标量各 1；每层数组则按层数计）。"""
        n_l = 1 if np.ndim(self.lambd) == 0 else len(self.lambd)
        n_m = 1 if np.ndim(self.mu) == 0 else len(self.mu)
        return n_l + n_m

    def _at(self, value, k: int) -> float:
        """取第 k 层参数（标量或每层数组）。"""
        if np.ndim(value) == 0:
            return float(value)
        return float(value[k % len(value)])

    def decompose(self, x: np.ndarray, nesterov: bool | None = None) -> DecomposeResult:
        """深度展开迭代分解。

        参数:
            x:        1D 观测（频谱/信号）。
            nesterov: 覆盖构造时的动量开关（None 用构造值）。

        返回:
            DecomposeResult（signal 与 x 同长；identity 字典时 residual = x - signal）。
        """
        x = np.asarray(x, dtype=float).ravel()
        if x.size == 0:
            raise ValueError("x 不能为空")
        use_mom = self.nesterov if nesterov is None else bool(nesterov)
        d = self._dict
        # 系数维度：identity 与 x 同长；字典 D(N,M) 时为 M（x ≈ D·s）
        coeff_dim = x.size if d is None else d.shape[1]

        s = np.zeros(coeff_dim, dtype=float)
        s_prev = np.zeros(coeff_dim, dtype=float)
        t = 1.0
        converged = False
        iters = 0

        for k in range(self.n_layers):
            lam = self._at(self.lambd, k)
            mu = self._at(self.mu, k)
            y = s
            if use_mom:
                t_new = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * t * t))
                y = s + ((t - 1.0) / t_new) * (s - s_prev)
            grad = (x - y) if d is None else (d.T @ (x - d @ y))
            s_new = soft_threshold(y + mu * grad, lam)
            if use_mom:
                t = t_new
            change = float(np.max(np.abs(s_new - s))) if s_new.size else 0.0
            s_prev, s = s, s_new
            iters = k + 1
            if change < self.tol and k > 0:
                converged = True
                break

        residual = (x - s) if d is None else (x - d @ s)
        return DecomposeResult(signal=s, residual=residual, n_iters=iters, converged=converged)


# ---------------------------------------------------------------------------
# CFAR 基线（对比用）：固定阈值检测，恢复分量 = 检测点原始幅度
# ---------------------------------------------------------------------------
def cfar_detect(x: np.ndarray, *, k: float = 3.0,
                floor: float | None = None, sigma: float | None = None) -> tuple[np.ndarray, float]:
    """稳健 CFAR 检测：阈值 = 噪声底 + k·σ，返回 (二值掩码, 阈值)。

    - floor：噪声底估计（缺省 = median(x)，对恒定/缓变干扰底稳健）
    - sigma：噪声标准差估计（缺省 = 1.4826·MAD，即中位数绝对偏差的稳健 σ）
    只做「有无信号」判决，不降噪——这是与 IDSD 的估计器身份的关键区别。
    """
    x = np.asarray(x, dtype=float).ravel()
    med = float(np.median(x)) if floor is None else float(floor)
    if sigma is None:
        mad = float(np.median(np.abs(x - med)))
        sigma = 1.4826 * mad
    thr = med + k * sigma
    return (x > thr).astype(bool), thr


def cfar_component(x: np.ndarray, *, k: float = 3.0) -> np.ndarray:
    """CFAR 基线恢复分量：检测点保留原始幅度，其余置零（不做幅度估计/降噪）。"""
    x = np.asarray(x, dtype=float).ravel()
    mask, _ = cfar_detect(x, k=k)
    return x * mask


__all__ = [
    "soft_threshold",
    "recon_snr",
    "DecomposeResult",
    "DeepUnfoldDecomposer",
    "cfar_detect",
    "cfar_component",
]
