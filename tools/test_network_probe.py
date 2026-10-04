"""network_probe 验收硬线（卷101 W101-06）。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.network_probe import (  # noqa: E402
    network_stats,
    skeletonize,
    snake_step,
    trace_ridge,
)


def _band_img(h=80, w=80, center=40, half_width=10):
    """帐篷形水平亮带：中心线 y=center，梯度幅值恒定（远优于高斯带）。"""
    yy, xx = np.mgrid[0:h, 0:w]
    return np.clip(1.0 - np.abs(yy - center) / half_width, 0.0, 1.0)


def test_skeletonize_thins_thick_bar():
    """Zhang-Suen 细化：5px 厚横条 → 单像素宽中线。"""
    img = np.zeros((60, 60))
    img[28:33, 5:55] = 1.0
    skel = skeletonize(img)
    assert skel.sum() < 100                     # 远小于原 250 个前景点
    col_counts = skel.sum(axis=0)
    assert col_counts.max() <= 1                # 单像素宽
    assert skel[30, 5:55].sum() >= 40           # 中线连通


def test_network_stats_on_cross():
    """十字网络：1 交叉点（中心）+ 4 端点 + 1 连通分量。"""
    img = np.zeros((41, 41))
    img[20, 5:36] = 1.0
    img[5:36, 20] = 1.0
    skel = skeletonize(img)
    stats = network_stats(skel)
    assert stats["n_junctions"] == 1
    assert stats["n_endpoints"] == 4
    assert stats["n_components"] == 1
    assert stats["total_length"] > 50


def test_snake_step_moves_toward_ridge():
    """蛇点朝亮脊移动：起点 y=35 → 收敛到 y≈40 亮带中心，且不塌缩。"""
    img = _band_img()
    gy, gx = np.gradient(img.astype(float))   # np.gradient 返回 (grad_y, grad_x)
    points = np.column_stack([np.arange(5, 35, dtype=float), np.full(30, 35.0)])
    for _ in range(300):
        points = snake_step(points, gx, gy)
    assert abs(points[:, 1].mean() - 40.0) < 2.0
    dists = np.linalg.norm(np.diff(points, axis=0), axis=1)
    assert dists.min() > 0.5                    # 拉伸力保持间距，不塌缩


def test_trace_ridge_follows_band():
    """脊线追踪：逼近脊线后沿脊线方向行走，间距保持、路径铺开。"""
    img = _band_img()
    path = trace_ridge(img, (5.0, 35.0), n_points=50, n_iter=150)
    assert abs(path[:, 1].mean() - 40.0) < 2.5
    assert path[:, 0].max() - path[:, 0].min() > 20.0   # 沿脊线铺开
    dists = np.linalg.norm(np.diff(path, axis=0), axis=1)
    assert dists.min() > 0.5                    # rest-length 拉伸力防塌缩
    assert dists.max() < 10.0                   # 路径不外飞
