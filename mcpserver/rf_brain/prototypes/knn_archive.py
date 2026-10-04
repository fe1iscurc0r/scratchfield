"""R35 · kNN 存档反演原型（ESP32 实时分类查表）

离线建库（频谱特征 → 类别）+ 在线最近邻查表，用于 ESP32 端侧实时分类。

原型：
  - 离线：K 类信号各成高斯簇（d 维频谱特征），建 kNN 存档（特征矩阵 + 标签）
  - 在线：新特征向量做最近邻查表 → 类别
  - 评估：分类准确率 + 查表复杂度/内存估算（含 int8 定点化要点）

查表复杂度（brute-force kNN）：
  - 延迟：每次查询 N×d 次乘加 + N 次比较，int8 定点可并行 4×（SIMD）
  - 内存：N×d 个特征值（int8 时每值 1 字节）+ N 个标签
  - 加速：KD-tree / 球树可把查询降到 O(log N)，但 MCU 上 brute-force 更省内存

运行：python -m mcpserver.rf_brain.prototypes.knn_archive
"""
from __future__ import annotations

import numpy as np


def synthesize_archive(n_per_class: int, n_classes: int, d: int, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """离线建库：K 类各生成 n 个 d 维特征（高斯簇，中心分散）。"""
    rng = np.random.default_rng(seed)
    centers = rng.standard_normal((n_classes, d)) * 4.0
    feats, labels = [], []
    for c in range(n_classes):
        X = centers[c] + 0.5 * rng.standard_normal((n_per_class, d))
        feats.append(X)
        labels.append(np.full(n_per_class, c))
    return np.vstack(feats), np.concatenate(labels)


def knn_lookup(query: np.ndarray, archive: np.ndarray, labels: np.ndarray, k: int = 1) -> int:
    """在线最近邻查表：返回 query 的预测类别（k 近邻多数表决）。"""
    dist = np.linalg.norm(archive - query, axis=1)
    topk = np.argsort(dist)[:k]
    votes = labels[topk].astype(int)
    return int(np.bincount(votes).argmax())


def classification_accuracy(n_test: int, archive, labels, n_classes: int, d: int, *,
                            noise: float = 0.0, seed: int = 1) -> float:
    """在线查表准确率（含可选噪声）。"""
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_test):
        c = rng.integers(0, n_classes)
        # 从该类的存档中取一个作原型 + 噪声
        proto = archive[np.flatnonzero(labels == c)[0]]
        q = proto + noise * rng.standard_normal(d)
        hits += knn_lookup(q, archive, labels, k=3) == c
    return hits / n_test


def cost_estimate(N: int, d: int) -> dict:
    """查表延迟/内存估算（brute-force，int8 定点）。"""
    return {
        "macs_per_query": N * d,
        "memory_bytes_fp32": N * d * 4 + N * 2,
        "memory_bytes_int8": N * d + N,        # 特征 1 字节 + 标签
        "approx_cycles_int8_simd": N * d // 4 + N,  # 4×int8 SIMD + 比较
    }


def main() -> None:
    N, K, d = 200, 4, 8   # 200 条存档、4 类、8 维特征
    archive, labels = synthesize_archive(N // K, K, d, seed=0)
    acc_clean = classification_accuracy(500, archive, labels, K, d, noise=0.0)
    acc_noisy = classification_accuracy(500, archive, labels, K, d, noise=0.3)
    cost = cost_estimate(N, d)
    print(f"kNN 查表准确率：干净 = {acc_clean*100:.0f}%  含噪 = {acc_noisy*100:.0f}%")
    print(f"每次查询 MACs = {cost['macs_per_query']}  int8 内存 = {cost['memory_bytes_int8']} B  "
          f"≈SIMD 周期 = {cost['approx_cycles_int8_simd']}")


if __name__ == "__main__":
    main()
