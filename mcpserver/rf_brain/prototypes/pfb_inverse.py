"""R13 · PFB 逆重建原型（多相滤波器组信道化 + 逆重建）

灵感：digest-g6-2a 授粉点 A · 论文 2608.23441v1（PFB 循环逆 + 维纳/最大似然重建，
将量化噪声放大溯源后把误差压到 <2% 通道宽）。

本原型实现标准多相滤波器组（WOLA 形式）：
  - pfb_analyze   分析：重叠加窗 → 折叠成 K 个多相分支 → FFT → K 子带
  - pfb_synthesize 逆：IFFT → 周期展开 → 加合成窗 → 重叠相加 → 全带重建

完美重建条件：分析窗 w_a 与合成窗 w_s 满足 COLA（Σ_p w_a[n+pK]·w_s[n+pK]=1）。
原型滤波器用窗化 sinc 低通（截止 1/(2K)），配合合适的合成窗缩放逼近完美重建，
以重建 SNR 度量误差（等价于「通道宽内误差」口径）。

运行：python -m mcpserver.rf_brain.prototypes.pfb_inverse
"""
from __future__ import annotations

import numpy as np


def prototype_filter(K: int, P: int, *, window: str = "hann") -> np.ndarray:
    """窗化 sinc 低通原型滤波器，长度 K*P，截止 1/(2K)（归一化频率）。"""
    L = K * P
    n = np.arange(L)
    center = (L - 1) / 2.0
    h = np.sinc((n - center) / K)  # 截止 1/(2K) 的低通
    if window == "hann":
        w = np.hanning(L)
    elif window == "hamming":
        w = np.hamming(L)
    else:
        w = np.ones(L)
    h = h * w
    # 归一化到 Nyquist 条件：每个多相分支能量 = 1（Σ_p h[pK+k]² = 1，∀k）。
    # 分析与合成共用同一窗（各乘一次），故 COLA 条件即 Σ_p h²[pK+k] = 1。
    for k in range(K):
        e = float(np.sum(h[k::K] ** 2))
        if e > 1e-12:
            h[k::K] /= np.sqrt(e)
    return h


def pfb_analyze(x: np.ndarray, h: np.ndarray, K: int, P: int) -> np.ndarray:
    """分析滤波器组：x → (K, n_blocks) 复子带。"""
    L = K * P
    x = np.asarray(x, dtype=float)
    n_blocks = len(x) // K
    out = np.zeros((K, n_blocks), dtype=complex)
    for b in range(n_blocks):
        seg = x[b * K:b * K + L]
        if seg.size < L:
            seg = np.pad(seg, (0, L - seg.size))
        seg = seg * h
        folded = seg.reshape(P, K).sum(axis=0)
        out[:, b] = np.fft.fft(folded)
    return out


def pfb_synthesize(sub: np.ndarray, h: np.ndarray, K: int, P: int) -> np.ndarray:
    """逆滤波器组：子带 → 全带重建信号。"""
    L = K * P
    n_blocks = sub.shape[1]
    out = np.zeros(n_blocks * K + L, dtype=float)
    for b in range(n_blocks):
        folded = np.fft.ifft(sub[:, b]).real
        seg = np.tile(folded, P)          # 周期展开 K → K*P
        seg = seg * h                     # 合成窗
        out[b * K:b * K + L] += seg       # 重叠相加
    return out[:n_blocks * K]


def reconstruction_snr_db(x: np.ndarray, x_hat: np.ndarray, *, skip: int = 0) -> float:
    """重建 SNR：20·log10(‖x‖/‖x-x̂‖)。

    skip: 跳过前 skip 个样本（PFB 合成前 K*P 个样本是暂态，边界帧不完整），
    度量稳态重建 SNR——与论文「通道宽内误差」同口径。
    """
    m = min(x.size, x_hat.size)
    a = max(0, min(skip, m))
    err = x[a:m] - x_hat[a:m]
    denom = np.linalg.norm(err)
    return float(20 * np.log10(np.linalg.norm(x[a:m]) / denom)) if denom > 0 else float("inf")


def main() -> None:
    K, P = 8, 16
    h = prototype_filter(K, P)
    rng = np.random.default_rng(0)
    x = rng.standard_normal(8192)
    sub = pfb_analyze(x, h, K, P)
    x_hat = pfb_synthesize(sub, h, K, P)
    # 暂态样本 = 原型滤波器长度 K*P
    print(f"K={K} P={P}  总体 SNR = {reconstruction_snr_db(x, x_hat):.1f} dB  "
          f"稳态 SNR = {reconstruction_snr_db(x, x_hat, skip=K*P):.1f} dB")
    # 冲激校验：δ → δ（验证结构正确）
    d = np.zeros(8192); d[4096] = 1.0
    d_hat = pfb_synthesize(pfb_analyze(d, h, K, P), h, K, P)
    print(f"冲激重建峰值 = {np.max(np.abs(d_hat)):.6f}（应≈1，位于 4096 处）")


if __name__ == "__main__":
    main()
