"""W59-03 · MM-Spectrum 多模态光谱→结构推断原型（生物质/水凝胶表征方向）。

来源：docs/mm-spectrum-多模态光谱-方案.md（M28 方案转原型）。
思想：红外(IR) + NMR + UV-vis 三模态联合推断分子结构——单模态各自携带互补线索，
融合后推断准确率显著高于任一单模态。

本原型（简化 + 诚实标注）：
  - 结构输出 = 6 个「结构片段」的**概率**（羟基/羰基/芳香环/羧基/胺基/双键，多标签）；
  - 三模态光谱各编码 2 个片段（IR→羟基/羰基，NMR→芳香环/羧基，UV→胺基/双键），
    合成谱（峰位 + 噪声）作输入；真实 IR/NMR/UV-vis 谱可替换（见接口说明）；
  - 轻量融合 = 特征拼接 + 逐片段 logistic（每片段一个二分类器，numpy 可跑）；
  - 输出：逐片段存在概率 P(片段|光谱)。

验收：pytest 全绿（≥4 用例）+ 断言「多模态输入的结构推断准确率 > 单一模态」（合成数据）。
纯 numpy + 标准库，无外部依赖。
"""
from __future__ import annotations

import numpy as np

N_FRAGMENTS = 6
FRAGMENT_NAMES = ["羟基", "羰基", "芳香环", "羧基", "胺基", "双键"]
# 每模态负责 2 个片段：IR=0,1  NMR=2,3  UV=4,5
MODALITIES = ["IR", "NMR", "UV-vis"]


def _spectrum(fragments: np.ndarray, frag_local: np.ndarray, n_bins: int,
              rng: np.random.Generator, noise: float = 0.08) -> np.ndarray:
    """单模态谱：负责的每个片段「存在→偶位峰、不存在→奇位峰」+ 底噪（合成 surrogate）。"""
    v = rng.normal(0.0, noise, size=n_bins)
    for i, f in enumerate(frag_local):
        lo, hi = 2 * i, 2 * i + 1
        v[lo if fragments[f] == 1 else hi] = 1.0 + rng.normal(0.0, 0.05)
    return v


def make_dataset(n: int = 400, seed: int = 0):
    """合成多模态谱 + 结构片段标签。返回 (X_ir, X_nmr, X_uv, Y) 各 (n, 4) / Y (n, 6)。"""
    rng = np.random.default_rng(seed)
    X_ir, X_nmr, X_uv, Y = [], [], [], []
    for _ in range(n):
        frag = rng.integers(0, 2, size=N_FRAGMENTS)
        X_ir.append(_spectrum(frag, np.array([0, 1]), 4, rng))
        X_nmr.append(_spectrum(frag, np.array([2, 3]), 4, rng))
        X_uv.append(_spectrum(frag, np.array([4, 5]), 4, rng))
        Y.append(frag)
    return (np.asarray(X_ir), np.asarray(X_nmr), np.asarray(X_uv), np.asarray(Y))


def concat_features(X_ir, X_nmr, X_uv) -> np.ndarray:
    """三模态特征拼接 → (n, 12)。"""
    return np.concatenate([X_ir, X_nmr, X_uv], axis=1)


class Logistic:
    """单特征二分类 logistic（numpy，每片段一个）。"""

    def __init__(self, iters: int = 1000, lr: float = 0.3, seed: int = 0):
        self.iters = iters
        self.lr = lr
        self.seed = seed
        self.w = None
        self.b = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Logistic":
        rng = np.random.default_rng(self.seed)
        self.w = rng.normal(0.0, 0.01, size=X.shape[1])
        for _ in range(self.iters):
            z = X @ self.w + self.b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            g = (p - y) / X.shape[0]
            self.w -= self.lr * (X.T @ g)
            self.b -= self.lr * g.sum()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(X @ self.w + self.b, -30, 30)))


def fragment_probabilities(X: np.ndarray, Y: np.ndarray, tr, te):
    """逐片段 logistic：返回 (片段概率矩阵, 片段准确率)。"""
    n_frag = Y.shape[1]
    probs = np.zeros((len(te), n_frag))
    accs = []
    for f in range(n_frag):
        clf = Logistic(seed=f).fit(X[tr], Y[tr, f].astype(float))
        p = clf.predict_proba(X[te])
        probs[:, f] = p
        accs.append(float(np.mean((p >= 0.5) == Y[te, f])))
    return probs, float(np.mean(accs))


def run_demo() -> None:
    X_ir, X_nmr, X_uv, Y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(Y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    acc = {}
    acc["IR"] = fragment_probabilities(X_ir, Y, tr, te)[1]
    acc["NMR"] = fragment_probabilities(X_nmr, Y, tr, te)[1]
    acc["UV-vis"] = fragment_probabilities(X_uv, Y, tr, te)[1]
    X_fused = concat_features(X_ir, X_nmr, X_uv)
    acc["融合"] = fragment_probabilities(X_fused, Y, tr, te)[1]

    print("[W59-03] 片段级结构推断准确率：")
    for k, v in acc.items():
        print(f"      {k:<8} {v:.3f}")
    print(f"[W59-03] 多模态(融合) > 单模态最优: "
          f"{acc['融合'] > max(acc['IR'], acc['NMR'], acc['UV-vis'])}")


if __name__ == "__main__":
    run_demo()
