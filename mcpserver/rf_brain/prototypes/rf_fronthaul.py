"""计算型射频前传原型（R51 · 波域权重映射 → 可调滤波器组）

授粉自 digest-g8-3b-2026-08-30.md 授粉点 ①（来源 2608.27137v1 OTA XL-MIMO 极限
学习机，超表面「波域权重映射」思想）：把「全基带 FFT + 全谱分类」下沉到射频前端
的可调滤波器组——滤波器组直接在模拟/前端域算出一小组判别特征（波域权重），基带
只做极低维线性分类，实现极低功耗异常检测。

原型对比同一异常检测任务的两条路径：
  1. 全基带 FFT 分类（基线）：raw ADC → N 点 FFT → 全谱 N 维功率特征 → 线性分类
  2. 计算型前传（滤波器组）：raw → M 个可调带通滤波器（M≪N）→ M 维子带能量特征
     → 线性分类。滤波器组在模拟域完成投影，基带数字计算只剩 M 维点积。

诚实说明：原型用 FFT 内部模拟滤波器组输出（验证精度），计算量/功耗是解析估算——
模拟滤波器组功耗 ≈ M×µW 量级，FFT DSP ≈ mW 量级，故「计算量/功耗降 ≥3×」成立。

验收：分类精度损失 ≤10%（前传精度 ≥ 基线 −10pp），基带计算量降 ≥3×。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 归一化频段（相对 Nyquist）：正常信号占「允许带」，异常占「禁带/宽带」
ALLOWED_BAND = (0.05, 0.18)
FORBIDDEN_BAND = (0.30, 0.45)


# ---------------------------------------------------------------------------
# 合成信号
# ---------------------------------------------------------------------------
def _sine_burst(t: np.ndarray, freq: float, amp: float) -> np.ndarray:
    return amp * np.sin(2.0 * np.pi * freq * t)


def synthetic_signal(kind: str, n: int = 512, seed: int = 0, noise: float = 0.1) -> np.ndarray:
    """合成一帧「raw ADC」时间信号。

    kind:
      - normal:    允许带内 2~3 个正弦（合法载波）+ 噪声
      - forbidden: 禁带内 2~3 个正弦（未预期载波）+ 噪声
      - broadband: 全带宽带噪声（宽带干扰）
      - mixed:     允许带 + 禁带各一个正弦（合法 + 未预期叠加）
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)  # 样本序号：f 以「周/样本」计，FFT bin = f·n
    x = np.zeros(n, dtype=float)
    if kind == "normal":
        for _ in range(rng.integers(2, 4)):
            f = float(rng.uniform(*ALLOWED_BAND))
            x += _sine_burst(t, f, float(rng.uniform(0.5, 1.0)))
    elif kind == "forbidden":
        for _ in range(rng.integers(2, 4)):
            f = float(rng.uniform(*FORBIDDEN_BAND))
            x += _sine_burst(t, f, float(rng.uniform(0.5, 1.0)))
    elif kind == "broadband":
        # 宽带干扰：局限在禁带内的一组密集正弦（禁带内能量散布 = 宽带干扰）
        for f in np.linspace(*FORBIDDEN_BAND, 7):
            x += _sine_burst(t, float(f), float(rng.uniform(0.3, 0.6)))
    elif kind == "single":
        # 单一未预期载波（禁带内单音）
        x += _sine_burst(t, float(rng.uniform(*FORBIDDEN_BAND)), float(rng.uniform(0.6, 1.0)))
    else:
        raise ValueError(f"未知信号类型 {kind!r}")
    x += noise * rng.standard_normal(n)
    return x


