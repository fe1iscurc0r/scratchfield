"""W69-07 融合 · 卫星过境跟踪（吸收 ground-station 的卫星跟踪算法，GPL-3.0 → 本仓 AGPL 兼容）

从 TLE（两行根数）出发做**简化 Keplerian 传播**（非完整 SGP4，标注为设计/模拟用途），
得到卫星 ECI 位置 → 转地心地面站方位角/仰角 → 找过境窗口（AOS/LOS/峰值仰角）。
算法吸收自 ground-station 的「轨道根数 → 过境预测」思路，用本仓 numpy 重实现（GPL 可融合）。

纯 numpy。用途：IC-705 卫星线 / 天线云台的过境预测与指向参考。
"""
from __future__ import annotations

import numpy as np

__all__ = ["parse_tle", "propagate_eci", "topocentric_az_el", "find_pass"]

MU = 3.986004418e14  # 地球引力常数 (m^3/s^2)
RE = 6378137.0       # 地球赤道半径 (m)
TWO_PI = 2.0 * np.pi


def parse_tle(line1: str, line2: str) -> dict:
    """解析 TLE 两行 → 轨道根数（倾角/RAAN/偏心率在行2，平近点角/平均运动在行2）。"""
    # 行 2：倾角(9-16)、RAAN(18-25)、偏心率(27-33)、近地点幅角(35-42)、
    #       平近点角(44-51)、平均运动(53-63)
    incl_deg = float(line2[8:16])
    raan_deg = float(line2[17:25])
    ecc = float("0." + line2[26:33].strip())
    arg_perigee_deg = float(line2[34:42])
    mean_anomaly_deg = float(line2[43:51])
    mean_motion_rev_day = float(line2[52:63])
    n = mean_motion_rev_day * TWO_PI / 86400.0  # rad/s
    a = (MU / n**2) ** (1.0 / 3.0)  # 半长轴
    return {
        "inclination": np.deg2rad(incl_deg),
        "raan": np.deg2rad(raan_deg),
        "eccentricity": ecc,
        "arg_perigee": np.deg2rad(arg_perigee_deg),
        "mean_anomaly": np.deg2rad(mean_anomaly_deg),
        "mean_motion": n,
        "semi_major_axis": a,
    }


def _solve_kepler(M: np.ndarray, e: float, iters: int = 10) -> np.ndarray:
    """牛顿迭代解开普勒方程 M = E - e·sin(E)。"""
    E = M.copy()
    for _ in range(iters):
        E = E - (E - e * np.sin(E) - M) / (1.0 - e * np.cos(E))
    return E


def propagate_eci(el: dict, t_since_epoch: np.ndarray) -> np.ndarray:
    """Keplerian 传播 → ECI 位置 (N,3)。"""
    n, e = el["mean_motion"], el["eccentricity"]
    M = el["mean_anomaly"] + n * t_since_epoch
    E = _solve_kepler(M, e)
    nu = 2.0 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    r = el["semi_major_axis"] * (1 - e * np.cos(E))
    # 轨道面坐标
    x_orb = r * np.cos(nu)
    y_orb = r * np.sin(nu)
    z_orb = np.zeros_like(x_orb)
    # 旋转到 ECI（RAAN → 倾角 → 近地点幅角）
    p = el["arg_perigee"]
    pos = np.stack([x_orb, y_orb, z_orb], axis=1)
    R = _rotz(-el["raan"]) @ _rotx(-el["inclination"]) @ _rotz(-p)
    return pos @ R.T


def _rotx(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rotz(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def topocentric_az_el(eci: np.ndarray, gs_ecef: np.ndarray, gmst: float) -> tuple[np.ndarray, np.ndarray]:
    """ECI 位置 → 地面站方位角/仰角。gs_ecef: 地面站地固坐标 (3,)。"""
    # ECI → ECEF（按格林尼治恒星时 GMST 旋转）
    c, s = np.cos(gmst), np.sin(gmst)
    ecef = eci @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]]).T
    rho = ecef - gs_ecef  # 相对地面站向量（ECEF 系，近似）
    # 地面站本地 ENU：简化为用地理北/东/上（近似，测试级精度）
    up = gs_ecef / np.linalg.norm(gs_ecef)
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    e_ = rho @ east
    n_ = rho @ north
    u_ = rho @ up
    rng = np.linalg.norm(rho, axis=1)
    el = np.arcsin(u_ / rng)
    az = np.arctan2(e_, n_) % TWO_PI
    return az, el


def find_pass(el: dict, gs_ecef: np.ndarray, gmst: float, duration_s: float = 3600.0, dt_s: float = 10.0) -> dict:
    """扫描一段时间找过境：AOS（升出地平）、LOS（落回地平）、峰值仰角。"""
    t = np.arange(0.0, duration_s, dt_s)
    pos = propagate_eci(el, t)
    _, el_deg = topocentric_az_el(pos, gs_ecef, gmst)
    el_deg = np.rad2deg(el_deg)
    above = el_deg > 0.0
    if not above.any():
        return {"has_pass": False, "peak_el_deg": float(el_deg.max()), "aos_s": None, "los_s": None}
    idx = np.flatnonzero(above)
    return {
        "has_pass": True,
        "peak_el_deg": float(el_deg.max()),
        "aos_s": float(t[idx[0]]),
        "los_s": float(t[idx[-1]]),
    }
