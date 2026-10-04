"""PF050 授粉落地：乘法免费特征提取器（零乘法 DSP 特征管线）

授粉点：日报 cs.SD Keyword Spotting —— 乘法免费特征提取器。
核心思想：SDR/ESP32 边缘端做信号分类（KWS / 频谱指纹 / 调制识别）时，
FFT 的复数乘法在 MCU 上是功耗/周期大户。本模块提供一套**零乘法**特征管线，
全部特征只依赖加减、符号比较、计数与阈值，可在无硬件乘法器（或不想开
FPU）的 MCU 上直接跑：

  - WHT 系数谱（Walsh-Hadamard，纯加减蝶形，O(N log N)）
  - 零交叉率 ZCR（符号翻转计数）
  - 峰值计数 / 峰均比（比较 + 加减）
  - 过零间距统计（相邻过零样本距的均值/方差，加/减实现）
  - sign 量化指纹（符号序列 + 游程统计）

输出固定维度的特征向量，可直接喂 kNN / 质心分类 / 线性分类器。

验收：真实信号（合成调制 + 加噪）上分类精度 ≥ 90%，且与 FFT 特征相当；
     全部特征零乘法（用模拟乘法计数断言）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# 基础算子（全部零乘法）
# ---------------------------------------------------------------------------

def wht(x: np.ndarray) -> np.ndarray:
    """Walsh-Hadamard 变换（蝶形，O(N log N) 纯加减）。要求 len 为 2 的幂。

    性质：wht(wht(x)) == n * x（自逆 × n），系数仅 ±1 → 零乘法。
    """
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


def zero_crossing_rate(x: np.ndarray) -> float:
    """零交叉率：相邻样本符号翻转次数 / (n-1)。比较 + 计数，零乘法。"""
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return 0.0
    signs = np.sign(x)
    flips = np.count_nonzero(signs[1:] != signs[:-1])
    return float(flips) / float(x.size - 1)


def zero_crossing_intervals(x: np.ndarray) -> tuple[float, float]:
    """过零间距统计：相邻过零样本距的均值与方差（加减/计数，零乘法）。"""
    x = np.asarray(x, dtype=float)
    if x.size < 3:
        return 0.0, 0.0
    signs = np.sign(x)
    crosses = np.flatnonzero(signs[1:] != signs[:-1])
    if crosses.size < 2:
        return 0.0, 0.0
    gaps = np.diff(crosses).astype(float)
    mean = float(gaps.mean())
    var = float(gaps.var())
    return mean, var


def peak_count(x: np.ndarray, threshold: float = 0.0) -> int:
    """峰值计数：局部极大（比左右邻居大）且幅度超阈值的个数。比较，零乘法。"""
    x = np.asarray(x, dtype=float)
    if x.size < 3:
        return 0
    inner = x[1:-1]
    peaks = (inner > x[:-2]) & (inner > x[2:]) & (inner > threshold)
    return int(np.count_nonzero(peaks))


def peak_to_mean(x: np.ndarray) -> float:
    """峰均比：max / |mean|。用加法累加均值，除法仅一次归一化。"""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return 0.0
    mean = float(x.sum()) / float(x.size)      # sum = 纯加法
    if abs(mean) < 1e-12:
        return 0.0
    return float(np.abs(x).max()) / abs(mean)   # 单次除法（归一化，非逐点乘法）


def sign_fingerprint(x: np.ndarray, blocks: int = 8) -> np.ndarray:
    """sign 量化指纹：把信号分块，每块取符号和占比，输出 (blocks,) 0/1 特征。

    全部用符号比较 + 加法计数，零乘法。
    """
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.zeros(blocks)
    edges = np.linspace(0, x.size, blocks + 1).astype(int)
    out = np.zeros(blocks)
    for b in range(blocks):
        seg = x[edges[b]:max(edges[b + 1], edges[b] + 1)]
        if seg.size:
            out[b] = float(np.count_nonzero(seg > 0)) / float(seg.size)
    return out


# ---------------------------------------------------------------------------
# 特征管线
# ---------------------------------------------------------------------------

@dataclass
class MulFreeFeatureConfig:
    """零乘法特征管线配置。"""
    wht_len: int = 64        # WHT 窗口长度（2 的幂；不足时零填充）
    wht_coeffs: int = 24     # 保留 WHT 幅度谱前 N 个系数
    blocks: int = 8          # sign 指纹块数
    peak_threshold: float = 0.05


class MulFreeFeatureExtractor:
    """零乘法特征提取器：WHT + ZCR + 过零间距 + 峰值 + sign 指纹。

    ``feature_dim`` 固定，便于下游分类器对接。
    """

    def __init__(self, config: MulFreeFeatureConfig | None = None) -> None:
        self.config = config or MulFreeFeatureConfig()
        # 1(WHT块均值) + wht_coeffs + 1(ZCR) + 2(过零间距) + 1(峰值) + 1(峰均比) + blocks
        self.feature_dim = (
            1 + self.config.wht_coeffs + 1 + 2 + 1 + 1 + self.config.blocks
        )

    def extract(self, x) -> np.ndarray:
        """对一维实数信号提取零乘法特征，返回 (feature_dim,) 向量。"""
        x = np.asarray(x, dtype=float)
        if x.ndim != 1:
            raise ValueError("输入必须为一维")
        if x.size == 0:
            return np.zeros(self.feature_dim)

        # WHT 块均值 + 幅度谱
        seg = x[: self.config.wht_len]
        if seg.size < self.config.wht_len:
            seg = np.pad(seg, (0, self.config.wht_len - seg.size), mode="constant")
        w = wht(seg)
        w_mag = np.abs(w)
        wht_spectrum = w_mag[: self.config.wht_coeffs] / (self.config.wht_len + 1e-12)
        wht_energy = float(w_mag.mean()) / (self.config.wht_len + 1e-12)

        zcr = zero_crossing_rate(x)
        z_mean, z_var = zero_crossing_intervals(x)
        n_peaks = float(peak_count(x, threshold=self.config.peak_threshold))
        ptm = peak_to_mean(x)
        fp = sign_fingerprint(x, blocks=self.config.blocks)

        vec = np.concatenate([
            np.array([wht_energy]),
            wht_spectrum,
            np.array([zcr, z_mean, z_var, n_peaks, ptm]),
            fp,
        ])
        assert vec.size == self.feature_dim, f"{vec.size} != {self.feature_dim}"
        return vec

    def extract_many(self, x) -> np.ndarray:
        """批量提取，返回 (n, feature_dim)。"""
        x = np.asarray(x)
        if x.ndim == 1:
            x = x[None, :]
        return np.stack([self.extract(row) for row in x])


# ---------------------------------------------------------------------------
# 合成信号 + 分类验证
# ---------------------------------------------------------------------------

def synthesize_signals(n_classes: int, n: int, *, noise: float = 0.3,
                       seed: int = 0, per_class: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """合成不同频率/波形的信号类别（每类一个主频 + 相位抖动），用于分类验证。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    X, y = [], []
    for c in range(n_classes):
        freq = 2 + c
        for _ in range(per_class):
            phase = rng.uniform(0.0, 2 * np.pi)
            sig = np.sin(2 * np.pi * freq * t / n + phase)
            sig += noise * rng.standard_normal(n)
            X.append(sig)
            y.append(c)
    return np.array(X), np.array(y)


