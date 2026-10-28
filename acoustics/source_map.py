"""声源成像内核：DAS / DAMAS / CLEAN-SC（工单 265 · P0-3）。

用途
----
把传声器阵列的互谱矩阵（CSM）反演成**声源分布图**，用于轮48 声发射/空化声源的定位。
三种算法由粗到精：

1. **DAS**（延时求和 / 常规波束形成）：稳健但主瓣宽、旁瓣高；
2. **DAMAS**（deconvolution approach）：把 DAS 图看作"真实源分布 × 点扩散函数"的卷积，
   做非负反卷积 ⇒ 主瓣被压窄；代价是迭代；
3. **CLEAN-SC**（Sijtsma）：从 CSM 里逐个扣除已识别源的相干成分，
   对**相干源**（本例的双点源）分辨率最好。

约定
----
- 窄带模型：单一频率 `f`，远场平面波近似。
- 阵列坐标 `pos` 形如 (M, 2)（x, y），单位 m。
- 扫描面在 `z = z0` 平面上，`grid_xy` 形如 (N, 2)。
- 导向向量取 `exp(-j·k·r)`，其中 `k = 2πf/c · [x/(z0), y/(z0), 1]` 的横向分量。

零新增依赖：仅 numpy。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "SourceMap",
    "planar_array",
    "steering_matrix",
    "csm_from_sources",
    "simulate_snapshots",
    "csm_from_snapshots",
    "das_map",
    "psf_matrix",
    "damas",
    "clean_sc",
    "localize",
]


# --------------------------------------------------------------------------- #
# 阵列与导向向量
# --------------------------------------------------------------------------- #
def planar_array(nx: int = 8, ny: int = 8, spacing: float = 4.3e-3) -> np.ndarray:
    """规则平面阵列（网格中心在原点），返回 (M, 2) 的 x/y 坐标。"""
    xs = (np.arange(nx) - (nx - 1) / 2.0) * spacing
    ys = (np.arange(ny) - (ny - 1) / 2.0) * spacing
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    return np.column_stack([gx.ravel(), gy.ravel()])


def steering_matrix(
    pos: np.ndarray,
    grid_xy: np.ndarray,
    *,
    z0: float,
    f: float,
    c: float = 343.0,
) -> np.ndarray:
    """导向向量矩阵 A，形状 (M, N)。

    远场近似下第 n 个扫描点到第 m 个传声器的相位为 `-j·k·(r_m - r_n)`，
    这里按扫描面法向取单位方向向量，省略公共相位。
    """
    pos = np.asarray(pos, dtype=float)
    grid = np.asarray(grid_xy, dtype=float)
    k = 2.0 * np.pi * f / float(c)

    # 扫描点相对阵列中心的单位方向（远场）：u = (x/z0, y/z0)，模长按 sqrt 归一
    ux = grid[:, 0] / z0
    uy = grid[:, 1] / z0
    norm = np.sqrt(ux**2 + uy**2 + 1.0)
    ux, uy = ux / norm, uy / norm

    # 相位 = k * (u_x * x_m + u_y * y_m)
    phase = k * (pos[None, :, 0] * ux[:, None] + pos[None, :, 1] * uy[:, None])
    return np.exp(-1j * phase).T  # (M, N)


def csm_from_sources(
    A: np.ndarray,
    src_idx: list[int],
    amps: list[complex] | None = None,
    *,
    noise_power: float = 1e-3,
    seed: int = 0,
) -> np.ndarray:
    """由源构造互谱矩阵：C = Σ |a_s|² a aᴴ + σ² I，并做对角加载。"""
    M = A.shape[0]
    if amps is None:
        amps = [1.0 + 0j] * len(src_idx)
    C = np.zeros((M, M), dtype=complex)
    for idx, amp in zip(src_idx, amps, strict=True):
        a = A[:, idx]
        C += (abs(amp) ** 2) * np.outer(a, a.conj())
    if noise_power > 0:
        rng = np.random.default_rng(seed)
        # 白噪：对角加载 + 少量非对角随机量，模拟有限快拍的估计误差
        C += noise_power * np.eye(M)
        eps = noise_power * 0.05 * (rng.standard_normal((M, M)) + 1j * rng.standard_normal((M, M)))
        C += (eps + eps.conj().T) / 2.0
    return C


def simulate_snapshots(
    A: np.ndarray,
    src_idx: list[int],
    *,
    n_snap: int = 30,
    noise_power: float = 1e-3,
    seed: int = 0,
) -> np.ndarray:
    """生成有限快拍的阵列频域数据 X（形状 (n_snap, M)）。

    每个快拍里各源带**随机相位**（模拟非相干激励），再叠加复高斯白噪。
    这是比 `csm_from_sources` 更接近实测的口径——C 由若干快拍估计而来，
    必然带估计误差，能检验算法对噪声的稳健性。
    """
    A = np.asarray(A, dtype=complex)
    rng = np.random.default_rng(seed)
    n_snap = int(n_snap)
    M = A.shape[0]

    X = np.zeros((n_snap, M), dtype=complex)
    for idx in src_idx:
        phase = np.exp(1j * rng.uniform(0, 2 * np.pi, n_snap))
        X += phase[:, None] * A[:, idx][None, :]
    if noise_power > 0:
        sigma = np.sqrt(noise_power / 2.0)
        X += sigma * (rng.standard_normal((n_snap, M)) + 1j * rng.standard_normal((n_snap, M)))
    return X


def csm_from_snapshots(X: np.ndarray, *, diag_load: float = 0.0) -> np.ndarray:
    """由快拍估计互谱矩阵：C = (1/T) Σ_t x_t x_tᴴ（+ 可选对角加载）。

    ⚠️ **不要写成 `XᴴX / T`**：`X` 的形状是 (T, M)，`(XᴴX)[m,k] = Σ_t conj(X[t,m])X[t,k]`
    等于 `C[k,m]`，即得到的是 **`Cᵀ = C*`（共轭）**。
    对单源 `x = p·a` 而言，`C* = a* aᵀ`，于是 DAS 的峰值会落在 `u = -u_s`（**镜像歧义**）——
    双源左右对称时镜像互相抵消看不出来，单源立刻暴露（实测 −20 mm 的源被定到 +20 mm）。
    正确写法是 `x_t x_tᴴ`，即 `Xᵀ conj(X) / T`。
    """
    X = np.asarray(X, dtype=complex)
    T = X.shape[0]
    C = (X.T @ X.conj()) / float(T)
    # 数值上强制 Hermitian（消除浮点非对称）
    C = (C + C.conj().T) / 2.0
    if diag_load:
        C = C + diag_load * np.eye(C.shape[0])
    return C


# --------------------------------------------------------------------------- #
# 1) DAS
# --------------------------------------------------------------------------- #
def das_map(A: np.ndarray, C: np.ndarray) -> np.ndarray:
    """常规波束形成（延时求和）：P_n = a_nᴴ C a_n / M²。

    注意 `A^H C A` 的对角元才是 `a_nᴴ C a_n`：第二项必须用 `A[m, n]` 本身
    （写成 `conj(A[m, n])` 会算出共轭量并出现负功率——踩过一次）。
    """
    M = A.shape[0]
    AC = A.conj().T @ C  # (N, M)，第 n 行是 (Aᴴ C) 的第 n 行
    P = np.einsum("nm,nm->n", AC, A.T)  # Σ_m (AᴴC)[n,m]·A[m,n]
    return np.real(P) / (M * M)


def psf_matrix(A: np.ndarray) -> np.ndarray:
    """点扩散函数矩阵：PSF[n, s] = |a_nᴴ a_s|² / M²。

    DAMAS 的反卷积模型：`P = PSF · q`（P 为 DAS 图，q 为真实源功率分布）。
    """
    M = A.shape[0]
    G = A.conj().T @ A  # (N, N)
    return (np.abs(G) ** 2) / (M * M)


# --------------------------------------------------------------------------- #
# 2) DAMAS
# --------------------------------------------------------------------------- #
def _psf_lipschitz(psf: np.ndarray, n_iter: int = 20, seed: int = 0) -> float:
    """幂迭代估计 ‖PSFᵀPSF‖₂（即 Lipschitz 常数），避免 1681² 矩阵做特征分解。"""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(psf.shape[1])
    nv = np.linalg.norm(v)
    if nv == 0:
        return 1.0
    v /= nv
    lam = 1.0
    for _ in range(int(n_iter)):
        w = psf.T @ (psf @ v)
        lam = float(np.linalg.norm(w))
        if lam <= 0:
            return 1.0
        v = w / lam
    return lam


def damas(
    P: np.ndarray,
    psf: np.ndarray,
    *,
    iters: int = 2000,
    tol: float = 1e-8,
    x0: np.ndarray | None = None,
) -> np.ndarray:
    """DAMAS 反卷积（非负最小二乘形式）。

    模型：`P ≈ PSF · q`，求 `q ≥ 0`。DAMAS 文献里的 Gauss-Seidel 更新式
    （`q ← max(0, P − Σ_{s≠n} PSF[n,s] q[s])`，因为 `diag(PSF) = 1`）
    与"在 `q ≥ 0` 约束下最小化 `‖PSF q − P‖²`"是同一目标的两种解法；
    这里用**投影梯度 + 幂迭代估 Lipschitz 步长**，收敛更稳、也不依赖 `diag=1` 的假设。

    返回主瓣被压窄后的源功率分布；对双源分辨能力明显强于 DAS。
    """
    P = np.asarray(P, dtype=float).ravel()
    psf = np.asarray(psf, dtype=float)
    n = P.size

    L = _psf_lipschitz(psf)
    step = 1.0 / L if L > 0 else 1.0

    q = np.zeros(n) if x0 is None else np.clip(np.asarray(x0, float).ravel(), 0.0, None)

    prev_obj: float | None = None
    for _ in range(int(iters)):
        resid = psf @ q - P
        grad = psf.T @ resid
        q = np.clip(q - step * grad, 0.0, None)

        obj = float(resid @ resid)
        # ⚠️ 初值必须为 None：用 inf 会让 `inf <= tol*inf` 恒真、第一轮就退出（踩过）
        if prev_obj is not None and abs(prev_obj - obj) <= tol * max(1.0, abs(prev_obj)):
            break
        prev_obj = obj
    return q


# --------------------------------------------------------------------------- #
# 3) CLEAN-SC
# --------------------------------------------------------------------------- #
@dataclass
class SourceMap:
    """定位结果。"""

    idx: list[int]
    xy: np.ndarray
    power: np.ndarray

    def positions(self) -> np.ndarray:
        return np.asarray(self.xy, dtype=float)


def clean_sc(
    A: np.ndarray,
    C: np.ndarray,
    grid_xy: np.ndarray,
    *,
    n_src: int = 2,
    n_iter: int = 200,
    stop_ratio: float = 1e-3,
) -> SourceMap:
    """CLEAN-SC（Sijtsma 2007 的简化实现）。

    每轮：
    1. 在 DAS 图上取当前最大点 `n*`，其导向向量 `w = a_n*/M`；
    2. 相干源分量 `g = C w / (wᴴ C w)`（列向量），贡献 `P* = wᴴ C w`；
    3. 从 CSM 扣除 `P* · g gᴴ / (gᴴ g)`（同时扣掉其相干旁瓣）；
    4. 记录 `(n*, P*)`，直到识别够 `n_src` 个或能量降到 `stop_ratio`。
    """
    A = np.asarray(A, dtype=complex)
    grid_xy = np.asarray(grid_xy, dtype=float)
    C = np.array(C, dtype=complex, copy=True)
    M = A.shape[0]

    found_idx: list[int] = []
    found_pw: list[float] = []
    p0 = float(np.real(np.trace(C))) or 1.0

    for _ in range(int(n_iter)):
        P = das_map(A, C)
        n_star = int(np.argmax(P))
        w = A[:, n_star] / np.sqrt(M)

        denom = float(np.real(w.conj() @ C @ w))
        if denom <= 0:
            break
        p_star = denom
        g = (C @ w) / denom  # 相干源分量（列）
        g_norm2 = float(np.real(g.conj() @ g))
        if g_norm2 <= 0:
            break

        C = C - p_star * np.outer(g, g.conj()) / g_norm2

        if n_star not in found_idx:
            found_idx.append(n_star)
            found_pw.append(p_star)
        if len(found_idx) >= n_src:
            break
        if p_star / p0 < stop_ratio:
            break

    idx = found_idx[:n_src]
    return SourceMap(idx=idx, xy=grid_xy[idx], power=np.asarray(found_pw[:n_src]))


# --------------------------------------------------------------------------- #
# 定位封装
# --------------------------------------------------------------------------- #
def localize(
    grid_xy: np.ndarray,
    power: np.ndarray,
    *,
    n_src: int = 2,
    exclude_neighbors: int = 1,
) -> SourceMap:
    """从一张功率图上取前 `n_src` 个**互不相邻**的局部最大点。

    `exclude_neighbors` 以"格点索引距离"近似抑制主瓣内的重复峰
    （网格是规则矩形，故用 (i, j) 坐标的切比雪夫距离）。
    """
    grid_xy = np.asarray(grid_xy, dtype=float)
    p = np.asarray(power, dtype=float).ravel()
    n_side = int(round(np.sqrt(p.size)))
    if n_side * n_side != p.size:
        raise ValueError("功率图必须是方形网格（N = n_side²）")

    order = np.argsort(p)[::-1]
    picked: list[int] = []
    for idx in order:
        i, j = divmod(int(idx), n_side)
        if all(max(abs(i - divmod(k, n_side)[0]), abs(j - divmod(k, n_side)[1])) > exclude_neighbors for k in picked):
            picked.append(int(idx))
        if len(picked) >= n_src:
            break

    return SourceMap(idx=picked, xy=grid_xy[picked], power=p[np.asarray(picked)])
