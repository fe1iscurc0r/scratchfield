"""R34 · 电磁孪生稀疏重建原型（1% 探测点补全频谱）

灵感：weekly_pollination 电磁孪生段（EM Twin 路线）。用图正则 + 稀疏采样，从
**1% 探测点重建全图**频谱——电磁数字孪生的稀疏重建核心。

思想：把频谱地图建模为图上信号，用图拉普拉斯正则（平滑先验）做稀疏重建：
  minimize ‖M·x - y‖² + λ·xᵀLx
其中 M=采样掩码、y=采样值、L=图拉普拉斯（网格邻接）。闭式解：
  x̂ = (MᵀM + λL)⁻¹ Mᵀy
从极稀疏采样（0.5%~10%）重建，输出重建误差 vs 采样率曲线。

运行：python -m mcpserver.rf_brain.prototypes.em_twin_sparse_recon
"""
from __future__ import annotations

import numpy as np


def synthesize_spectrum_map(nx: int, ny: int, n_sources: int = 3, *, seed: int = 0) -> np.ndarray:
    """合成电磁频谱地图（多源路径损耗 + 平滑）。"""
    rng = np.random.default_rng(seed)
    xs, ys = np.meshgrid(np.arange(nx), np.arange(ny))
    m = np.zeros((ny, nx))
    for _ in range(n_sources):
        sx, sy = rng.uniform(0, nx - 1), rng.uniform(0, ny - 1)
        amp = rng.uniform(20.0, 40.0)
        m += amp / ((xs - sx) ** 2 + (ys - sy) ** 2 + 8.0)
    return m


def graph_laplacian(nx: int, ny: int) -> np.ndarray:
    """2D 网格图的拉普拉斯矩阵（4-邻接）。"""
    n = nx * ny
    L = np.zeros((n, n))
    idx = np.arange(n).reshape(ny, nx)
    for dy, dx in ((1, 0), (0, 1)):   # 下、右邻接（上、左对称）
        y, x = np.meshgrid(np.arange(ny - dy), np.arange(nx - dx), indexing="ij")
        a = idx[y, x].ravel()
        b = idx[y + dy, x + dx].ravel()
        L[a, a] += 1; L[b, b] += 1
        L[a, b] -= 1; L[b, a] -= 1
    return L


def sample_sparse(map_: np.ndarray, frac: float, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """稀疏采样：随机保留 frac 比例像素。返回 (采样向量, 掩码向量)。"""
    rng = np.random.default_rng(seed)
    mask = rng.random(map_.size) < frac
    y = np.where(mask, map_.ravel(), 0.0)
    return y, mask.astype(float)


def reconstruct(y: np.ndarray, mask: np.ndarray, L: np.ndarray, lam: float = 0.1) -> np.ndarray:
    """图正则闭式解：x̂ = (MᵀM + λL)⁻¹ Mᵀy。"""
    M = np.diag(mask)
    A = np.diag(mask) + lam * L          # MᵀM = diag(mask)（mask 为 0/1）
    return np.linalg.solve(A, mask * y)


def rel_error(truth: np.ndarray, pred: np.ndarray) -> float:
    return float(np.linalg.norm(truth - pred) / np.linalg.norm(truth))


def main() -> None:
    nx = ny = 32
    truth = synthesize_spectrum_map(nx, ny, seed=0)
    L = graph_laplacian(nx, ny)
    print(f"{'采样率':<8}{'相对重建误差':>12}")
    for frac in (0.005, 0.01, 0.02, 0.05, 0.1):
        y, mask = sample_sparse(truth, frac, seed=0)
        pred = reconstruct(y, mask, L, lam=0.1).reshape(ny, nx)
        print(f"{frac*100:>5.1f}%{rel_error(truth, pred):>12.3f}")


if __name__ == "__main__":
    main()
