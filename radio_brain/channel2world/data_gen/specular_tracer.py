"""简化镜面反射追踪器（降级路径，纯 NumPy）。

对应实现草稿 §七「风险 1」的降级方案：当 NVIDIA Sionna RT 无法在目标环境
安装（Sionna 依赖 TensorFlow，且官方未提供 Python 3.13 轮子）时，用镜像源法
（image-source method）为矩形工厂场景生成多径信道参数。

工厂场景以矩形反射面为主（四面墙 + 地面 + 天花板，共 6 个反射面），镜像源法
在这些平面上给出**精确**的路径时延与到达角；反射损耗按反射次数折减。该方案
不依赖任何第三方渲染/RT 库，仅需 NumPy，可在 CPU 上小规模验证整条数据管线。

镜像源用 Allen-Berkley 格点公式枚举：各轴反射次数 (nx, ny, nz) ∈ Z，
|nx|+|ny|+|nz| ≤ max_reflections。第 ``nx`` 次反射后的镜像坐标

    x_img(nx) = nx·Lx + (xs  if nx 为偶) 或  nx·Lx + (Lx − xs)  (nx 为奇)

该公式天然去除了「同一面墙连续反射两次」的退化镜像（镜像 = 源本身）。近似
假设（已在 README 标注）：低阶镜像的反射点落在有限墙范围内，不校验反射点
越界，适用于源/接收机位于工厂中部、矩形反射面为主的场景（衍射关闭）。

与 Sionna 主路径（``sionna_factory_gen.py``）共享同一输出 schema，因此 T2 的
``dataset.py`` 无需感知后端差异。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

C_LIGHT = 299_792_458.0  # 真空光速 (m/s)


@dataclass(frozen=True)
class FactoryLayout:
    """矩形工厂大厅几何与材料参数。

    论文 Table I：7.0 GHz、工厂布局、BS 高 15 m、UE 高 1.5 m、≤3 次反射、
    衍射关闭。工厂尺寸为可调默认值（室内工厂大厅量级）。
    """

    width: float = 60.0  # x 方向跨度 (m)
    length: float = 90.0  # y 方向跨度 (m)
    height: float = 20.0  # z 方向跨度 (m)，须 > BS 高度 15 m
    reflection_loss_db: float = 6.02  # 每次反射损耗，|Γ| = 0.5 ≈ -6.02 dB


def _axis_image(n: int, xs: float, extent: float) -> float:
    """Allen-Berkley 镜像源格点：某轴第 n 次反射后的镜像坐标。"""
    if n % 2 == 0:
        return n * extent + xs
    return n * extent + (extent - xs)


def _spherical(direction: np.ndarray) -> tuple[float, float]:
    """方向单位向量 → (theta, phi)。

    theta: 天顶角（相对 +z，向上），范围 [0, π]；phi: 方位角（相对 +x），范围 [0, 2π)。
    """
    norm = np.linalg.norm(direction)
    d = direction / max(norm, 1e-12)
    theta = float(np.arccos(np.clip(d[2], -1.0, 1.0)))
    phi = float(np.arctan2(d[1], d[0]))
    if phi < 0.0:
        phi += 2.0 * np.pi
    return theta, phi


class SpecularTracer:
    """矩形工厂的镜像源法射线追踪器。

    对 |nx|+|ny|+|nz| ≤ max_reflections 的每组镜像源，镜像源到 UE 的直线距离
    即该反射路径的精确长度，方向即到达方向（§七 关键 hack：直接输出路径参数，
    无需自行做 3D 参数估计）。
    """

    def __init__(
        self,
        layout: FactoryLayout | None = None,
        max_reflections: int = 3,
        max_paths: int = 12,
        frequency_hz: float = 7.0e9,
    ) -> None:
        self.layout = layout or FactoryLayout()
        self.max_reflections = max_reflections
        self.max_paths = max_paths
        self.frequency_hz = frequency_hz

    def trace(self, bs_pos: np.ndarray, ue_pos: np.ndarray) -> dict[str, np.ndarray | int]:
        """追踪 BS → UE 的多径信道。

        返回 dict:
            tau_rel   (P,) float32  相对时延（秒），LOS 为 0
            aoa_theta (P,) float32  到达天顶角（rad）
            aoa_phi   (P,) float32  到达方位角（rad）
            gain_rel  (P,) float32  相对增益（dB），LOS 为 0
            num_paths int           有效路径数（1..max_paths）
        """
        bs = np.asarray(bs_pos, dtype=np.float64)
        ue = np.asarray(ue_pos, dtype=np.float64)
        lx, ly, lz = self.layout.width, self.layout.length, self.layout.height

        los_dist = float(np.linalg.norm(ue - bs))
        # (路径长, 镜像源位置, 反射次数)
        candidates: list[tuple[float, np.ndarray, int]] = [(los_dist, bs.copy(), 0)]

        r = self.max_reflections
        for nx in range(-r, r + 1):
            for ny in range(-r, r + 1):
                for nz in range(-r, r + 1):
                    k = abs(nx) + abs(ny) + abs(nz)
                    if k == 0 or k > r:
                        continue
                    img = np.array(
                        [
                            _axis_image(nx, bs[0], lx),
                            _axis_image(ny, bs[1], ly),
                            _axis_image(nz, bs[2], lz),
                        ],
                        dtype=np.float64,
                    )
                    candidates.append((float(np.linalg.norm(ue - img)), img, k))

        # 按路径长度升序（时延升序），取最短 max_paths 条。
        candidates.sort(key=lambda c: c[0])
        candidates = candidates[: self.max_paths]

        tau_rel = []
        aoa_theta = []
        aoa_phi = []
        gain_rel = []
        for dist, img, k in candidates:
            tau_rel.append((dist - los_dist) / C_LIGHT)
            # 到达方向 = 从 UE 指向（镜像）源的方向；LOS 时即从 UE 指向 BS。
            theta, phi = _spherical(img - ue)
            aoa_theta.append(theta)
            aoa_phi.append(phi)
            # 相对增益（dB）：自由空间路径差 + 每次反射损耗。
            g = 20.0 * np.log10(los_dist / max(dist, 1e-9)) - k * self.layout.reflection_loss_db
            gain_rel.append(g)

        return {
            "tau_rel": np.asarray(tau_rel, dtype=np.float32),
            "aoa_theta": np.asarray(aoa_theta, dtype=np.float32),
            "aoa_phi": np.asarray(aoa_phi, dtype=np.float32),
            "gain_rel": np.asarray(gain_rel, dtype=np.float32),
            "num_paths": len(candidates),
        }
