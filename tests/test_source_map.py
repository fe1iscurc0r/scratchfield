"""工单 265 · P0-3 验收：声源成像（DAS / DAMAS / CLEAN-SC）。

验收来源：轮48 报告 §6 表 P0-3 ——
  `pytest tests/test_source_map.py -q` 全过；
  合成**双点源 + 白噪**，DAMAS 与 CLEAN-SC 定位误差均 **< λ/4**。

场景（与 P0-3 的物理量级一致）：
  - 空气，c = 343 m/s，f = 40 kHz ⇒ λ = 8.575 mm，判据 **λ/4 = 2.14 mm**
  - 24×24 平面阵，间距 λ/2（孔径 98.7 mm）
  - 扫描面 z0 = 0.30 m，41×41 网格（步长 2.00 mm ≤ λ/4）
  - 双点源位于 (±20 mm, 0)
"""

from __future__ import annotations

import numpy as np
import pytest

from acoustics import source_map as sm

C_AIR = 343.0
FREQ = 40e3
Z0 = 0.30
HALF = 0.04
N_GRID = 41
N_MIC = 24
SRC = [(-0.02, 0.0), (0.02, 0.0)]


@pytest.fixture(scope="module")
def setup():
    lam = C_AIR / FREQ
    pos = sm.planar_array(N_MIC, N_MIC, lam / 2)
    xs = np.linspace(-HALF, HALF, N_GRID)
    gx, gy = np.meshgrid(xs, xs, indexing="xy")
    grid = np.column_stack([gx.ravel(), gy.ravel()])
    A = sm.steering_matrix(pos, grid, z0=Z0, f=FREQ, c=C_AIR)
    src_idx = [int(np.argmin(np.hypot(grid[:, 0] - s[0], grid[:, 1] - s[1]))) for s in SRC]
    return {"lam": lam, "pos": pos, "grid": grid, "A": A, "src_idx": src_idx, "xs": xs}


def _errs_mm(found_xy: np.ndarray, srcs=SRC) -> list[float]:
    """每个真源到最近检出峰的距离（mm）。"""
    return [min(float(np.hypot(f[0] - s[0], f[1] - s[1])) for f in np.atleast_2d(found_xy)) * 1e3 for s in srcs]


# --------------------------------------------------------------------------- #
# 结构性 / 实现不变量
# --------------------------------------------------------------------------- #
def test_psf_diagonal_is_one(setup):
    """PSF 对角元为 1（|aᴴa|²/M² = 1）。

    这条不是形式主义：DAMAS 的经典 Gauss-Seidel 更新式**依赖 diag = 1**；
    我第一版按 `diag = 1/M²` 写，导致一步就把 q 打成负数、被 clip 到 0 后触发早退，
    返回的其实是 DAS 图本身（实测残差 92.86，主瓣一点没窄）。
    """
    psf = sm.psf_matrix(setup["A"])
    assert np.allclose(np.diag(psf), 1.0, atol=1e-12)
    assert np.all(psf >= 0)
    assert np.allclose(psf, psf.T)


def test_das_matches_bruteforce_reference(setup):
    """DAS 必须与逐点暴力实现一致（防止 einsum 的共轭写错——踩过一次）。"""
    A, grid = setup["A"], setup["grid"]
    C = sm.csm_from_sources(A, [setup["src_idx"][0]], noise_power=1e-6, seed=3)

    P_fast = sm.das_map(A, C)
    M = A.shape[0]
    P_ref = np.array([np.real(A[:, n].conj() @ C @ A[:, n]) / (M * M) for n in range(A.shape[1])])

    assert np.allclose(P_fast, P_ref, rtol=1e-10, atol=1e-16)
    assert P_fast.min() >= -1e-12, "DAS 图不该出现负功率"


def test_maps_are_nonnegative(setup):
    """DAS / DAMAS 的功率分布都必须非负。"""
    A = setup["A"]
    C = sm.csm_from_snapshots(sm.simulate_snapshots(A, setup["src_idx"], n_snap=30, noise_power=1e-2, seed=5))
    P = sm.das_map(A, C)
    q = sm.damas(P, sm.psf_matrix(A), iters=800)
    assert P.min() >= -1e-12
    assert q.min() >= 0.0


