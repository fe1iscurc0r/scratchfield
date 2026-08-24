"""射频大脑 · 测向模块（HW-02：MUSIC DOA）

均匀线阵（ULA）阵列信号测向，MUSIC 超分辨算法：

    X(M×K) --样本协方差--> R = XX^H/K --特征分解--> UΣU^H
    --噪声子空间 U_n（M-D 个最小特征向量）--> P(θ) = 1 / (a^H U_n U_n^H a)
    --谱峰检测--> DOA 估计

假设/边界：
- 远场窄带、各源不相干（相干源需空间平滑去相干，不在本模块范围）
- 信号源数 D < 阵元数 M（D 由调用方给定，或 MDL 准则自动估计）
- 阵元间距 d ≤ λ/2 无空间混叠（默认 d = λ/2）

核心接口：
- ``ula_steering_vector``    ULA 导向矢量 a(θ)
- ``synthesize_snapshots``   合成多源阵列快拍（高斯信号 + 高斯噪声）
- ``sample_covariance``      样本协方差矩阵
- ``estimate_doa``           MUSIC 空间谱扫描 + 谱峰检测
- ``estimate_n_sources_mdl`` Rissanen MDL 信号源数估计
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "DoaEstimate",
    "ula_steering_vector",
    "synthesize_snapshots",
    "sample_covariance",
    "estimate_doa",
    "estimate_n_sources_mdl",
]


# --------------------------------------------------------------------------- #
# 阵列几何
# --------------------------------------------------------------------------- #
def ula_steering_vector(theta_deg, n_elements, d_norm=0.5):
    """ULA 导向矢量 a(θ)，返回 M×G 矩阵（每列对应一个角度）。

    a_m(θ) = exp(-j·2π·m·(d/λ)·sinθ),  m = 0..M-1

    参数：
    - theta_deg: 标量或数组，角度（度）
    - n_elements: 阵元数 M
    - d_norm: 阵元间距 / 载波波长，默认 0.5（半波长，无空间混叠）
    """
    theta = np.deg2rad(np.atleast_1d(np.asarray(theta_deg, dtype=float)))
    m = np.arange(n_elements, dtype=float)[:, None]
    return np.exp(-2j * np.pi * d_norm * m * np.sin(theta))


# --------------------------------------------------------------------------- #
# 阵列快拍合成（仿真底）
# --------------------------------------------------------------------------- #
def synthesize_snapshots(
    doas_deg,
    n_elements=8,
    d_norm=0.5,
    n_snapshot=256,
    snr_db=20.0,
    seed=None,
):
    """合成 D 个远场窄带不相干源的 ULA 阵列快拍。

    模型：X = A·S + N
    - A (M×D)：导向矢量矩阵
    - S (D×K)：各源 i.i.d. 复圆对称高斯，单位功率，源间统计独立 → 不相干
    - N (M×K)：i.i.d. 复圆对称高斯，方差按 SNR 缩放（每阵元每源信噪比）

    返回 X (M×K)，每列一个快拍。
    """
    rng = np.random.default_rng(seed)
    doas = np.atleast_1d(np.asarray(doas_deg, dtype=float))
    n_src = len(doas)
    steering = ula_steering_vector(doas, n_elements, d_norm)  # M×D
    signal = (
        rng.standard_normal((n_src, n_snapshot))
        + 1j * rng.standard_normal((n_src, n_snapshot))
    ) / np.sqrt(2.0)  # 单位功率
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
# MUSIC 估计
# --------------------------------------------------------------------------- #
@dataclass
class DoaEstimate:
    """MUSIC 估计结果。"""

    doas_deg: np.ndarray    # 估计方向（升序，长度 ≤ n_sources，峰不足时更少）
    spectrum: np.ndarray    # 空间伪谱（dB）
    grid_deg: np.ndarray    # 扫描网格
    n_sources_requested: int


def _find_peaks(spectrum, n_peaks, guard_bins=2, min_sep_bins=2):
    """线性谱局部峰检测：按谱值降序取前 n_peaks 个，间隔不足的合并。

    guard_bins: 边界保护带，不把扫描边缘误判为源。
    min_sep_bins: 两个峰的最小间隔（bin），更近视为同一峰。
    """
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
        # 无局部峰（退化谱）：取有效区最大值
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
    """3 点抛物线插值细化谱峰位置（dB 域），突破扫描网格量化。

    顶点偏移 δ = h·(y0-y2) / (2·(y0-2y1+y2))，截断到 ±h/2。
    边界处不细化（返回原网格值）。
    """
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
    """MUSIC DOA 估计。

    流程：样本协方差 → 特征分解 → 噪声子空间（M-D 个最小特征向量）→
    空间伪谱 P(θ)=1/(a^H U_n U_n^H a) → 谱峰检测取前 n_sources 个峰。

    参数：
    - x: M×K 阵列快拍矩阵
    - n_sources: 信号源数 D（必须 < M）
    - d_norm: 阵元间距 / 波长
    - scan_step_deg: 空间谱扫描步进（度）
    - scan_range_deg: 扫描范围 (lo, hi)
    - grid_deg: 自定义扫描网格（覆盖前两项）
    - refine: 对谱峰做抛物线插值，突破网格量化（默认 True）

    返回 DoaEstimate。
    """
    x = np.asarray(x, dtype=complex)
    m_elem, n_snap = x.shape
    if n_sources >= m_elem:
        raise ValueError(f"n_sources={n_sources} 必须小于阵元数 M={m_elem}")
    if grid_deg is None:
        lo, hi = scan_range_deg
        grid_deg = np.linspace(lo, hi, int(round((hi - lo) / scan_step_deg)) + 1)

    cov = sample_covariance(x)
    eigvals, eigvecs = np.linalg.eigh(cov)  # 升序
    n_noise = m_elem - n_sources
    noise_subspace = eigvecs[:, :n_noise]   # M×(M-D)

    steering = ula_steering_vector(grid_deg, m_elem, d_norm)  # M×G
    proj = noise_subspace.conj().T @ steering                 # (M-D)×G
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


# --------------------------------------------------------------------------- #
# 信号源数估计（MDL）
# --------------------------------------------------------------------------- #
def estimate_n_sources_mdl(x, max_sources=None):
    """Wax & Kailath Rissanen MDL 准则估计信号源数。

    MDL(d) = -K(M-d)·ln( G(λ_{d+1..M}) / A(λ_{d+1..M}) ) + ½·d·(2M-d)·lnK

    其中 G/A 分别为噪声特征值的几何/算术均值，取 d ∈ [0, min(M-1, max_sources)]
    使 MDL 最小。
    """
    x = np.asarray(x, dtype=complex)
    m_elem, n_snap = x.shape
    eigvals = np.linalg.eigvalsh(sample_covariance(x))[::-1]  # 降序
    if max_sources is None:
        max_sources = m_elem - 1
    max_sources = min(max_sources, m_elem - 1)

    best_d, best_mdl = 0, np.inf
    for d in range(max_sources + 1):
        noise_eig = eigvals[d:]                    # λ_{d+1..M}
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