def make_dataset(n_per_class: int = 200, n: int = 512, seed: int = 0,
                 noise: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """构造二分类数据集：label=0 正常（normal），label=1 异常（forbidden/broadband/mixed）。"""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for i in range(n_per_class):
        xs.append(synthetic_signal("normal", n, seed=int(rng.integers(1 << 30)), noise=noise))
        ys.append(0)
        kind = ("forbidden", "broadband", "single")[i % 3]
        xs.append(synthetic_signal(kind, n, seed=int(rng.integers(1 << 30)), noise=noise))
        ys.append(1)
    return np.stack(xs), np.asarray(ys, dtype=int)


# ---------------------------------------------------------------------------
# 特征提取：全基带 FFT vs 可调滤波器组
# ---------------------------------------------------------------------------
def fft_features(x: np.ndarray, n_fft: int | None = None) -> np.ndarray:
    """全基带路径特征：N 点 FFT → 正频功率谱（N//2+1 维）。"""
    n_fft = len(x) if n_fft is None else int(n_fft)
    X = np.fft.rfft(x, n=n_fft)
    return np.abs(X) ** 2


def filter_bank_features(x: np.ndarray, m_bands: int = 32) -> np.ndarray:
    """前传路径特征：M 个可调带通滤波器组 = 正频谱均分 M 段，每段能量（M 维）。

    模拟域滤波器组输出（原型用 FFT 内部模拟），基带只取 M 个标量。
    分带求和用 np.add.reduceat 向量化（要求 m_bands ≤ 谱 bin 数，实践中恒成立）。
    """
    power = fft_features(x)
    starts = np.linspace(0, power.size, m_bands + 1).astype(int)
    return np.add.reduceat(power, starts[:-1])


# ---------------------------------------------------------------------------
# 线性分类器（Fisher LDA + 标准化，纯 numpy 确定性）
# ---------------------------------------------------------------------------
class LinearClassifier:
    """2 类 Fisher 线性判别：标准化 → w = μ1 − μ0 → 投影阈值。"""

    def __init__(self) -> None:
        self._mu: np.ndarray | None = None
        self._sd: np.ndarray | None = None
        self._w: np.ndarray | None = None
        self._b: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LinearClassifier":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        self._mu = X.mean(axis=0)
        self._sd = X.std(axis=0) + 1e-9
        Z = (X - self._mu) / self._sd
        m0, m1 = Z[y == 0].mean(axis=0), Z[y == 1].mean(axis=0)
        self._w = m1 - m0
        self._b = 0.5 * float(self._w @ m0 + self._w @ m1)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - self._mu) / self._sd
        return (Z @ self._w > self._b).astype(int)

    def accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        return float((self.predict(X) == y).mean())


# ---------------------------------------------------------------------------
# 计算量 / 功耗估算
# ---------------------------------------------------------------------------
def digital_macs_baseline(n_fft: int) -> float:
    """全基带路径基带数字 MAC：FFT（N·log2N）+ 全谱分类点积（N/2+1）。"""
    n_bins = n_fft // 2 + 1
    return n_fft * float(np.log2(n_fft)) + n_bins


def digital_macs_fronthaul(m_bands: int) -> float:
    """前传路径基带数字 MAC：滤波器组在模拟域完成，基带仅 M 维分类点积。"""
    return float(m_bands)


def compute_reduction(n_fft: int, m_bands: int) -> float:
    """基带计算量降幅 = 全基带 MAC / 前传 MAC（≥3× 验收）。"""
    return digital_macs_baseline(n_fft) / digital_macs_fronthaul(m_bands)


# ---------------------------------------------------------------------------
# 对比实验
# ---------------------------------------------------------------------------
@dataclass
class FronthaulResult:
    """前传 vs 全基带对比结果。"""
    acc_baseline: float      # 全基带 FFT 分类精度
    acc_fronthaul: float     # 滤波器组分类精度
    acc_loss: float          # 精度损失（percentage points）
    reduction: float         # 基带计算量降幅
    n_fft: int
    m_bands: int


def run_comparison(n_per_class: int = 200, n: int = 512, m_bands: int = 32,
                   seed: int = 0, noise: float = 0.1) -> FronthaulResult:
    """跑一次前传 vs 全基带对比：同数据集、同线性分类器，只换特征域。"""
    X, y = make_dataset(n_per_class, n, seed=seed, noise=noise)
    split = int(len(X) * 0.5)
    tr = slice(0, split)
    te = slice(split, None)

    # 全基带 FFT
    Xf_fft = np.stack([fft_features(x, n) for x in X])
    clf_fft = LinearClassifier().fit(Xf_fft[tr], y[tr])
    acc_base = clf_fft.accuracy(Xf_fft[te], y[te])

    # 计算型前传（滤波器组）
    Xf_fb = np.stack([filter_bank_features(x, m_bands) for x in X])
    clf_fb = LinearClassifier().fit(Xf_fb[tr], y[tr])
    acc_fb = clf_fb.accuracy(Xf_fb[te], y[te])

    return FronthaulResult(
        acc_baseline=acc_base,
        acc_fronthaul=acc_fb,
        acc_loss=acc_base - acc_fb,
        reduction=compute_reduction(n, m_bands),
        n_fft=n,
        m_bands=m_bands,
    )


__all__ = [
    "ALLOWED_BAND",
    "FORBIDDEN_BAND",
    "synthetic_signal",
    "make_dataset",
    "fft_features",
    "filter_bank_features",
    "LinearClassifier",
    "digital_macs_baseline",
    "digital_macs_fronthaul",
    "compute_reduction",
    "run_comparison",
    "FronthaulResult",
]
