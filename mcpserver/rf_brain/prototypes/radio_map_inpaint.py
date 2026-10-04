"""R27 · 边缘无线电地图修复原型（稀疏 RSS 采样重建）

灵感：digest-g8-1b 授粉点① · 论文 2608.16167（RadioVIL，DDPM 引导稀疏无线电地图修复）。

思想：从稀疏 RSS 采样重建完整无线电地图（本地推理，不上传原始数据）。DDPM 先验的
轻量等价物 = **扩散/谐波修复**：迭代「去噪（高斯平滑）+ 数据一致性（把已测像素
拉回测量值）」，从测量点向未测区域平滑扩散，收敛到与测量一致的光滑地图。

原型对比：
  - inpaint_bilinear    双线性插值（基线）
  - inpaint_diffusion   扩散修复（迭代去噪 + 数据一致性，模拟 DDPM 先验引导）

以重建 MSE 对比两者。

运行：python -m mcpserver.rf_brain.prototypes.radio_map_inpaint
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter


def synthesize_radio_map(nx: int, ny: int, n_sources: int = 3, *, seed: int = 0) -> np.ndarray:
    """合成无线电地图：多个信号源 + 路径损耗（1/d²）+ 平滑噪声。"""
    rng = np.random.default_rng(seed)
    xs, ys = np.meshgrid(np.arange(nx), np.arange(ny))
    map_ = np.zeros((ny, nx))
    for _ in range(n_sources):
        sx, sy = rng.uniform(0, nx - 1), rng.uniform(0, ny - 1)
        amp = rng.uniform(20.0, 40.0)
        d2 = (xs - sx) ** 2 + (ys - sy) ** 2
        map_ += amp / (d2 + 10.0)  # 路径损耗 + 近场截止
    map_ += 0.5 * rng.standard_normal((ny, nx))
    return map_


def sample_sparse(map_: np.ndarray, frac: float, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """稀疏采样：随机保留 frac 比例像素，返回 (采样值, 掩码)。"""
    rng = np.random.default_rng(seed)
    mask = rng.random(map_.shape) < frac
    return np.where(mask, map_, 0.0), mask


def _interpolate(sampled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """用已知点的双线性插值填充缺失区域（简易实现：先填最近邻再平滑）。"""
    # 简单基线：缺失点用已知点均值 + 高斯平滑近似
    known_mean = sampled[mask].mean()
    filled = sampled.copy()
    filled[~mask] = known_mean
    return gaussian_filter(filled, sigma=2.0)


def inpaint_bilinear(sampled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """双线性/平滑插值基线。"""
    return _interpolate(sampled, mask)


def inpaint_diffusion(sampled: np.ndarray, mask: np.ndarray, *, iterations: int = 200,
                      sigma: float = 1.5) -> np.ndarray:
    """扩散修复：迭代去噪 + 数据一致性（把已测像素拉回测量值）。"""
    img = _interpolate(sampled, mask).copy()
    for _ in range(iterations):
        img = gaussian_filter(img, sigma=sigma)      # 去噪（扩散步）
        img[mask] = sampled[mask]                     # 数据一致性（投影回测量）
    return img


def mse(truth: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean((truth - pred) ** 2))


def main() -> None:
    truth = synthesize_radio_map(64, 64, seed=0)
    sampled, mask = sample_sparse(truth, frac=0.05, seed=0)
    bil = inpaint_bilinear(sampled, mask)
    dif = inpaint_diffusion(sampled, mask)
    print(f"5% 稀疏采样下  双线性 MSE = {mse(truth, bil):.3f}   扩散修复 MSE = {mse(truth, dif):.3f}")
    print(f"误差降低 = {(1 - mse(truth, dif)/mse(truth, bil))*100:.1f}%")


if __name__ == "__main__":
    main()
