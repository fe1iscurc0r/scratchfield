"""计算型射频前传 · Koopman 特征映射原型（digest-g8-3b 波域权重授粉）。

授粉源：digest-g8-3b-2026-08-30.md「超表面波域权重 → 可调滤波器组替代基带计算」。
本原型为「计算型射频前传」的 Koopman 分支（R51 为滤波器组分支持，共享设计文档
docs/koopman-rf-frontend-方案.md）：

  原始 ADC 数据 ──轻量 Koopman 非线性提升（可观测量）──> 前端线性分类
  （异常检测 / 调制识别），用「时域非线性提升 + 线性分类」替代「全基带 FFT +
  分类」，在精度不显著损失下大幅降低计算量/功耗。

验收（见 test_koopman_rf_frontend.py）：
  - 分类精度 ≥ 全基带精度的 90%；
  - 计算量（每帧乘法次数）较全基带 FFT 降 ≥ 3×。

纯 numpy 实现，无 LLM/网络调用。
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9

# --------------------------------------------------------------------------- #
# 合成 ADC 信号（调制识别 + 噪声异常）
# --------------------------------------------------------------------------- #
def _add_noise(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    sig_p = np.mean(x ** 2)
    noise_p = sig_p / (10 ** (snr_db / 10.0)) if snr_db < 90 else 0.0
    return x + rng.normal(0.0, np.sqrt(noise_p), size=x.shape)


def gen_ook(n: int, fs: float, f0: float, snr_db: float,
            rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / fs
    bits = rng.integers(0, 2, size=max(1, n // 64))
    env = np.repeat(bits, 64)[:n]
    return _add_noise(env * np.sin(2 * np.pi * f0 * t), snr_db, rng)


def gen_fsk(n: int, fs: float, f0: float, f1: float, snr_db: float,
            rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / fs
    bits = rng.integers(0, 2, size=max(1, n // 64))
    freqs = np.where(np.repeat(bits, 64)[:n] == 0, f0, f1)
    phase = 2 * np.pi * np.cumsum(freqs) / fs
    return _add_noise(np.sin(phase), snr_db, rng)


def gen_cw(n: int, fs: float, f0: float, snr_db: float,
           rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / fs
    return _add_noise(np.sin(2 * np.pi * f0 * t), snr_db, rng)


def gen_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.normal(0.0, 1.0, size=n)


# --------------------------------------------------------------------------- #
# 特征：全基带 FFT（基线） vs Koopman 前端
# --------------------------------------------------------------------------- #
def fft_features(x: np.ndarray, n_bins: int = 64) -> np.ndarray:
    """全基带：N 点 FFT → 幅度谱前 n_bins 个 bin，L2 归一化。"""
    spec = np.abs(np.fft.rfft(x))
    bins = spec[:n_bins]
    return bins / (np.linalg.norm(bins) + EPS)


def koopman_features(x: np.ndarray, decim: int = 4) -> np.ndarray:
    """Koopman 前端：抽取 + 非线性可观测量提升 + 统计聚合（12 维）。

    可观测量（时域非线性提升，不做显式 FFT）：
      x、x²、|x|、x·x[-1]（滞后 1 相关）、x[-1]（延迟）、(x-x[-1])²（差分能量）。
    每个可观测量取 mean/std → 特征向量。抽取 decim 降低采样点 → 降计算量。
    """
    xd = x[::decim].astype(float)
    x1 = np.roll(xd, 1)
    x1[0] = xd[0]
    obs = {
        "x": xd,
        "x2": xd ** 2,
        "absx": np.abs(xd),
        "xx1": xd * x1,
        "x1": x1,
        "d2": (xd - x1) ** 2,
    }
    feats = []
    for o in obs.values():
        feats.append(float(np.mean(o)))
        feats.append(float(np.std(o)))
    return np.asarray(feats, dtype=float)


# --------------------------------------------------------------------------- #
# 前端线性分类器（softmax 多分类，numpy 手写，无外部依赖）
# --------------------------------------------------------------------------- #
class LinearClassifier:
    def __init__(self, n_features: int, n_classes: int, lr: float = 0.1,
                 iters: int = 400, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0.0, 0.01, size=(n_classes, n_features))
        self.b = np.zeros(n_classes)
        self.lr = lr
        self.iters = iters

    def _softmax(self, z: np.ndarray) -> np.ndarray:
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / (e.sum(axis=1, keepdims=True) + EPS)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LinearClassifier":
        n = X.shape[0]
        y_onehot = np.zeros((n, self.W.shape[0]))
        y_onehot[np.arange(n), y] = 1.0
        for _ in range(self.iters):
            logits = X @ self.W.T + self.b
            probs = self._softmax(logits)
            grad = (probs - y_onehot) / n
            self.W -= self.lr * (grad.T @ X)
            self.b -= self.lr * grad.sum(axis=0)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(X @ self.W.T + self.b, axis=1)

    def accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        return float(np.mean(self.predict(X) == y))


# --------------------------------------------------------------------------- #
# 计算量 / 功耗估算
# --------------------------------------------------------------------------- #
def macs_full_baseband(n: int) -> float:
    """全基带：N 点 FFT 的实乘次数 ≈ 2N·log2(N)（radix-2 蝶形）。"""
    return 2.0 * n * np.log2(n)


def macs_koopman(n: int, decim: int = 4, n_obs: int = 6) -> float:
    """Koopman 前端：n_obs 个可观测量 × 抽取后采样点数的乘法次数。

    可观测量 x²、x·x[-1]、(x-x[-1])² 各 1 次乘法/样本；|x|/延迟/线性≈0 次乘法。
    保守按 n_obs 个可观测量各 1 次乘法估算。
    """
    return float(n_obs * (n // decim))


# --------------------------------------------------------------------------- #
# 演示入口
# --------------------------------------------------------------------------- #
def run_demo() -> None:
    rng = np.random.default_rng(7)
    fs, f0, f1, snr, n = 100_000.0, 5_000.0, 15_000.0, 15.0, 1024
    per = 300
    Xf, Xk, y = [], [], []
    gens = [
        lambda: gen_ook(n, fs, f0, snr, rng),
        lambda: gen_fsk(n, fs, f0, f1, snr, rng),
        lambda: gen_cw(n, fs, f0, snr, rng),
        lambda: gen_noise(n, rng),
    ]
    for c, g in enumerate(gens):
        for _ in range(per):
            s = g()
            Xf.append(fft_features(s))
            Xk.append(koopman_features(s))
            y.append(c)
    Xf, Xk = np.array(Xf), np.array(Xk)
    y = np.array(y)

    idx = np.arange(len(y))
    rng.shuffle(idx)
    split = int(len(idx) * 0.7)
    tr, te = idx[:split], idx[split:]

    clf_f = LinearClassifier(Xf.shape[1], 4, seed=0).fit(Xf[tr], y[tr])
    clf_k = LinearClassifier(Xk.shape[1], 4, seed=0).fit(Xk[tr], y[tr])
    acc_f = clf_f.accuracy(Xf[te], y[te])
    acc_k = clf_k.accuracy(Xk[te], y[te])

    m_full = macs_full_baseband(n)
    m_koop = macs_koopman(n)
    print(f"[K16] 全基带 FFT 分类精度 = {acc_f:.3f}")
    print(f"[K16] Koopman 前端分类精度 = {acc_k:.3f}（较全基带 {acc_k / max(acc_f, EPS):.2f}）")
    print(f"[K16] 计算量（每帧乘法）全基带 = {m_full:.0f} ｜ Koopman = {m_koop:.0f}"
          f"（降 {m_full / max(m_koop, EPS):.1f}×）")


if __name__ == "__main__":
    run_demo()
