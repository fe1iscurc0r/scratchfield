"""doa 子包——MUSIC / MVDR / 酉变换等测向算法集合。

将旧 doa.py 的所有内容内联于此，保持向后兼容；
同时暴露新迁入的 music_doa.py（独立类封装）。

导出接口（兼容旧 doa.py）：
    from mcpserver.rf_brain.doa import estimate_doa, ...
    from mcpserver.rf_brain.doa import MusicDOA   # 新增
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------- #
# 阵列几何
# --------------------------------------------------------------------------- #
def ula_steering_vector(theta_deg, n_elements, d_norm=0.5):
    """ULA 导向矢量 a(θ)，返回 M×G 矩阵（每列对应一个角度）。

    a_m(θ) = exp(-j·2π·m·(d/λ)·sinθ),  m = 0..M-1
    """
    theta = np.deg2rad(np.atleast_1d(np.asarray(theta_deg, dtype=float)))
    m = np.arange(n_elements, dtype=float)[:, None]
    return np.exp(-2j * np.pi * d_norm * m * np.sin(theta))


# --------------------------------------------------------------------------- #
# 阵列快拍合成
# --------------------------------------------------------------------------- #
def synthesize_snapshots(
    doas_deg,
    n_elements=8,
    d_norm=0.5,
    n_snapshot=256,
    snr_db=20.0,
    seed=None,
):
    """合成 D 个远场窄带不相干源的 ULA 阵列快拍。"""
    rng = np.random.default_rng(seed)
    doas = np.atleast_1d(np.asarray(doas_deg, dtype=float))
    n_src = len(doas)
    steering = ula_steering_vector(doas, n_elements, d_norm)
    signal = (
        rng.standard_normal((n_src, n_snapshot))
        + 1j * rng.standard_normal((n_src, n_snapshot))
    ) / np.sqrt(2.0)
    noise_power = 10.0 ** (-snr_db / 10.0)
    noise = np.sqrt(noise_power / 2.0) * (
        rng.standard_normal((n_elements, n_snapshot))
        + 1j * rng.standard_normal((n_elements, n_snapshot))
    )
    return steering @ signal + noise


# --------------------------------------------------------------------------- #
# 协方差矩阵
# --------------------------------------------------------------------------- #
def sample_covariance(x):
    """样本协方差矩阵 R = XX^H / K（M×M，Hermitian）。"""
    return (x @ x.conj().T) / x.shape[1]


# --------------------------------------------------------------------------- #
# MUSIC 估计（来自旧 doa.py）
# --------------------------------------------------------------------------- #
@dataclass
class DoaEstimate:
    doas_deg: np.ndarray
    spectrum: np.ndarray
    grid_deg: np.ndarray
    n_sources_requested: int


def _find_peaks(spectrum, n_peaks, guard_bins=2, min_sep_bins=2):
    n = len(spectrum)
    if n < 2 * guard_bins + 3:
        return np.array([], dtype=int)
    valid = np.ones(n, dtype=bool)
    valid[:guard_bins] = False
    valid[-guard_bins:] = False
    local_max = np.zeros(n, dtype=bool)
    local_max[1:-1] = (spectrum[1:-1] >= spectrum[:-2]) & (spectrum[1:-1] > spectrum[2:])
    cand = np.where(valid & local_max)[0]
    if len(cand) == 0:
        inner = np.arange(guard_bins, n - guard_bins)
        if len(inner) == 0:
            return np.array([], dtype=int)
        cand = np.array([inner[int(np.argmax(spectrum[inner]))]])
    order = cand[np.argsort(spectrum[cand])[::-1]]
    picked = []
    for i in order:
        if all(abs(int(i) - int(j)) >= min_sep_bins for j in picked):
            picked.append(int(i))
        if len(picked) >= n_peaks:
            break
    return np.array(sorted(picked), dtype=int)


def _parabolic_refine(spectrum, grid_deg, peak_idx):
    h = float(grid_deg[1] - grid_deg[0]) if len(grid_deg) > 1 else 0.0
    refined = []
    for i in peak_idx:
        i = int(i)
        if h <= 0.0 or i <= 0 or i >= len(spectrum) - 1:
            refined.append(float(grid_deg[i]))
            continue
        y0, y1, y2 = float(spectrum[i - 1]), float(spectrum[i]), float(spectrum[i + 1])
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) < 1e-30:
            refined.append(float(grid_deg[i]))
            continue
        delta = np.clip(0.5 * (y0 - y2) / denom, -0.5, 0.5)
        refined.append(float(grid_deg[i]) + delta * h)
    return np.array(refined)


def estimate_doa(
    x,
    n_sources,
    d_norm=0.5,
    scan_step_deg=0.1,
    scan_range_deg=(-90.0, 90.0),
    grid_deg=None,
    refine=True,
):
    """MUSIC DOA 估计。返回 DoaEstimate。"""
    x = np.asarray(x, dtype=complex)
    m_elem, n_snap = x.shape
    if n_sources >= m_elem:
        raise ValueError(f"n_sources={n_sources} 必须小于阵元数 M={m_elem}")
    if grid_deg is None:
        lo, hi = scan_range_deg
        grid_deg = np.linspace(lo, hi, int(round((hi - lo) / scan_step_deg)) + 1)

    cov = sample_covariance(x)
    eigvals, eigvecs = np.linalg.eigh(cov)
    n_noise = m_elem - n_sources
    noise_subspace = eigvecs[:, :n_noise]

    steering = ula_steering_vector(grid_deg, m_elem, d_norm)
    proj = noise_subspace.conj().T @ steering
    pseudo = 1.0 / (np.sum(np.abs(proj) ** 2, axis=0) + 1e-30)
    spectrum = 10.0 * np.log10(pseudo + 1e-30)

    peak_idx = _find_peaks(pseudo, n_sources)
    if refine:
        doas = _parabolic_refine(spectrum, grid_deg, peak_idx)
    else:
        doas = grid_deg[peak_idx]
    return DoaEstimate(
        doas_deg=doas,
        spectrum=spectrum,
        grid_deg=grid_deg,
        n_sources_requested=n_sources,
    )


def estimate_n_sources_mdl(x, max_sources=None):
    """Wax & Kailath Rissanen MDL 准则估计信号源数。"""
    x = np.asarray(x, dtype=complex)
    m_elem, n_snap = x.shape
    eigvals = np.linalg.eigvalsh(sample_covariance(x))[::-1]
    if max_sources is None:
        max_sources = m_elem - 1
    max_sources = min(max_sources, m_elem - 1)

    best_d, best_mdl = 0, np.inf
    for d in range(max_sources + 1):
        noise_eig = eigvals[d:]
        noise_eig = noise_eig[noise_eig > 1e-30]
        if len(noise_eig) == 0:
            continue
        geom = np.exp(np.mean(np.log(noise_eig)))
        arith = np.mean(noise_eig)
        ratio = geom / arith
        penalty = 0.5 * d * (2 * m_elem - d) * np.log(n_snap) if d > 0 else 0.0
        mdl = -n_snap * (m_elem - d) * np.log(ratio + 1e-30) + penalty
        if mdl < best_mdl:
            best_mdl, best_d = mdl, d
    return best_d


# --------------------------------------------------------------------------- #
# 新增：迁入的 music_doa.py（独立封装类）
# --------------------------------------------------------------------------- #
from mcpserver.rf_brain.doa.music_doa import MusicDOA, simulate_signals

__all__ = [
    # 旧接口（来自 doa.py）
    "DoaEstimate",
    "ula_steering_vector",
    "synthesize_snapshots",
    "sample_covariance",
    "estimate_doa",
    "estimate_n_sources_mdl",
    # 新接口（来自 music_doa.py）
    "MusicDOA",
    "simulate_signals",
]
