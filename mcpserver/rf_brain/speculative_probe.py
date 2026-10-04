"""射频大脑 · 推测探针式信号分类（R65）

授粉自 round3 digest-g1b Speculative Probing（2608.28099）：利用推测解码 pipeline
中已有的 KV-cache 做「零额外开销」的序列分类。跨领域映射：SDR 感知 pipeline 为
解调已算出频谱/特征，二次分类（调制/异常）不再单独跑分类模型，而是把「推测
探针」附加在感知末端，复用同一组中间特征——分类器只读既有频谱，不再算 FFT。

原型（纯 numpy，无新依赖）：
  - pipeline_spectrum  感知 pipeline 既有的频谱（FFT，代表已算好的中间特征）
  - ProbeClassifier    线性探针分类器：复用频谱，只做 M 维点积（零额外 FFT）
  - overhead_ratio     N 点 FFT（N·log₂N MAC）vs 探针（M MAC）的开销比

验收口径：合成信号分类准确率 ≥85%，额外开销 ≤5%。
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "pipeline_spectrum",
    "ProbeClassifier",
    "overhead_ratio",
    "fit_probe",
]


def pipeline_spectrum(iq: np.ndarray, n_fft: int | None = None) -> np.ndarray:
    """感知 pipeline 既有的频谱（正频功率谱）——代表「已算好的中间特征」。

    真实 pipeline 里这一步是解调/特征提取的必经步骤；探针分类器直接复用其结果，
    不再单独跑 FFT。
    """
    x = np.asarray(iq, dtype=float)
    n = len(x) if n_fft is None else int(n_fft)
    return np.abs(np.fft.rfft(x, n=n)) ** 2


class ProbeClassifier:
    """线性探针分类器：在既有频谱上做 M 维点积（Fisher 线性判别，确定性）。"""

    def __init__(self, probe_bins: int = 32) -> None:
        if probe_bins < 1:
            raise ValueError("probe_bins 必须 >= 1")
        self.probe_bins = int(probe_bins)
        self._mu: np.ndarray | None = None
        self._sd: np.ndarray | None = None
        self._w: np.ndarray | None = None
        self._b: float = 0.0

    def _features(self, spec: np.ndarray) -> np.ndarray:
        """频谱 → 探针特征（分块均值降采样到 probe_bins，无 FFT）。

        分块求和用 np.add.reduceat 向量化，除以块宽即块均值。
        """
        p = np.asarray(spec, dtype=float)
        n = p.size
        if self.probe_bins >= n:
            return p.copy()
        starts = np.linspace(0, n, self.probe_bins + 1).astype(int)
        return np.add.reduceat(p, starts[:-1]) / np.diff(starts)

    def fit(self, spectra: list[np.ndarray] | np.ndarray, labels: np.ndarray) -> "ProbeClassifier":
        X = np.stack([self._features(s) for s in spectra])
        y = np.asarray(labels, dtype=int)
        self._mu = X.mean(axis=0)
        self._sd = X.std(axis=0) + 1e-9
        Z = (X - self._mu) / self._sd
        m0, m1 = Z[y == 0].mean(axis=0), Z[y == 1].mean(axis=0)
        self._w = m1 - m0
        self._b = 0.5 * float(self._w @ m0 + self._w @ m1)
        return self

    def predict(self, spectrum: np.ndarray) -> int:
        z = (self._features(spectrum) - self._mu) / self._sd
        return int(z @ self._w > self._b)

    def accuracy(self, spectra: list[np.ndarray] | np.ndarray, labels: np.ndarray) -> float:
        pred = np.array([self.predict(s) for s in spectra])
        return float((pred == np.asarray(labels, dtype=int)).mean())


def overhead_ratio(n_fft: int, probe_bins: int) -> float:
    """探针额外开销比 = 探针点积 MAC / 既有 FFT MAC（越小越好）。"""
    fft_mac = n_fft * float(np.log2(n_fft))
    return float(probe_bins) / fft_mac


def fit_probe(spectra: list[np.ndarray], labels: np.ndarray, *, probe_bins: int = 32) -> ProbeClassifier:
    """训练探针分类器（复用既有频谱）。"""
    return ProbeClassifier(probe_bins=probe_bins).fit(spectra, labels)
