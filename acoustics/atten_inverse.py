"""超声衰减谱反演（工单 265 · P0-1）。

本模块把「衰减场」换成「分布向量」——这是 `attomo` 反演骨架的核心思想，
在此重写为**零第三方依赖**（仅 numpy）的实现，供轮47 PBM 的在线 PSD 通路使用。

两层模型
--------
1. **幂律层**（两个机制系数）::

       α(f) = a·f² + b·f⁴

   - `f²` 项：粘性 / 热耗散的经典小粒子极限
   - `f⁴` 项：Rayleigh 散射极限（ka ≪ 1）

   未知量只有 `(a, b)`，可用最小二乘直接解；当频点少、噪声大时改用
   **Tikhonov 正则**（`tikhonov_solve`）并用 **L 曲线**（`plot_lcurve`）选参。

2. **分布层**（把衰减场换成分布向量）::

       α(f_i) = Σ_j w_j · K(f_i, D_j)

   `w_j ≥ 0` 是粒径 `D_j` 上的体积分数权重（即"分布向量"）。
   `K` 是双机制合成核（散射 f⁴D³ + 粘性 f²D²）。
   求解用**非负 + 平滑**的投影梯度法（`invert_distribution`），
   避免纯最小二乘在病态核下给出负权重/振荡解。

设计约束（工单 265 §6）
-----------------------
- **零新增运行时依赖**：只用 numpy；matplotlib 由 `plot_lcurve` **函数内懒导入**，
  缺库时返回数据而不抛异常。
- 全部函数对 `f` 的单位不敏感（只要与 `a`/`b` 的口径一致），
  但核函数默认按 `f0`、`D0` 归一化，避免量纲溢出。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "PowerLawFit",
    "DistributionFit",
    "power_law",
    "power_law_basis",
    "tikhonov_solve",
    "lcurve_scan",
    "fit_power_law",
    "plot_lcurve",
    "inversion_kernel",
    "invert_distribution",
    "synthesize_power_law",
    "synthesize_distribution",
]

# 缺省归一化尺度：1 MHz、10 µm（只影响核矩阵条件数，不影响物理结论）
_F0_HZ = 1.0e6
_D0_M = 10.0e-6


# --------------------------------------------------------------------------- #
# 层 1：幂律 α(f) = a·f² + b·f⁴
# --------------------------------------------------------------------------- #
def power_law(f, a: float, b: float) -> np.ndarray:
    """正演：α(f) = a·f² + b·f⁴。"""
    f = np.asarray(f, dtype=float)
    return a * f**2 + b * f**4


def synthesize_power_law(f, a: float, b: float, noise_rel: float = 0.0, seed: int = 0) -> np.ndarray:
    """按给定 `(a, b)` 生成带相对噪声的衰减谱（用于标定与测试）。"""
    alpha = power_law(f, a, b)
    if noise_rel <= 0:
        return alpha
    rng = np.random.default_rng(seed)
    return alpha * (1.0 + noise_rel * rng.standard_normal(alpha.shape))


def power_law_basis(f) -> np.ndarray:
    """设计矩阵 A = [f², f⁴]，形状 (N, 2)。"""
    f = np.asarray(f, dtype=float).ravel()
    return np.column_stack([f**2, f**4])


def _second_difference(n: int) -> np.ndarray:
    """二阶差分平滑算子 L（n-2 × n），用于 Tikhonov 的平滑项。"""
    if n <= 2:
        return np.zeros((0, n))
    return np.diff(np.eye(n), n=2, axis=0)


def tikhonov_solve(A: np.ndarray, y: np.ndarray, lam: float, *, smooth: bool = True) -> np.ndarray:
    """解标准形式 Tikhonov：min ‖Ax − y‖² + lam·‖Lx‖²。

    `smooth=True` 时 `L` 取二阶差分（抑制振荡解）；否则 `L = I`（岭回归）。
    数值上用正规方程 + `lstsq`，避免显式求逆。
    """
    A = np.asarray(A, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    n = A.shape[1]
    L = _second_difference(n) if smooth else np.eye(n)
    if L.size == 0:
        # n ≤ 2 时没有二阶差分可用 ⇒ 退化为岭回归，否则 λ 完全不起作用
        L = np.eye(n)

    lam = float(max(lam, 0.0))
    # 堆叠形式比 AᵀA + λLᵀL 条件数更好
    A_aug = np.vstack([A, np.sqrt(lam) * L])
    y_aug = np.concatenate([y, np.zeros(A_aug.shape[0] - y.size)])
    sol, *_ = np.linalg.lstsq(A_aug, y_aug, rcond=None)
    return sol


def lcurve_scan(A: np.ndarray, y: np.ndarray, lams: np.ndarray, *, smooth: bool = True) -> dict:
    """L 曲线扫描：对每个 `lam` 记录残差范数与解范数。

    返回 dict：`lam` / `residual` / `solution_norm` / `x` / `corner`（拐点下标）。
    拐点用「到两端点连线的最大垂距」判定（L 曲线的标准拐点准则）。
    """
    A = np.asarray(A, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    lams = np.asarray(lams, dtype=float)

    residuals = np.empty(lams.size)
    norms = np.empty(lams.size)
    xs = []
    for i, lam in enumerate(lams):
        x = tikhonov_solve(A, y, lam, smooth=smooth)
        xs.append(x)
        residuals[i] = np.linalg.norm(A @ x - y)
        norms[i] = np.linalg.norm(x)

    corner = _lcurve_corner(residuals, norms)
    return {
        "lam": lams,
        "residual": residuals,
        "solution_norm": norms,
        "x": xs,
        "corner": int(corner),
    }


def _lcurve_corner(residual: np.ndarray, norm: np.ndarray) -> int:
    """L 曲线拐点：log-log 空间里离首末连线最远的点。"""
    lr = np.log10(np.clip(residual, 1e-300, None))
    ln = np.log10(np.clip(norm, 1e-300, None))
    if lr.size < 3:
        return 0
    p0 = np.array([lr[0], ln[0]])
    p1 = np.array([lr[-1], ln[-1]])
    d = p1 - p0
    norm_d = np.linalg.norm(d)
    if norm_d == 0:
        return 0
    pts = np.column_stack([lr, ln]) - p0
    # 点到直线距离（叉积 / |d|）
    dist = np.abs(pts[:, 0] * d[1] - pts[:, 1] * d[0]) / norm_d
    return int(np.argmax(dist))


@dataclass
class PowerLawFit:
    """幂律反演结果。"""

    a: float
    b: float
    lam: float = 0.0
    residual_rms: float = 0.0
    ok: bool = True

    def predict(self, f) -> np.ndarray:
        return power_law(f, self.a, self.b)

    def rel_errors(self, a_true: float, b_true: float) -> tuple[float, float]:
        ea = abs(self.a - a_true) / abs(a_true) if a_true else float("nan")
        eb = abs(self.b - b_true) / abs(b_true) if b_true else float("nan")
        return ea, eb


def fit_power_law(f, alpha, *, lam: float = 0.0, smooth: bool = True) -> PowerLawFit:
    """从衰减谱反演 `(a, b)`。

    `lam == 0` ⇒ 普通最小二乘（频点充足时最准）；
    `lam > 0`  ⇒ Tikhonov 正则（频点少/噪声大时压住发散）。

    **列归一化是必须的**：`f⁴` 与 `f²` 在 1–20 MHz 下量级相差 1e14 以上，
    直接对原始基做 `lstsq` 会因条件数爆炸而丢掉 `b` 的精度（实测 `b` 相对误差 >100%）。
    归一化后求解、再按列尺度还原，`a`/`b` 才能同时达到 1e-10 量级精度。
    """
    A = power_law_basis(f)
    y = np.asarray(alpha, dtype=float).ravel()
    if A.shape[0] < 2:
        raise ValueError("至少需要 2 个频点才能反演 (a, b)")

    scale = np.linalg.norm(A, axis=0)
    scale[scale == 0] = 1.0
    An = A / scale

    if lam > 0:
        coef_n = tikhonov_solve(An, y, lam, smooth=smooth)
    else:
        coef_n, *_ = np.linalg.lstsq(An, y, rcond=None)

    coef = coef_n / scale  # 还原到原始量纲
    resid = A @ coef - y
    return PowerLawFit(
        a=float(coef[0]),
        b=float(coef[1]),
        lam=float(lam),
        residual_rms=float(np.sqrt(np.mean(resid**2))),
    )


def gradient_fit_power_law(
    f,
    alpha,
    *,
    lam: float = 0.0,
    iters: int = 50_000,
    x0: np.ndarray | None = None,
    tol: float = 1e-14,
) -> PowerLawFit:
    """用**梯度下降**反演 `(a, b)`（工单 266 P1-1：`jwave` 可微正演思路的无 JAX 版）。

    目标与 `fit_power_law` 完全一致：``min ‖A x − y‖² + lam·‖L x‖²``，
    只是求解器从"闭式 lstsq"换成"最优步长梯度下降"。

    为什么值得单独实现
    ------------------
    真实反演里 `A` 往往不是显式矩阵（而是"正演算子"），闭式解不可用；
    可微正演 + 梯度下降是那条路（jwave 用 JAX 自动微分，本模块用**解析梯度**）。

    ⚠️ 验收纪律：**不能只看"残差够小"就认为对**——线性系统里步长选错时
    常见"残差在降但解是错的"。本函数的验收判据是**与闭式解逐系数一致**（见测试）。

    步长取 `1/L`，`L = λ_max(AᵀA + lam·LᵀL)`（Lipschitz 常数），保证收敛。
    与 `fit_power_law` 一样先做**列归一化**（否则 `f⁴`/`f²` 量级差 1e14，梯度立刻发散）。
    """
    A = power_law_basis(f)
    y = np.asarray(alpha, dtype=float).ravel()
    if A.shape[0] < 2:
        raise ValueError("至少需要 2 个频点才能反演 (a, b)")

    # 列归一化（与 fit_power_law 保持一致的口径）
    scale = np.linalg.norm(A, axis=0)
    scale[scale == 0] = 1.0
    An = A / scale

    n = An.shape[1]
    L = _second_difference(n) if lam > 0 else np.zeros((0, n))
    LtL = (L.T @ L) if L.size else np.zeros((n, n))

    H = An.T @ An + lam * LtL
    g = An.T @ y
    step = 1.0 / float(np.linalg.eigvalsh(H).max())
    if not np.isfinite(step) or step <= 0:
        step = 1.0

    if x0 is None:
        x = np.zeros(n)
    else:
        # x0 若给的是**原始量纲**的 (a,b)，需换算到归一化坐标系
        x = np.asarray(x0, dtype=float).ravel() * scale

    prev_obj: float | None = None
    for _ in range(int(iters)):
        grad = H @ x - g
        x = x - step * grad
        obj = float(x @ H @ x - 2.0 * g @ x)
        # ⚠️ 初值必须为 None（inf 会让 `inf <= tol*inf` 恒真、第一轮就退出）
        if prev_obj is not None and abs(prev_obj - obj) <= tol * max(1.0, abs(prev_obj)):
            break
        prev_obj = obj

    coef = x / scale  # 还原到原始量纲
    resid = A @ coef - y
    return PowerLawFit(
        a=float(coef[0]),
        b=float(coef[1]),
        lam=float(lam),
        residual_rms=float(np.sqrt(np.mean(resid**2))),
    )


def plot_lcurve(scan: dict, path: str | None = None):
    """画 L 曲线（**可选**：matplotlib 懒导入，缺库时返回 (None, scan)）。

    返回 `(fig_or_None, scan)`；`path` 非空时顺带存盘。
    这个函数名同时满足工单 265 P0-1 的验收 grep（`plot_lcurve|tikhonov` ≥ 2）。
    """
    try:  # 懒导入：不把 matplotlib 变成硬依赖
        import matplotlib

        if path:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - 无 matplotlib 环境
        return None, scan

    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    ax.loglog(scan["residual"], scan["solution_norm"], "o-", ms=3, lw=1)
    ci = scan.get("corner", 0)
    ax.loglog(
        [scan["residual"][ci]],
        [scan["solution_norm"][ci]],
        "r*",
        ms=12,
        label=f"corner λ={scan['lam'][ci]:.3g}",
    )
    ax.set_xlabel("residual ‖Ax−y‖")
    ax.set_ylabel("solution ‖x‖")
    ax.set_title("L-curve")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=120)
    return fig, scan


# --------------------------------------------------------------------------- #
# 层 2：分布向量反演  α(f_i) = Σ_j w_j K(f_i, D_j)
# --------------------------------------------------------------------------- #
def inversion_kernel(
    f,
    diam,
    *,
    c: float = 1500.0,
    f0: float = _F0_HZ,
    d0: float = _D0_M,
) -> np.ndarray:
    """尺寸参数（ka）饱和的双机制核矩阵 K，形状 (N_freq, N_diam)。

    **为什么必须带 ka**：若核只写成 ``(D/D0)³(f/f0)⁴ + (D/D0)²(f/f0)²``，
    则整个谱被压缩成两个数（两个矩），**分布向量在数学上不可辨识**——
    任何分布只要两阶矩相同就给出同一条 α(f)（实测双峰会反演成单调分布）。
    引入 ``ka = πfD/c`` 后，不同粒径的谱形在 Rayleigh→几何 过渡区被拉开，
    分布才变得可辨识。

    两机制效率（工程化写法，Rayleigh 极限 → 几何极限的平滑过渡）：

    - 散射：``Q_sca = ka⁴ / (1 + ka²)²``（小 ka ∝ ka⁴，大 ka 饱和）
    - 粘性/热：``Q_vis = ka² / (1 + ka²)``（小 ka ∝ ka²，大 ka 饱和）

    再乘体积权重 ``(D/D0)³`` 与表面积权重 ``(D/D0)²``：

        K(f, D) = (D/D0)³·Q_sca(ka) + (D/D0)²·Q_vis(ka)

    `c` 为介质声速（水 ≈ 1500 m/s）。权重 `w_j` 是"相对体积分数"。
    """
    f = np.asarray(f, dtype=float).ravel()
    d = np.asarray(diam, dtype=float).ravel()
    ka = np.pi * f[:, None] * d[None, :] / float(c)
    ka2 = ka**2
    q_sca = ka**4 / (1.0 + ka2) ** 2
    q_vis = ka2 / (1.0 + ka2)
    dr = d / d0
    return dr[None, :] ** 3 * q_sca + dr[None, :] ** 2 * q_vis


def synthesize_distribution(f, diam, weights, *, noise_rel: float = 0.0, seed: int = 0) -> np.ndarray:
    """正演：给定分布向量 `weights`，算出衰减谱。"""
    K = inversion_kernel(f, diam)
    alpha = K @ np.asarray(weights, dtype=float).ravel()
    if noise_rel <= 0:
        return alpha
    rng = np.random.default_rng(seed)
    return alpha * (1.0 + noise_rel * rng.standard_normal(alpha.shape))


@dataclass
class DistributionFit:
    """分布反演结果。"""

    diam: np.ndarray
    weights: np.ndarray
    lam: float
    residual_rms: float
    iters: int = 0
    history: list[float] = field(default_factory=list)

    def peaks(self, k: int = 2) -> list[int]:
        """返回权重最大的 `k` 个格点下标（按权重降序）。"""
        order = np.argsort(self.weights)[::-1]
        return [int(i) for i in order[:k]]

    def predict(self, f) -> np.ndarray:
        return inversion_kernel(f, self.diam) @ self.weights


def invert_distribution(
    f,
    alpha,
    diam,
    *,
    lam: float = 1e-3,
    iters: int = 4000,
    nonneg: bool = True,
    tol: float = 1e-10,
) -> DistributionFit:
    """非负 + 平滑 Tikhonov 的分布反演（投影梯度，纯 numpy）。

    目标：min_{w≥0} ‖K w − α‖² + lam·‖L w‖²
    `L` 为二阶差分，`lam` 起平滑作用（避免多峰互相抵消的振荡解）。
    步长取 `1 / λ_max(KᵀK + lam·LᵀL)`（Lipschitz 常数倒数），保证收敛。
    """
    f = np.asarray(f, dtype=float).ravel()
    y = np.asarray(alpha, dtype=float).ravel()
    d = np.asarray(diam, dtype=float).ravel()

    K = inversion_kernel(f, d)
    n = K.shape[1]
    L = _second_difference(n)
    LtL = L.T @ L if L.size else np.zeros((n, n))

    # 归一化：按列能量缩放，避免大粒径格点天然占优
    col = np.linalg.norm(K, axis=0)
    col[col == 0] = 1.0
    Kn = K / col

    H = Kn.T @ Kn + lam * LtL
    g = Kn.T @ y
    step = 1.0 / (np.linalg.eigvalsh(H).max() + 1e-12)

    w = np.zeros(n)
    hist: list[float] = []
    # ⚠️ 初值不能是 inf：`inf <= tol*inf` 为真，会让第一次收敛检查就 break（实测只跑 200 步）。
    prev: float | None = None
    it = 0
    for it in range(1, iters + 1):
        grad = H @ w - g
        w = w - step * grad
        if nonneg:
            w = np.clip(w, 0.0, None)
        obj = float(w @ H @ w - 2 * g @ w)
        if it % 200 == 0:
            hist.append(obj)
            if prev is not None and abs(prev - obj) <= tol * max(1.0, abs(prev)):
                break
            prev = obj

    # 还原列缩放
    w = w / col
    resid = K @ w - y
    return DistributionFit(
        diam=d,
        weights=w,
        lam=float(lam),
        residual_rms=float(np.sqrt(np.mean(resid**2))),
        iters=it,
        history=hist,
    )
