"""R39 · 乘法免费特征提取原型（Walsh-Hadamard 变换）

灵感：digest-g8-1a 授粉点② · 论文 2608.19048（WHT 尖峰排序，仅加法器/减法器）。

Walsh-Hadamard 变换（WHT）只用 ±1 系数，即**纯加减、零乘法**，可作 SDR 收包分类的
无乘法特征提取器（FFT/滤波器的轻量近似）。本原型对比 WHT 特征与 FFT 特征在信号
分类上的精度，并估算 MCU 周期（WHT 无乘法、FFT 有复数乘法）。

运行：python -m mcpserver.rf_brain.prototypes.mul_free_features
"""
from __future__ import annotations

import numpy as np


def wht(x: np.ndarray) -> np.ndarray:
    """Walsh-Hadamard 变换（蝶形，O(N log N) 纯加减）。要求 len 为 2 的幂。"""
    x = np.asarray(x, dtype=float).copy()
    n = x.size
    if n & (n - 1) != 0:
        raise ValueError("长度须为 2 的幂")
    h = 1
    while h < n:
        for i in range(0, n, 2 * h):
            for j in range(i, i + h):
                a, b = x[j], x[j + h]
                x[j] = a + b
                x[j + h] = a - b
        h *= 2
    return x


def synthesize_signals(n_classes: int, n: int, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """合成不同频率的信号类别（每类一个主频）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    X, y = [], []
    for c in range(n_classes):
        freq = 2 + c          # 每类不同频率
        for _ in range(30):
            sig = np.sin(2 * np.pi * freq * t / n) + 0.3 * rng.standard_normal(n)
            X.append(sig)
            y.append(c)
    return np.array(X), np.array(y)


def wht_features(X: np.ndarray) -> np.ndarray:
    """WHT 特征（幅度谱，前一半系数）。"""
    return np.abs(np.array([wht(x) for x in X]))[:, :X.shape[1] // 2]


def fft_features(X: np.ndarray) -> np.ndarray:
    """FFT 特征（幅度谱，前一半系数）。"""
    return np.abs(np.fft.rfft(X, axis=1))[:, :-1]


def classify(features: np.ndarray, y: np.ndarray, test_feats: np.ndarray,
             test_y: np.ndarray) -> float:
    """最近类质心分类，返回准确率。"""
    n_classes = int(y.max()) + 1
    centroids = np.array([features[y == c].mean(axis=0) for c in range(n_classes)])
    pred = np.argmin(np.linalg.norm(test_feats[:, None, :] - centroids[None, :, :], axis=2), axis=1)
    return float(np.mean(pred == test_y))


def cycle_estimate(n: int) -> dict:
    """MCU 周期估算：WHT 纯加减 vs FFT 复数乘法。"""
    return {
        "wht_adds": n * int(np.log2(n)),          # 每蝶一层 n 次加减
        "fft_mults": 2 * n * int(np.log2(n)),     # 复数乘 ≈ 4 实数乘（保守×2）
        "wht_multiplies": 0,
    }


def main() -> None:
    n = 64
    X, y = synthesize_signals(3, n, seed=0)
    rng = np.random.default_rng(1)
    perm = rng.permutation(X.shape[0])
    X, y = X[perm], y[perm]
    X_tr, y_tr, X_te, y_te = X[:60], y[:60], X[60:], y[60:]
    acc_wht = classify(wht_features(X_tr), y_tr, wht_features(X_te), y_te)
    acc_fft = classify(fft_features(X_tr), y_tr, fft_features(X_te), y_te)
    c = cycle_estimate(n)
    print(f"WHT 特征分类准确率 = {acc_wht*100:.1f}%    FFT 特征 = {acc_fft*100:.1f}%")
    print(f"MCU 周期：WHT {c['wht_adds']} 次加减（0 乘法）vs FFT ~{c['fft_mults']} 次乘法")


if __name__ == "__main__":
    main()