# --------------------------------------------------------------------------- #
# 定位精度（工单硬指标）
# --------------------------------------------------------------------------- #
def test_single_source_localization_within_quarter_wavelength(setup):
    """单点源：DAS 峰位误差 < λ/4。"""
    A, grid, lam = setup["A"], setup["grid"], setup["lam"]
    i0 = setup["src_idx"][0]
    C = sm.csm_from_snapshots(sm.simulate_snapshots(A, [i0], n_snap=30, noise_power=1e-2, seed=5))

    P = sm.das_map(A, C)
    found = sm.localize(grid, P, n_src=1)
    err = _errs_mm(grid[found.idx], srcs=[SRC[0]])[0]

    assert err < lam / 4 * 1e3, f"DAS 定位误差 {err:.2f}mm ≥ λ/4={lam / 4 * 1e3:.2f}mm"


def test_two_sources_damas_and_clean_sc_within_quarter_wavelength(setup):
    """**工单 P0-3 验收**：双点源 + 白噪，DAMAS 与 CLEAN-SC 定位误差均 < λ/4。"""
    A, grid, lam = setup["A"], setup["grid"], setup["lam"]
    limit_mm = lam / 4 * 1e3

    X = sm.simulate_snapshots(A, setup["src_idx"], n_snap=30, noise_power=1e-2, seed=5)
    C = sm.csm_from_snapshots(X)

    P = sm.das_map(A, C)
    q = sm.damas(P, sm.psf_matrix(A), iters=1500)
    src_damas = sm.localize(grid, q, n_src=2, exclude_neighbors=2)
    src_clean = sm.clean_sc(A, C, grid, n_src=2)

    err_damas = _errs_mm(grid[src_damas.idx])
    err_clean = _errs_mm(src_clean.positions())

    assert max(err_damas) < limit_mm, f"DAMAS 误差 {err_damas}mm ≥ {limit_mm:.2f}mm"
    assert max(err_clean) < limit_mm, f"CLEAN-SC 误差 {err_clean}mm ≥ {limit_mm:.2f}mm"


def test_damas_narrows_main_lobe(setup):
    """DAMAS 存在的意义：主瓣必须比 DAS 明显窄（实测 20.0mm → 8.0mm）。"""
    A, grid, xs = setup["A"], setup["grid"], setup["xs"]
    C = sm.csm_from_snapshots(sm.simulate_snapshots(A, [setup["src_idx"][0]], n_snap=30, noise_power=1e-2, seed=5))

    P = sm.das_map(A, C)
    q = sm.damas(P, sm.psf_matrix(A), iters=1500)

    def width3db(img_flat: np.ndarray) -> float:
        img = img_flat.reshape(N_GRID, N_GRID)
        row = img[N_GRID // 2]
        above = np.where(row >= row.max() / 2)[0]
        return float(xs[above.max()] - xs[above.min()]) * 1e3

    w_das, w_damas = width3db(P), width3db(q)
    assert w_damas < 0.6 * w_das, f"DAMAS 主瓣未明显变窄：{w_damas:.1f}mm vs DAS {w_das:.1f}mm"


def test_clean_sc_returns_nonnegative_power_and_distinct_sources(setup):
    """CLEAN-SC 的功率为正，且两源必须是不同格点。"""
    A, grid = setup["A"], setup["grid"]
    C = sm.csm_from_snapshots(sm.simulate_snapshots(A, setup["src_idx"], n_snap=30, noise_power=1e-2, seed=5))

    res = sm.clean_sc(A, C, grid, n_src=2)
    assert len(res.idx) == 2
    assert res.idx[0] != res.idx[1]
    assert np.all(res.power > 0)


def test_localize_rejects_nonsquare_grid(setup):
    with pytest.raises(ValueError):
        sm.localize(np.zeros((10, 2)), np.ones(10))
