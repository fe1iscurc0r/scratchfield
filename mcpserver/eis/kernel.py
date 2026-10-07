"""可换核谱反卷积内核抽象（EIS / DLS / SDR 三域共用的数学骨架）。

设计动机（工单202 任务一）：
    电化学阻抗谱（EIS）的 DRT 反演、动态光散射（DLS）的粒度反演、SDR 频谱提纯，
    本质是**同一类病态逆问题**——离散化后都是一个线性系统 ``A g = b``，
    A 的条件数极大，必须靠正则化/先验把解收敛到物理可解释的形态：

        DLS:  b = 衰减率分布卷积核     A(τ, D)   → 粒径分布 g(D)
        DRT:  b = 阻抗实/虚部          A(ω, τ)   → 松弛时间分布 γ(τ)
        SDR:  b = 观测频谱            A(f, f')  → 提纯谱 g(f')

    所以把「逆问题求解」抽成可替换的内核：数据侧（EIS/DLS/SDR）只负责构造 A 与 b，
    求解策略（Tikhonov / 层级贝叶斯 / 未来新增的任何核）走统一 Protocol。

换核位：``register_kernel`` / ``get_kernel`` / ``list_kernels``。
内置核：
    - ``tikhonov``            ：L 曲线式固定正则 + 非负最小二乘（DLS 粒度反演同款）
    - ``hierarchical_bayes``  ：二阶平滑先验 + 证据近似的自适应正则（bayes-drt 风格）

边界（说清不含糊）：
    - 内置核是**自包含 numpy/scipy 实现**，不依赖外部包即可跑；
      若环境装了 ``impedance``（ECSHackWeek/impedance.py），``linkk`` 工具会优先用它的
      Lin-KK 实现做交叉验证，并在返回里标明 ``method``。
    - 本模块只管「已知 A、b 求 g」；A/b 的构造属于各域工具（见 tools.py）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np


@dataclass
class InversionResult:
    """一次谱反卷积的统一返回（跨域字段尽量求同）。"""

    x: np.ndarray                      # 反演轴（τ / D / f 网格）
    y: np.ndarray                      # 分布强度 γ(τ) / g(D) / 谱
    residual: float                    # 相对残差 ||A y - b|| / ||b||
    method: str                        # 实际使用的核名
    hyperparams: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def peaks(self, rel_height: float = 0.05) -> list[dict[str, float]]:
        """局部极大值（相对最高峰高度的 rel_height 以上），按高度降序。

        用于「峰位=特征时间常数」这类判读，DLS 域同一实现可直接复用。
        """
        y = np.asarray(self.y, dtype=float)
        x = np.asarray(self.x, dtype=float)
        if y.size == 0 or not np.any(y > 0):
            return []
        thr = float(y.max()) * float(rel_height)
        out: list[dict[str, float]] = []
        for i in range(1, y.size - 1):
            if y[i] >= y[i - 1] and y[i] > y[i + 1] and y[i] >= thr:
                out.append({"x": float(x[i]), "height": float(y[i])})
        out.sort(key=lambda p: p["height"], reverse=True)
        return out


@runtime_checkable
class SpectrumInversionKernel(Protocol):
    """谱反卷积内核契约——新核只要满足它就能被 DRT/DLS/SDR 复用。

    ``solve`` 的最小契约：
        入参 ``matrix`` (m×n) 与 ``data`` (m,) 是已离散化的逆问题；``hyperparams``
        是该核自己的超参（不认识的键必须忽略，不得抛错，保证换核不破坏调用方）。
        返回必须含 ``x``/``y``/``residual``；``x`` 由调用方在 result 上覆写成
        物理轴更友好（核只关心索引顺序）。
    """

    name: str

    def solve(self, matrix: np.ndarray, data: np.ndarray,
              **hyperparams: Any) -> InversionResult:  # pragma: no cover - 协议声明
        ...


# ---------------------------------------------------------------------------
# 内置核 1：Tikhonov 正则 + 非负约束（固定/自适应 λ）
# ---------------------------------------------------------------------------

class TikhonovKernel:
    """经典 Tikhonov：min ||A y - b||² + λ ||L y||²，y ≥ 0。

    λ 缺省走「自适应」档：在候选网格上取解最平滑且残差仍在可接受区间者
    （L 曲线思想的轻量版，避免引入完整 L 曲线实现）。
    与 DLS 里流行的 CONTIN/DLS 粒度反演同属「病态逆 + 正则化」骨架。
    """

    name = "tikhonov"

    def __init__(self, order: int = 2, lam: float | None = None) -> None:
        self.order = int(order)
        self.lam = lam

    def solve(self, matrix: np.ndarray, data: np.ndarray,
              **hyperparams: Any) -> InversionResult:
        from scipy.optimize import lsq_linear

        lam = hyperparams.get("lam", self.lam)
        order = int(hyperparams.get("order", self.order))
        A = np.asarray(matrix, dtype=float)
        b = np.asarray(data, dtype=float)
        n = A.shape[1]
        L = _difference_operator(n, order)

        if lam is None or float(lam) <= 0:
            lam = self._auto_lambda(A, b, L)
        lam = max(float(lam), 1e-12)

        # 堆叠正则行，非负盒约束求解（等价于 NNLS + Tikhonov）
        A_aug = np.vstack([A, np.sqrt(lam) * L])
        b_aug = np.concatenate([b, np.zeros(L.shape[0])])
        sol = lsq_linear(A_aug, b_aug, bounds=(0.0, np.inf),
                         lsmr_tol="auto", max_iter=200)
        y = np.asarray(sol.x, dtype=float)
        res = _rel_residual(A, y, b)
        return InversionResult(
            x=np.arange(n, dtype=float), y=y, residual=res, method=self.name,
            hyperparams={"lam": lam, "order": order},
        )

    @staticmethod
    def _auto_lambda(A: np.ndarray, b: np.ndarray, L: np.ndarray) -> float:
        """在 log 网格上挑一个「残差可接受 + 解最平滑」的 λ（轻量 L 曲线）。"""
        from scipy.optimize import lsq_linear

        scale = float(np.linalg.norm(A, ord=2)) or 1.0
        for lam in (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0):
            A_aug = np.vstack([A, np.sqrt(lam * scale) * L])
            b_aug = np.concatenate([b, np.zeros(L.shape[0])])
            y = lsq_linear(A_aug, b_aug, bounds=(0.0, np.inf),
                           lsmr_tol="auto", max_iter=200).x
            if _rel_residual(A, y, b) <= 0.05:   # 残差达标即停（宁平滑勿过拟合）
                return lam * scale
        return 1.0 * scale


# ---------------------------------------------------------------------------
# 内置核 2：层级贝叶斯（平滑先验 + 证据近似自适应正则）
# ---------------------------------------------------------------------------

class HierarchicalBayesKernel:
    """层级贝叶斯风格反演——二阶平滑先验 + **证据近似的自适应正则**。

    实现口径（说清边界）：这是「证据近似选择超参」的可运行实现（GCV 选择 λ，
    即 MacKay 证据框架下的解析近似），**不是**完整 bayes-drt 的后验采样；
    换核位（``register_kernel``）随时可挂真 bayes-drt / MCMC 版本，接口不变。

    模型：y ~ N(0, (σ²/λ)(LᵀL)⁻¹) 平滑先验；λ 由 GCV 在 log 网格上选出
    （等价于让先验强度随有效自由度自调），再做非负约束求解。
    与 SDR 频谱提纯、LLA-MPC 置信度截断共享「先验强度按证据自调」的思想。
    """

    name = "hierarchical_bayes"

    def __init__(self, order: int = 2, max_iter: int = 60, tol: float = 1e-6) -> None:
        self.order = int(order)
        self.max_iter = int(max_iter)      # 保留在签名里（换核调用方可能传）
        self.tol = float(tol)

    def solve(self, matrix: np.ndarray, data: np.ndarray,
              **hyperparams: Any) -> InversionResult:
        from scipy.optimize import lsq_linear

        A = np.asarray(matrix, dtype=float)
        b = np.asarray(data, dtype=float)
        n, m = A.shape[1], A.shape[0]
        order = int(hyperparams.get("order", self.order))
        L = _difference_operator(n, order)
        AtA, Atb, LTL = A.T @ A, A.T @ b, L.T @ L
        eye = np.eye(n)

        # 证据近似：扫 λ，取 GCV 最小者（解析可算，无需迭代发散风险）
        best_gcv, best_lam, best_y = None, 1e-6, np.zeros(n)
        for lam in np.logspace(-12, 2, 71):
            H = AtA + lam * LTL
            try:
                Hinv = np.linalg.inv(H + 1e-12 * eye)
            except np.linalg.LinAlgError:
                continue
            y_lin = Hinv @ Atb
            eff = float(np.trace(Hinv @ AtA))                 # 有效参数数
            rss = float(np.sum((A @ y_lin - b) ** 2))
            denom = max(1.0 - eff / m, 1e-6)
            gcv = rss / (m * denom ** 2)
            if best_gcv is None or gcv < best_gcv:
                best_gcv, best_lam, best_y = gcv, lam, y_lin

        lam = float(best_lam)
        A_aug = np.vstack([A, np.sqrt(lam) * L])
        b_aug = np.concatenate([b, np.zeros(L.shape[0])])
        sol = lsq_linear(A_aug, b_aug, bounds=(0.0, np.inf),
                         lsmr_tol="auto", max_iter=300)
        y = np.asarray(sol.x, dtype=float)
        return InversionResult(
            x=np.arange(n, dtype=float), y=y,
            residual=_rel_residual(A, y, b), method=self.name,
            hyperparams={"lam": lam, "gcv": float(best_gcv or 0.0), "order": order},
            extras={"prior": "second_order_smoothness",
                    "selection": "gcv(evidence-approx)"},
        )


# ---------------------------------------------------------------------------
# 注册表（换核位）
# ---------------------------------------------------------------------------

_KERNELS: dict[str, Callable[[], SpectrumInversionKernel]] = {
    TikhonovKernel.name: TikhonovKernel,
    HierarchicalBayesKernel.name: HierarchicalBayesKernel,
}

DEFAULT_KERNEL = TikhonovKernel.name


def register_kernel(name: str, factory: Callable[[], SpectrumInversionKernel]
                    ) -> None:
    """注册（或覆盖）一个内核。``factory`` 须零参可调用并返回内核实例。

    EIS/DLS/SDR 三域的数据侧共用此入口——换核不动调用方。
    """
    key = str(name or "").strip()
    if not key:
        raise ValueError("kernel name 不能为空")
    if not callable(factory):
        raise TypeError("factory 必须可调用")
    _KERNELS[key] = factory


def unregister_kernel(name: str) -> bool:
    """移除注册的核（内置核也可被移除/覆盖；返回是否存在）。"""
    return _KERNELS.pop(str(name), None) is not None


def list_kernels() -> list[str]:
    """当前可用核名（含内置与外部注册）。"""
    return sorted(_KERNELS)


def get_kernel(name: str | None = None) -> SpectrumInversionKernel:
    """取内核实例；名字未知时抛 KeyError（附可用清单，不静默降级）。"""
    key = str(name or DEFAULT_KERNEL)
    if key not in _KERNELS:
        raise KeyError(f"unknown_kernel: {key}（可用：{list_kernels()}）")
    return _KERNELS[key]()


def invert(matrix: np.ndarray, data: np.ndarray, kernel: str | None = None,
           **hyperparams: Any) -> InversionResult:
    """统一入口：选核 → 求解（换核只需改 ``kernel`` 参数）。"""
    return get_kernel(kernel).solve(matrix, data, **hyperparams)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _difference_operator(n: int, order: int) -> np.ndarray:
    """一阶/二阶差分算子 L（用于平滑先验）；n 很小时退化为单位阵。"""
    if n <= 1:
        return np.eye(max(n, 1))
    if order <= 1:
        return np.diff(np.eye(n), n=1, axis=0)
    if n <= 2:
        return np.diff(np.eye(n), n=1, axis=0)
    return np.diff(np.eye(n), n=2, axis=0)


def _rel_residual(A: np.ndarray, y: np.ndarray, b: np.ndarray) -> float:
    den = float(np.linalg.norm(b)) or 1.0
    return float(np.linalg.norm(A @ y - b) / den)
