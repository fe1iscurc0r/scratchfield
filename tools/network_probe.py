"""凝胶网络量化最小探针（卷101 W101-06 · BSD-3 可借鉴，numpy-only 独立实现）。

设计参考：Xu et al./SOAX（BSD-3-Clause）的「多拉伸开蛇」（multiple stretching
open active contours）丝状网络提取：
- 蛇演化 = 内部力（拉伸/弯曲） + 外部力（图像梯度），见 snake.cc
  ComputeRHSVector/AddExternalForce/AddStretchingForce；
- 网络拓扑量化 = 端点/交叉点/段统计，见 junctions.cc。
本模块仅依赖 numpy（skimage 不在依赖清单），实现最小忠实骨架：
骨架细化（Zhang-Suen）、开蛇演化、脊线追踪、网络统计。
"""
from __future__ import annotations

import numpy as np


def image_gradient(img: np.ndarray):
    """中心差分梯度，返回 (gx, gy)，与源 ComputeImageGradient 语义对应。"""
    gy, gx = np.gradient(np.asarray(img, dtype=float))
    return gx, gy


def _sample_gradient(gx: np.ndarray, gy: np.ndarray, x: float, y: float) -> np.ndarray:
    """双线性采样梯度场，返回 [gx, gy]。

    最近邻取整采样在脊线峰值处形成梯度死区（点堆积塌缩），双线性采样
    得到连续力场，点可平滑收敛到脊线。
    """
    h, w = gx.shape
    x = min(max(x, 0.0), w - 1.001)
    y = min(max(y, 0.0), h - 1.001)
    x0, y0 = int(x), int(y)
    fx, fy = x - x0, y - y0
    w00, w10 = (1 - fx) * (1 - fy), fx * (1 - fy)
    w01, w11 = (1 - fx) * fy, fx * fy
    gxs = gx[y0, x0] * w00 + gx[y0, x0 + 1] * w10 + gx[y0 + 1, x0] * w01 + gx[y0 + 1, x0 + 1] * w11
    gys = gy[y0, x0] * w00 + gy[y0, x0 + 1] * w10 + gy[y0 + 1, x0] * w01 + gy[y0 + 1, x0 + 1] * w11
    return np.array([gxs, gys])


def snake_step(points: np.ndarray, gx: np.ndarray, gy: np.ndarray,
               alpha: float = 0.3, beta: float = 0.2, gamma: float = 0.5,
               rest_len: float | None = None) -> np.ndarray:
    """开蛇单步演化：p += 拉伸力 + 弯曲力 + 梯度外力（同步更新）。

    拉伸力：保持相邻点间距 = rest_len（过近排斥、过远吸引，沿点间方向），
    对应 SOAX 的 stretching force + Resample 语义；rest_len 缺省取初始平均间距。
    弯曲力：二阶差分平滑（p_{i-1} + p_{i+1} - 2p_i）。
    外力：最近邻像素采样图像梯度，朝亮脊移动。
    """
    pts = np.asarray(points, dtype=float).copy()
    n = len(pts)
    h, w = gx.shape
    if rest_len is None:
        if n > 1:
            rest_len = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).mean())
        else:
            rest_len = 1.0
    new = pts.copy()
    for i in range(n):
        f_stretch = np.zeros(2)
        for j in (i - 1, i + 1):
            if 0 <= j < n:
                d = pts[j] - pts[i]
                dist = np.linalg.norm(d)
                if dist > 1e-9:
                    f_stretch += alpha * (dist - rest_len) * d / dist
        f_bend = np.zeros(2)
        if 0 < i < n - 1:
            f_bend = beta * (pts[i - 1] + pts[i + 1] - 2.0 * pts[i])
        f_ext = _sample_gradient(gx, gy, pts[i, 0], pts[i, 1])
        new[i] = pts[i] + f_stretch + f_bend + gamma * f_ext
    return new


