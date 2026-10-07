"""EIS 三工具实现：linkk（KK 合法性）/ drt（DRT 反演）/ ecm（等效电路拟合）。

数学骨架（与 kernel.py 的换核抽象对接）：
    Z(ω) = R∞ + ∫ γ(lnτ) / (1 + jωτ) d lnτ
    离散化后 A(ω, τ) 的实/虚部核：
        实部核  1 / (1 + (ωτ)²)
        虚部核  -ωτ / (1 + (ωτ)²)        （电化学惯例：Z'' 为负）
    ``linkk`` 用同一套 A 做「RK 近似 vs 实测」残差（Lin-KK 思想）；
    ``drt`` 用同一套 A 反演 γ（走入 kernel 换核）；
    ``ecm`` 是参数化路径（R0 + Σ R||CPE），不走离散 A。

依赖口径（工单202 任务一）：
    - 底座 ECSHackWeek/impedance.py（MIT）——**可用则优先**（Lin-KK 交叉验证）；
    - 缺失时自包含路径照跑，返回里标明 ``degraded`` 与原因，不静默降级；
    - AutoEIS 不引入（792MB，整包过重）。
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from . import kernel as _kernel

# 数据符号约定：'negative' = 电化学惯例（-Z'' 为正画 Nyquist）；'positive' = 物理惯例
IMAG_NEGATIVE = "negative"
IMAG_POSITIVE = "positive"


# ---------------------------------------------------------------------------
# 公共：数据 / 网格 / A 矩阵
# ---------------------------------------------------------------------------

def _as_arrays(freqs: Iterable[float], z_real: Iterable[float],
               z_imag: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    f = np.asarray(list(freqs), dtype=float)
    zr = np.asarray(list(z_real), dtype=float)
    zi = np.asarray(list(z_imag), dtype=float)
    if f.size == 0 or zr.size != f.size or zi.size != f.size:
        raise ValueError("freqs / z_real / z_imag 长度必须一致且非空")
    order = np.argsort(f)                      # 统一按频率升序处理
    return f[order], zr[order], zi[order]


def _detect_imag_convention(z_imag: np.ndarray) -> str:
    """探测虚部符号约定（EIS 数据两种流派都有，明确标注比猜更负责）。"""
    nonzero = z_imag[np.abs(z_imag) > 1e-15]
    if nonzero.size == 0:
        return IMAG_NEGATIVE
    return IMAG_NEGATIVE if float(np.median(nonzero)) < 0 else IMAG_POSITIVE


def _tau_grid(tau_min: float, tau_max: float, n: int) -> np.ndarray:
    return np.logspace(math.log10(tau_min), math.log10(tau_max), int(n))


def _design_matrix(freqs: np.ndarray, tau: np.ndarray,
                   imag_convention: str) -> np.ndarray:
    """构造 A（2N × (M+1)）：上行实部核、下行虚部核，含 dlnτ 权重。

    最后一列是 R∞（高频截距的纯电阻项）：实部恒 1、虚部恒 0。
    缺这一列会让含纯电阻的谱无法被拟合（KK 一致的数据也会判 fail）。
    """
    omega = 2.0 * np.pi * freqs
    wt = omega[:, None] * tau[None, :]          # (N, M)
    denom = 1.0 + wt ** 2
    real_k = 1.0 / denom
    imag_k = -wt / denom
    if imag_convention == IMAG_POSITIVE:
        imag_k = -imag_k
    dln = math.log(tau[1] / tau[0]) if tau.size > 1 else 1.0
    n, m = freqs.size, tau.size
    A = np.zeros((2 * n, m + 1), dtype=float)
    A[:n, :m] = real_k * dln
    A[:n, m] = 1.0                               # R∞ 实部
    A[n:, :m] = imag_k * dln
    return A


def _stack_data(z_real: np.ndarray, z_imag: np.ndarray) -> np.ndarray:
    return np.concatenate([z_real, z_imag])


def _auto_tau_range(freqs: np.ndarray, factor: float = 10.0
                    ) -> tuple[float, float]:
    """τ 网格范围：覆盖频率窗口两端各扩 factor 倍（反演外推留边）。"""
    omega = 2.0 * np.pi * np.asarray(freqs, dtype=float)
    fmax, fmin = float(omega.max()), float(omega.min())
    return factor / fmax, factor / fmin


# ---------------------------------------------------------------------------
# 工具 1：linkk —— Kramers-Kronig 合法性验证
# ---------------------------------------------------------------------------

def linkk(freqs: Iterable[float], z_real: Iterable[float],
          z_imag: Iterable[float], *, n_tau: int = 40,
          threshold: float = 0.01, use_impedance_lib: bool = True
          ) -> dict[str, Any]:
    """Lin-KK 风格合法性检验：数据能否被正实（RC 网络）函数良好逼近。

    判据：相对残差 ≤ ``threshold``（默认 1%）→ 判定 pass。
    含义：KK 一致的数据是「线性、因果、稳定」的，pass 表示可直接做后续反演；
    显著不通过通常意味着漂移/非线性/接线故障，先修数据再做 DRT。
    """
    f, zr, zi = _as_arrays(freqs, z_real, z_imag)
    conv = _detect_imag_convention(zi)
    lo, hi = _auto_tau_range(f)
    tau = _tau_grid(lo, hi, n_tau)
    A = _design_matrix(f, tau, conv)
    b = _stack_data(zr, zi)

    # 自包含路径：轻正则 + 非负（RK 近似的线性最小二乘）
    result = _kernel.invert(A, b, kernel="tikhonov", lam=1e-6)
    residual = float(result.residual)

    out: dict[str, Any] = {
        "status": "ok",
        "method": "lin-kk(self-contained)",
        "imag_convention": conv,
        "residual": residual,
        "residual_pct": round(residual * 100.0, 4),
        "threshold": threshold,
        "verdict": "pass" if residual <= threshold else "fail",
        "n_points": int(f.size),
        "n_tau": int(n_tau),
    }

    # 交叉验证：装了 impedance.py 就用它的 linKK 再算一遍（不覆盖自包含结论）
    imp_lib = _try_impedance_lib() if use_impedance_lib else None
    if imp_lib is None:
        out["degraded"] = "impedance_lib_absent: 未安装 impedance.py，仅自包含路径（已标注）"
    else:
        try:
            from impedance.validation import linKK as _linKK

            z = zr + 1j * zi
            m, mu, _ = _linKK(f, z, c=0.85, max_M=100, fit_type="real",
                              add_capacitance=True)
            out["cross_check"] = {
                "method": "impedance.validation.linKK",
                "mu": [round(float(v), 6) for v in np.asarray(mu, dtype=float)],
                "residuals": [round(float(v), 6) for v in np.asarray(m, dtype=float)],
            }
        except Exception as exc:  # 交叉验证失败不影响主结论，但要说清
            out["cross_check"] = {"method": "impedance.validation.linKK",
                                  "error": f"{type(exc).__name__}: {exc}"}
    return out


# ---------------------------------------------------------------------------
# 工具 2：drt —— Distribution of Relaxation Times 反演
# ---------------------------------------------------------------------------

def drt(freqs: Iterable[float], z_real: Iterable[float],
        z_imag: Iterable[float], *, n_tau: int = 60, kernel: str | None = None,
        lam: float | None = None, peak_rel_height: float = 0.05
        ) -> dict[str, Any]:
    """DRT 反演：由阻抗谱求松弛时间分布 γ(τ)。

    ``kernel`` 走换核位（默认 tikhonov；可换 hierarchical_bayes 或外部注册核）；
    返回 τ 网格、γ、峰位与残差——峰位即特征时间常数（与 DLS 粒度峰同构判读）。
    """
    f, zr, zi = _as_arrays(freqs, z_real, z_imag)
    conv = _detect_imag_convention(zi)
    lo, hi = _auto_tau_range(f)
    tau = _tau_grid(lo, hi, n_tau)
    A = _design_matrix(f, tau, conv)
    b = _stack_data(zr, zi)

    hypers: dict[str, Any] = {}
    if lam is not None:
        hypers["lam"] = lam
    result = _kernel.invert(A, b, kernel=kernel, **hypers)

    # A 的最后一列是 R∞，前 M 列才是 γ（τ 轴与之对齐）
    y = np.asarray(result.y, dtype=float)
    m = tau.size
    gamma = y[:m]
    r_inf = float(y[m]) if y.size > m else 0.0
    gamma_only = _kernel.InversionResult(
        x=tau, y=gamma,                       # x 轴必须是物理 τ（不是索引）
        residual=result.residual, method=result.method,
    )
    peaks = gamma_only.peaks(rel_height=peak_rel_height)
    peaks_out = [{"tau": p["x"], "gamma": p["height"],
                  "freq_hz": float(1.0 / (2.0 * np.pi * p["x"])) if p["x"] > 0 else None}
                 for p in peaks]
    return {
        "status": "ok",
        "method": f"drt:{result.method}",
        "kernel": result.method,
        "kernel_available": _kernel.list_kernels(),
        "imag_convention": conv,
        "residual": float(result.residual),
        "R_inf": r_inf,
        "hyperparams": _jsonable(result.hyperparams),
        "tau": [float(v) for v in tau],
        "gamma": [float(v) for v in gamma],
        "peaks": peaks_out,
        "n_tau": int(n_tau),
    }


# ---------------------------------------------------------------------------
# 工具 3：ecm —— 等效电路拟合（R0 + Σ R||CPE）
# ---------------------------------------------------------------------------

def ecm(freqs: Iterable[float], z_real: Iterable[float],
        z_imag: Iterable[float], *, num_elements: int = 2) -> dict[str, Any]:
    """拟合 R0 + Σ_k [R_k || CPE_k] 等效电路（ZARC 串联）。

    Z = R0 + Σ_k R_k / (1 + R_k Q_k (jω)^{n_k})
    返回参数、逐点残差与相对误差；初值由谱形启发式给出（避免发散）。
    """
    f, zr, zi = _as_arrays(freqs, z_real, z_imag)
    conv = _detect_imag_convention(zi)
    z_meas = zr + 1j * zi
    omega = 2.0 * np.pi * f
    k = max(int(num_elements), 1)

    def model(params: np.ndarray) -> np.ndarray:
        r0 = params[0]
        z = np.full_like(omega, r0, dtype=complex)
        for i in range(k):
            rk, qk, nk = params[1 + 3 * i], params[2 + 3 * i], params[3 + 3 * i]
            z = z + rk / (1.0 + rk * qk * (1j * omega) ** nk)
        return z

    # 初值启发式：R0 取高频端实部；元件电阻按实部跨度均分；Q 由中频特征估
    r0_0 = float(np.min(zr))
    span = max(float(np.max(zr)) - r0_0, 1e-6)
    p0 = [r0_0]
    for i in range(k):
        rk0 = span / k
        w_mid = float(np.exp(np.mean(np.log(omega))))
        qk0 = 1.0 / max(rk0 * w_mid, 1e-12)
        p0 += [rk0, qk0, 0.85]
    p0_arr = np.asarray(p0, dtype=float)

    lower = [0.0] + [0.0, 1e-12, 0.3] * k
    upper = [np.inf] + [np.inf, np.inf, 1.0] * k

    try:
        from scipy.optimize import least_squares

        def resid(p: np.ndarray) -> np.ndarray:
            z_mod = model(p)
            # 相对残差（避免高频小阻抗被大阻抗淹没）
            return np.concatenate([(z_mod.real - zr) / (np.abs(z_meas) + 1e-12),
                                   (z_mod.imag - zi) / (np.abs(z_meas) + 1e-12)])

        fit = least_squares(resid, p0_arr, bounds=(lower, upper), max_nfev=20000)
        params = np.asarray(fit.x, dtype=float)
        ok = bool(fit.success)
        rel_err = float(np.linalg.norm(resid(params)) / math.sqrt(2 * omega.size))
    except Exception as exc:  # 不静默降级：返回 error 与原因
        return {"status": "error", "error": f"fit_failed: {type(exc).__name__}: {exc}",
                "imag_convention": conv}

    elements = []
    for i in range(k):
        elements.append({
            "R": float(params[1 + 3 * i]),
            "Q": float(params[2 + 3 * i]),
            "n": float(params[3 + 3 * i]),
            "tau_s": float(params[1 + 3 * i] * params[2 + 3 * i]) ** (1.0 / max(params[3 + 3 * i], 1e-6)),
        })
    z_mod = model(params)
    return {
        "status": "ok" if ok else "warn",
        "method": f"ecm:r0+{k}x(r||cpe)",
        "imag_convention": conv,
        "fit_success": ok,
        "R0": float(params[0]),
        "elements": elements,
        "rel_err": rel_err,
        "z_fit_real": [float(v) for v in z_mod.real],
        "z_fit_imag": [float(v) for v in z_mod.imag],
        "num_elements": k,
    }


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _try_impedance_lib():
    """返回 impedance 模块（未装则 None）——不触发安装，只探测。"""
    try:
        import impedance  # noqa: F401

        return impedance
    except Exception:
        return None


def _jsonable(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (np.floating, np.integer)):
            out[k] = float(v)
        else:
            out[k] = v
    return out