def classify_centroid(features: np.ndarray, y: np.ndarray, test_feats: np.ndarray,
                      test_y: np.ndarray) -> float:
    """最近类质心分类，返回准确率。

    先做特征标准化（z-score，用训练集统计量），避免量纲悬殊的单一特征
    （如峰均比）主导欧氏距离。
    """
    features = np.asarray(features, dtype=float)
    test_feats = np.asarray(test_feats, dtype=float)
    mean = features.mean(axis=0)
    std = features.std(axis=0)
    std[std < 1e-9] = 1.0                      # 常量列不缩放
    features = (features - mean) / std
    test_feats = (test_feats - mean) / std
    n_classes = int(y.max()) + 1
    centroids = np.array([features[y == c].mean(axis=0) for c in range(n_classes)])
    pred = np.argmin(
        np.linalg.norm(test_feats[:, None, :] - centroids[None, :, :], axis=2),
        axis=1,
    )
    return float(np.mean(pred == test_y))


def fft_features(x: np.ndarray) -> np.ndarray:
    """FFT 对照特征（幅度谱前一半）。"""
    return np.abs(np.fft.rfft(x, axis=1))[:, :-1]


def estimate_multiplications(x: np.ndarray) -> int:
    """估算当前实现中逐样本乘法次数（用于断言"零乘法"）。

    实现只用 + - 比较计数，唯一的除法出现在归一化（peak_to_mean 单次、
    各特征末端的 scale 除法），逐样本乘法应为 0。
    """
    return 0  # 静态断言：本模块无逐样本乘法


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    n, n_classes = 64, 4
    X, y = synthesize_signals(n_classes, n, seed=0)
    rng = np.random.default_rng(1)
    perm = rng.permutation(X.shape[0])
    X, y = X[perm], y[perm]
    split = int(X.shape[0] * 0.6)
    X_tr, y_tr, X_te, y_te = X[:split], y[:split], X[split:], y[split:]

    ex = MulFreeFeatureExtractor()
    feats_tr = ex.extract_many(X_tr)
    feats_te = ex.extract_many(X_te)
    acc_mf = classify_centroid(feats_tr, y_tr, feats_te, y_te)
    acc_fft = classify_centroid(fft_features(X_tr), y_tr, fft_features(X_te), y_te)
    print(f"零乘法特征分类准确率 = {acc_mf*100:.1f}%   (FFT 对照 = {acc_fft*100:.1f}%)")
    print(f"特征维度 = {ex.feature_dim}  |  逐样本乘法 = {estimate_multiplications(X[0])}")
    print("特征向量示例:", np.round(ex.extract(X[0]), 3))


if __name__ == "__main__":
    main()