def trace_ridge(img: np.ndarray, start, n_points: int = 60, n_iter: int = 120,
                alpha: float = 0.3, beta: float = 0.2, gamma: float = 0.5,
                spacing: float = 1.0) -> np.ndarray:
    """从起点追踪亮脊，产出丝状路径。

    初始化沿梯度方向排布（梯度趋零时沿用上一方向，对应 InitializeSnakes 的
    梯度扫描种子思想），随后迭代 snake_step（对应 DeformSnakes）。
    """
    gx, gy = image_gradient(img)
    pts = np.zeros((n_points, 2))
    pts[0] = np.asarray(start, dtype=float)
    d_prev = np.zeros(2)
    mode = "approach"
    for i in range(1, n_points):
        g = _sample_gradient(gx, gy, pts[i - 1, 0], pts[i - 1, 1])
        nrm = np.linalg.norm(g)
        if mode == "approach":
            if nrm > 1e-9:
                ghat = g / nrm
                if i > 1 and np.dot(ghat, d_prev) < 0:
                    mode = "follow"   # 梯度方向翻转 = 已越过脊线
                else:
                    d = ghat
            else:
                d = d_prev if np.linalg.norm(d_prev) > 1e-9 else np.array([1.0, 0.0])
        if mode == "follow":
            tangent = np.array([g[1], -g[0]])   # 贴脊线：沿切线（脊线方向）行走
            nrm_t = np.linalg.norm(tangent)
            d = tangent / nrm_t if nrm_t > 1e-9 else d_prev
        if np.linalg.norm(d) < 1e-9:
            d = np.array([1.0, 0.0])
        d_prev = d
        pts[i] = pts[i - 1] + spacing * d
    for _ in range(n_iter):
        pts = snake_step(pts, gx, gy, alpha, beta, gamma, rest_len=spacing)
    return pts


def skeletonize(img: np.ndarray, threshold: float = 0.5, max_iter: int = 300) -> np.ndarray:
    """Zhang-Suen 细化，numpy-only 替代 skimage.morphology.skeletonize。

    返回 bool 骨架图（单像素宽的网络中线）。
    """
    skel = (np.asarray(img, dtype=float) > threshold).astype(np.uint8)
    h, w = skel.shape
    for _ in range(max_iter):
        removed_any = False
        for step in (1, 2):
            to_remove = []
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if skel[y, x] == 0:
                        continue
                    nb = skel[y - 1:y + 2, x - 1:x + 2]
                    p2, p3, p4 = nb[0, 1], nb[0, 2], nb[1, 2]
                    p5, p6, p7 = nb[2, 2], nb[2, 1], nb[2, 0]
                    p8, p9 = nb[1, 0], nb[0, 0]
                    b_count = int(p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9)
                    if not 2 <= b_count <= 6:
                        continue
                    ring = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
                    transitions = sum(1 for a, b in zip(ring, ring[1:]) if a == 0 and b == 1)
                    if transitions != 1:
                        continue
                    if step == 1:
                        if p2 * p4 * p6 != 0 or p4 * p6 * p8 != 0:
                            continue
                    else:
                        if p2 * p4 * p8 != 0 or p2 * p6 * p8 != 0:
                            continue
                    to_remove.append((y, x))
            for y, x in to_remove:
                skel[y, x] = 0
            if to_remove:
                removed_any = True
        if not removed_any:
            break
    return skel.astype(bool)


def _label_components(skel: np.ndarray):
    """8 邻域连通分量标记（BFS），返回 (labels, n_components)。"""
    h, w = skel.shape
    labels = np.zeros((h, w), dtype=np.int32)
    n_comp = 0
    for y in range(h):
        for x in range(w):
            if not skel[y, x] or labels[y, x] != 0:
                continue
            n_comp += 1
            stack = [(y, x)]
            labels[y, x] = n_comp
            while stack:
                cy, cx = stack.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and skel[ny, nx] and labels[ny, nx] == 0:
                            labels[ny, nx] = n_comp
                            stack.append((ny, nx))
    return labels, n_comp


def network_stats(skel: np.ndarray) -> dict:
    """骨架网络统计：端点数 / 交叉点数 / 连通分量数 / 骨架总长。

    用交叉数（8 邻域环 0→1 转移次数）分类：cn==1 端点，cn>=3 交叉点，
    其余为段点。避免「8 邻域计数」把交叉点旁的段点误判为交叉点
    （junctions.cc 拓扑语义的稳健近似）。
    """
    skel = np.asarray(skel, dtype=bool)
    h, w = skel.shape
    _, n_components = _label_components(skel)
    spad = np.pad(skel.astype(np.uint8), 1)  # 边界零填充，环采样免越界
    n_end = n_junc = total_len = 0
    for y in range(h):
        for x in range(w):
            if not skel[y, x]:
                continue
            total_len += 1
            nb = spad[y:y + 3, x:x + 3]
            ring = (nb[0, 1], nb[0, 2], nb[1, 2], nb[2, 2],
                    nb[2, 1], nb[2, 0], nb[1, 0], nb[0, 0], nb[0, 1])
            cn = sum(1 for a, b in zip(ring, ring[1:]) if a == 0 and b == 1)
            if cn == 1:
                n_end += 1
            elif cn >= 3:
                n_junc += 1
    return {
        "n_endpoints": n_end,
        "n_junctions": n_junc,
        "n_components": n_components,
        "total_length": total_len,
    }
