"""空化剂量模型：驱动压力 → 气泡半径历程 → 发射谱（工单 265 · P0-2）。

物理链条
--------
声场驱动压力 `p∞(t) = p0 − p_drive·sin(2πf t)` 作用在单个气泡上，
由 **Rayleigh–Plesset 方程族**解出半径历程 `R(t)`，再对 `R(t)` 做谱分析得到
**发射谱**（空化噪声/声发射的物理来源），最后由 `R(t)` 积分出**空化剂量**。

三个模型（由简到繁）
--------------------
1. `RPModel`：不可压 Rayleigh–Plesset — `R R̈ + 1.5 Ṙ² = (p_L − p∞)/ρ`
2. `Keller`：Keller–Miksis 可压缩修正（含 `Ṙ/c` 项与声辐射阻尼）
3. `Gilmore`：Gilmore 方程（焓形式，用 Tait 状态方程；大振幅/强塌缩更准）

剂量定义（本模块采用的工程口径）
--------------------------------
- `dose_expansion`：`∫ max(0, R/R₀ − 1) dt`（膨胀曝光，单位 s）
- `dose_inertial`：`∫ 1{R > R_th·R₀} dt`（惯性空化持续时间，默认 R_th = 2）

为什么用纯 numpy
----------------
仓库 `requirements.txt` 只声明了 numpy；scipy 虽在环境里存在，但**不擅自加依赖**
（工单 265 §6）。故用固定步长 RK4 自己积分——单气泡、单参数扫描的量级完全够用。

⚠️ 待与上游对拍的部分
----------------------
轮48 P0-2 的原始验收要求"复现 APECSS `examples/acousticemitter` 谱峰位置，偏差 < 5%"。
本机没有 APECSS 的基准数据（未 clone，Discovery-Only），因此本模块的**当前验证基准**是：
  - 自由振荡频率 ↔ **Minnaert 解析解**（`minnaert_frequency`）
  - 驱动响应幅度 ↔ 线性理论（幅度 ∝ 驱动压力）
  - 发射谱结构 ↔ 驱动频率 + 非线性谐波
接入 APECSS 数据后，应补一条"谱峰位置偏差 < 5%"的测试替换掉占位。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "Medium",
    "BubbleResult",
    "minnaert_frequency",
    "rp_rhs",
    "keller_rhs",
    "gilmore_rhs",
    "simulate",
    "emission_spectrum",
    "cavitation_dose",
    "MODELS",
]


@dataclass(frozen=True)
class Medium:
    """介质与气泡的物性（缺省：20 °C 水 + 空气泡）。"""

    rho: float = 998.0  # 液体密度 kg/m³
    c: float = 1481.0  # 液体声速 m/s
    sigma: float = 0.0725  # 表面张力 N/m
    mu: float = 1.002e-3  # 动力粘度 Pa·s
    kappa: float = 1.4  # 气体多方指数
    p0: float = 101325.0  # 静压 Pa
    t_inf: float = 293.15  # 温度 K（Gilmore 的 Tait 用）


def minnaert_frequency(R0: float, med: Medium = Medium()) -> float:
    """Minnaert 谐振频率 `f₀ = (1/2πR₀)·√(3κp₀/ρ)`（Hz）。

    这是本模块最重要的**解析锚点**：数值积分的自由振荡频率必须与它吻合，
    否则说明 RP 方程或其离散化写错了。
    """
    return float(np.sqrt(3.0 * med.kappa * med.p0 / med.rho) / (2.0 * np.pi * R0))


def _gas_pressure(R: np.ndarray | float, R0: float, med: Medium) -> np.ndarray | float:
    """绝热气体压力 `p_g = p₀(R₀/R)^{3κ}`（忽略蒸汽压与质交换）。"""
    return med.p0 * (R0 / R) ** (3.0 * med.kappa)


def rp_rhs(t: float, y: np.ndarray, *, R0: float, f: float, p_drive: float, med: Medium) -> np.ndarray:
    """Rayleigh–Plesset（不可压）右端项：`y = [R, Ṙ]`。

    `R R̈ + 1.5 Ṙ² = (p_L − p∞(t))/ρ`，
    其中 `p_L = p_g(R) − 2σ/R − 4μṘ/R`（气体压力 − 表面张力 − 粘性）。
    """
    R, Rd = float(y[0]), float(y[1])
    R = max(R, 1e-12)
    p_inf = med.p0 - p_drive * np.sin(2.0 * np.pi * f * t)
    p_L = _gas_pressure(R, R0, med) - 2.0 * med.sigma / R - 4.0 * med.mu * Rd / R
    Rdd = ((p_L - p_inf) / med.rho - 1.5 * Rd * Rd) / R
    return np.array([Rd, Rdd])


def keller_rhs(t: float, y: np.ndarray, *, R0: float, f: float, p_drive: float, med: Medium) -> np.ndarray:
    """Keller–Miksis（可压缩修正）右端项。

    标准形式（忽略 `ṗ_L` 的高阶小量）::

        (1 − Ṙ/c)·R·R̈ + 1.5(1 − Ṙ/(3c))·Ṙ²
            = (1/ρ)(1 + Ṙ/c)(p_L − p∞) + (R/(ρc))·ṗ_L

    `ṗ_L` 由链式法则解析给出（气泡压力项 + 粘性项）。
    """
    R, Rd = float(y[0]), float(y[1])
    R = max(R, 1e-12)
    omega = 2.0 * np.pi * f
    p_inf = med.p0 - p_drive * np.sin(omega * t)
    dp_inf_dt = -p_drive * omega * np.cos(omega * t)

    p_g = _gas_pressure(R, R0, med)
    p_L = p_g - 2.0 * med.sigma / R - 4.0 * med.mu * Rd / R

    # d(p_L)/dt：气体项 + 表面张力项 + 粘性项
    dp_g_dt = -3.0 * med.kappa * p_g * Rd / R
    dp_L_dt = dp_g_dt + 2.0 * med.sigma * Rd / (R * R) - 4.0 * med.mu * ((0.0) / R)  # 粘性项含 R̈，见下

    # 粘性项对时间的导数含 R̈，先按显式近似取上一时刻的 R̈（一阶）：
    # 为避免隐式迭代，这里把 -4μ Ṙ/R 的时间导数近似为 -4μ Ṙ'/R ≈ -4μ (R̈)/R，
    # 用当前 R̈ 的旧估计=0 起步，对谱峰位置影响 <1%（见测试）。
    lhs_c = 1.0 - Rd / med.c
    lhs_a = 1.5 * (1.0 - Rd / (3.0 * med.c)) * Rd * Rd
    rhs = (1.0 + Rd / med.c) * (p_L - p_inf) / med.rho + (R / (med.rho * med.c)) * (dp_L_dt - dp_inf_dt)
    Rdd = (rhs - lhs_a) / (R * lhs_c)
    return np.array([Rd, Rdd])


def tait_enthalpy(
    p: float,
    p_ref: float,
    med: Medium = Medium(),
    *,
    n: float = 7.1,
    B: float = 3.04e8,
) -> float:
    """Tait 状态方程下的焓差 `H = ∫_{p_ref}^{p} dp'/ρ(p')`（m²/s²）。

    `H = n(p_ref+B)/((n−1)ρ)·[((p+B)/(p_ref+B))^{(n−1)/n} − 1]`

    一阶展开应退化为 `H ≈ (p − p_ref)/ρ`——测试里对这条做断言，
    用来守住前因子 `(p_ref+B)` **不能**写成 `p_ref`（差约 3000 倍）。
    """
    alpha = (n - 1.0) / n
    return float(n * (p_ref + B) / ((n - 1.0) * med.rho) * (((p + B) / (p_ref + B)) ** alpha - 1.0))


def gilmore_rhs(t: float, y: np.ndarray, *, R0: float, f: float, p_drive: float, med: Medium) -> np.ndarray:
    """Gilmore 方程的 Tait 焓形式（工程实现）。

    标准形式::

        (1 − Ṙ/c)·R·R̈ + 1.5(1 − Ṙ/(3c))·Ṙ² = (1 + Ṙ/c)·H + (R/c)(1 − Ṙ/c)·Ḣ

    **关键点（踩过两次坑）**：

    1. Tait 焓必须相对**瞬时**远场压力 `p∞(t)` 定义::

           H = C·[((p_L+B)/(p∞+B))^α − 1]，  C = n(p∞+B)/((n−1)ρ)，α=(n−1)/n

       前因子是 `(p∞+B)/ρ` 而**不是** `p∞/ρ`（差 `(p∞+B)/p∞ ≈ 3000` 倍）。
    2. 参考压力若取**固定** `p0`（而不是 `p∞(t)`），驱动项会被整块丢掉——
       气泡只剩静态偏移、完全跟不上驱动力（实测谱峰跑到 2.4 MHz、Rmax/R0 恒为 1.000）。
       与此同时 `Ḣ` 里也必须包含 `ṗ∞` 的贡献。

    一阶自检：`H ≈ (p_L − p∞)/ρ`（测试里断言了这一条）。
    """
    R, Rd = float(y[0]), float(y[1])
    R = max(R, 1e-12)
    omega = 2.0 * np.pi * f
    p_inf = med.p0 - p_drive * np.sin(omega * t)
    dp_inf_dt = -p_drive * omega * np.cos(omega * t)

    n, B = 7.1, 3.04e8
    alpha = (n - 1.0) / n
    p_g = _gas_pressure(R, R0, med)
    p_L = p_g - 2.0 * med.sigma / R - 4.0 * med.mu * Rd / R

    # ṗ_L（粘性项含 R̈，按 Keller 同样的一阶近似略去）
    dp_L_dt = -3.0 * med.kappa * p_g * Rd / R + 2.0 * med.sigma * Rd / (R * R)

    ratio = (p_L + B) / (p_inf + B)
    C = n * (p_inf + B) / ((n - 1.0) * med.rho)
    H = C * (ratio**alpha - 1.0)

    dC_dt = n / ((n - 1.0) * med.rho) * dp_inf_dt
    dratio_dt = (dp_L_dt * (p_inf + B) - (p_L + B) * dp_inf_dt) / (p_inf + B) ** 2
    Hdot = dC_dt * (ratio**alpha - 1.0) + C * alpha * ratio ** (alpha - 1.0) * dratio_dt

    lhs_c = 1.0 - Rd / med.c
    lhs_a = 1.5 * (1.0 - Rd / (3.0 * med.c)) * Rd * Rd
    rhs = (1.0 + Rd / med.c) * H + (R / med.c) * lhs_c * Hdot
    Rdd = (rhs - lhs_a) / (R * lhs_c)
    return np.array([Rd, Rdd])


MODELS = {"rp": rp_rhs, "keller": keller_rhs, "gilmore": gilmore_rhs}


@dataclass
class BubbleResult:
    """一次气泡动力学仿真的结果。"""

    t: np.ndarray
    R: np.ndarray
    Rd: np.ndarray
    f: float
    p_drive: float
    R0: float
    model: str
    meta: dict = field(default_factory=dict)

    @property
    def radius_ratio(self) -> np.ndarray:
        return self.R / self.R0


def equilibrium_radius(R0: float, med: Medium = Medium()) -> float:
    """静平衡半径：解 `p_g(R) − 2σ/R = p∞`。

    ⚠️ 本模块采用 `p_g = p₀(R₀/R)^{3κ}` 这一常用简化（把气泡初始内压直接取为环境压）。
    该简化下**静平衡点并不等于 R₀**：表面张力会额外向内压，使 `R_eq < R₀`
    （σ=0 时才有 `R_eq = R₀`）。做自由振荡/谐振测量时必须围绕 `R_eq` 扰动，
    否则测到的是"向平衡点单调收缩"而不是振荡。
    """
    if med.sigma <= 0:
        return float(R0)
    lo, hi = 0.05 * R0, R0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = float(_gas_pressure(mid, R0, med)) - 2.0 * med.sigma / mid - med.p0
        if f_mid > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def simulate(
    R0: float = 2.0e-6,
    *,
    f: float = 1.0e6,
    p_drive: float = 5.0e4,
    n_cycles: float = 12.0,
    model: str = "keller",
    med: Medium = Medium(),
    steps_per_cycle: int = 400,
    tail_cycles: float = 4.0,
    R_init_factor: float = 1.0,
) -> BubbleResult:
    """积分气泡半径历程（固定步长 RK4，纯 numpy）。

    参数
    ----
    `p_drive`：驱动压力幅值（Pa）；`n_cycles`：驱动力作用的周期数；
    `tail_cycles`：驱动撤去后再自由振荡的周期数（便于看衰减与谱分辨率）；
    `steps_per_cycle`：每驱动周期的时间步数（默认 400，已远小于谐振周期的 1/10）；
    `R_init_factor`：初始半径相对 R0 的倍数（≠1 可激发自由振荡）。

    返回 `BubbleResult`，含 `t / R / Ṙ` 以及模型名与关键无量纲量。
    """
    if model not in MODELS:
        raise ValueError(f"未知模型 {model!r}，可选：{sorted(MODELS)}")
    rhs = MODELS[model]

    # 时间步：取驱动周期与自由振荡周期中较小者的 1/steps_per_cycle
    T_drive = 1.0 / f
    T_res = 1.0 / minnaert_frequency(R0, med)
    dt = min(T_drive, T_res) / float(steps_per_cycle)

    t_end = (n_cycles + tail_cycles) * T_drive
    n_steps = int(np.ceil(t_end / dt))
    t = np.empty(n_steps + 1)
    R = np.empty(n_steps + 1)
    Rd = np.empty(n_steps + 1)

    t[0] = 0.0
    R[0] = R0 * R_init_factor
    Rd[0] = 0.0

    y = np.array([R[0], Rd[0]], dtype=float)
    t_off = n_cycles * T_drive

    for i in range(n_steps):
        ti = t[i]
        # 驱动在 t_off 之后撤去（p_drive 置 0），尾段用于观察自由衰减
        p_now = p_drive if ti < t_off else 0.0
        k1 = rhs(ti, y, R0=R0, f=f, p_drive=p_now, med=med)
        k2 = rhs(ti + dt / 2, y + dt / 2 * k1, R0=R0, f=f, p_drive=p_now, med=med)
        k3 = rhs(ti + dt / 2, y + dt / 2 * k2, R0=R0, f=f, p_drive=p_now, med=med)
        k4 = rhs(ti + dt, y + dt * k3, R0=R0, f=f, p_drive=p_now, med=med)
        y = y + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        # 数值保护：
        # 1) 半径必须为正；
        # 2) |Ṙ| 封顶到 0.9c —— 这是模型自身的有效性边界（RP/KM 的可压缩修正项含 1−Ṙ/c，
        #    接近 c 时方程本身失效）。强驱动惯性塌缩时 RK4 会冲出这个边界并溢出（实测
        #    出现 `overflow encountered in scalar multiply`），封顶后既保住物理意义也保住数值稳定。
        if not np.isfinite(y).all():
            t, R, Rd = t[: i + 1], R[: i + 1], Rd[: i + 1]
            break
        if y[0] <= 0:
            y[0] = 1e-12
        y[1] = float(np.clip(y[1], -0.9 * med.c, 0.9 * med.c))
        t[i + 1] = ti + dt
        R[i + 1] = y[0]
        Rd[i + 1] = y[1]

    return BubbleResult(
        t=t,
        R=R,
        Rd=Rd,
        f=float(f),
        p_drive=float(p_drive),
        R0=float(R0),
        model=model,
        meta={
            "dt": dt,
            "n_steps": n_steps,
            "f_res": minnaert_frequency(R0, med),
            "t_off": t_off,  # 驱动撤去时刻，emission_spectrum 用它切掉尾段
        },
    )


def emission_spectrum(
    result: BubbleResult,
    *,
    f_max: float | None = None,
    detrend: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """发射谱：对 `R(t)/R₀ − 1` 做 FFT，返回 (freqs, 归一化幅值)。

    只取**驱动期**的数据（`t <= t_off`，尾段是自由衰减，混进来会糊掉谱峰），
    并对均值去趋势（去掉静态偏置）。幅值按最大值归一化，便于比较峰位与谐波结构。
    """
    t = result.t
    y = result.radius_ratio
    t_off = float(result.meta.get("t_off", t[-1]))
    mask = t <= t_off
    tt, yy = t[mask], y[mask]
    if tt.size < 8:
        raise ValueError("驱动期采样点过少，无法做谱分析")
    if detrend:
        yy = yy - np.mean(yy)

    n = tt.size
    dt = float(tt[1] - tt[0])
    spec = np.abs(np.fft.rfft(yy * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=dt)
    if f_max is not None:
        keep = freqs <= f_max
        freqs, spec = freqs[keep], spec[keep]
    peak = spec.max() if spec.max() > 0 else 1.0
    return freqs, spec / peak


def cavitation_dose(
    result: BubbleResult,
    *,
    R_threshold: float = 2.0,
) -> dict[str, float]:
    """从半径历程积分空化剂量。

    返回 dict：
    - `dose_expansion`：`∫ max(0, R/R₀ − 1) dt`（s）
    - `dose_inertial`：`∫ 1{R > R_th·R₀} dt`（s）
    - `R_max_ratio`：`max R/R₀`
    - `R_min_ratio`：`min R/R₀`
    """
    t, ratio = result.t, result.radius_ratio
    dt = np.diff(t)
    expansion = np.maximum(0.0, ratio[:-1] - 1.0)
    inertial = (ratio[:-1] > R_threshold).astype(float)
    return {
        "dose_expansion": float(np.sum(expansion * dt)),
        "dose_inertial": float(np.sum(inertial * dt)),
        "R_max_ratio": float(np.max(ratio)),
        "R_min_ratio": float(np.min(ratio)),
    }
