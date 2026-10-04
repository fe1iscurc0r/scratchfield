"""M28 MM-Spectrum 多模态光谱→分子结构推断（特征拼接基线原型）。

授粉源：digest-g1-4-2026-08-30.md 2608.27286（MM-Spectrum: Multimodal
Multi-spectral Molecular Structure inference）。
思想：红外(IR)+质谱(MS)+NMR 三模态联合推断未知分子结构——单模态各自携带
互补的结构线索（IR 给官能团、MS 给分子量、NMR 给连接性），融合后结构推断
准确率显著高于任一单模态。

本原型为「特征拼接基线」：三模态谱各自离散成 bin 强度向量 → 拼接 → 线性
softmax 分类。合成数据（无真实谱，显式 mock）：每类分子用一个 3-bit 结构编码
（IR 编码 bit0、MS 编码 bit1、NMR 编码 bit2），单模态只能解出 1 bit（≤50% 上限），
三模态拼接才能解出全部 3 bit（8 类全分离）。

验收：合成光谱数据集结构推断准确率 ≥70%（见 test_mm_spectrum_fusion.py）。
纯 numpy，无外部依赖，无 LLM/网络调用。
"""
from __future__ import annotations

import numpy as np

N_CLASSES = 8
N_BINS = 24  # 每模态 bin 数
CLASS_NAMES = ["醇", "酮", "羧酸", "酯", "芳香族", "胺", "烷烃", "醚"]


def _one_modality(bit: int, lo_bin: int, hi_bin: int, n_bins: int,
                  rng: np.random.Generator, noise: float = 0.08) -> np.ndarray:
    """单模态谱：bit 决定强峰落在 lo_bin 还是 hi_bin，其余为底噪。

    合成 surrogate（mock）：真实 IR 波数/MS m/z/NMR ppm 峰位会替换此处的 bin。
    """
    v = rng.normal(0.0, noise, size=n_bins)
    peak_bin = lo_bin if bit == 0 else hi_bin
    v[peak_bin] = 1.0 + rng.normal(0.0, 0.1)
    return v


def make_dataset(n_per_class: int = 80, seed: int = 0):
    """生成合成三模态谱 + 结构类标签。

    返回 X_ir/X_ms/X_nmr (n, N_BINS) 与 y (n,)。类 c 的 3-bit 编码：
      x = c>>2 & 1（IR 编码） y = c>>1 & 1（MS 编码） z = c & 1（NMR 编码）。
    """
    rng = np.random.default_rng(seed)
    X_ir, X_ms, X_nmr, y = [], [], [], []
    for c in range(N_CLASSES):
        x, yy, z = (c >> 2) & 1, (c >> 1) & 1, c & 1
        for _ in range(n_per_class):
            X_ir.append(_one_modality(x, 4, 5, N_BINS, rng))
            X_ms.append(_one_modality(yy, 8, 9, N_BINS, rng))
            X_nmr.append(_one_modality(z, 12, 13, N_BINS, rng))
            y.append(c)
    return (np.asarray(X_ir), np.asarray(X_ms), np.asarray(X_nmr), np.asarray(y))


def concat_features(X_ir, X_ms, X_nmr) -> np.ndarray:
    """三模态特征拼接 → (n, 3*N_BINS)。"""
    return np.concatenate([X_ir, X_ms, X_nmr], axis=1)


class SoftmaxClassifier:
    """线性 softmax 多分类（numpy 手写，无外部依赖）。"""

    def __init__(self, n_features: int, n_classes: int, lr: float = 0.3,
                 iters: int = 500, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0.0, 0.01, size=(n_classes, n_features))
        self.b = np.zeros(n_classes)
        self.lr = lr
        self.iters = iters

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SoftmaxClassifier":
        n = X.shape[0]
        onehot = np.zeros((n, self.W.shape[0]))
        onehot[np.arange(n), y] = 1.0
        for _ in range(self.iters):
            logits = X @ self.W.T + self.b
            z = logits - logits.max(axis=1, keepdims=True)
            probs = np.exp(z) / (np.exp(z).sum(axis=1, keepdims=True) + 1e-9)
            grad = (probs - onehot) / n
            self.W -= self.lr * (grad.T @ X)
            self.b -= self.lr * grad.sum(axis=0)
        return self

    def accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        return float(np.mean(np.argmax(X @ self.W.T + self.b, axis=1) == y))


def run_demo() -> None:
    X_ir, X_ms, X_nmr, y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    X_fused = concat_features(X_ir, X_ms, X_nmr)
    accs = {}
    for name, X in [("IR", X_ir), ("MS", X_ms), ("NMR", X_nmr), ("融合", X_fused)]:
        clf = SoftmaxClassifier(X.shape[1], N_CLASSES, seed=0).fit(X[tr], y[tr])
        accs[name] = clf.accuracy(X[te], y[te])

    print("[M28] 单模态准确率:", {k: round(v, 3) for k, v in accs.items() if k != "融合"})
    print(f"[M28] 三模态融合准确率 = {accs['融合']:.3f}（验收 ≥0.70）")


if __name__ == "__main__":
    run_demo()
