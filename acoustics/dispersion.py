"""板波频散：对称（S）模态族的 Rayleigh–Lamb 求解（工单 266 · P1-2）。

用途
----
衰减谱（P0-1）回答"有多少散射体"，**频散曲线**回答"介质/结构本身的弹性参数"——
两者互补，可交叉验证材料状态（壁厚、模量、含气量）。这是轮48 P1 `PyDispersion` 的落点。

本模块只做对称（S）模态族
-------------------------
**A0 未实现**，原因写在 `lamb_symmetric_residual` 的注释与 §A0 说明里：
`c_ph < c_T` 时 `p`、`q` **同时为虚数**，`sin/cos` 变成 `sinh/cosh`，
数值上迅速溢出；正确做法是改用双曲形式的方程组（`tanh(qh)/tanh(ph)` 形式）并单独分支跟踪。
实测：用复开方硬算在该区域 Newton 收敛率 **0/60**（全部失败）。
⇒ 与其糊一个"看起来有数"的假曲线，不如**明确不做**。

方程
----
板半厚 `h`、`ω = 2πf`、`k = ω/c_ph`：

    p² = ω²/c_L² − k²,   q² = ω²/c_T² − k²

    对称(S): (k²−q²)²·sin(qh)·cos(ph) + 4k²pq·cos(qh)·sin(ph) = 0

**`p` 在 `c_ph < c_L` 时为纯虚数**，所以 `p` 必须按**复数**开方后代入，再取行列式实部。
（踩过的坑：早先用 `sqrt(max(p²,0))` 把虚部强行压成 0，残差在整个区间恒为 ±1、找不到任何根。）

求根现状（**重要，别高估本模块**）
----------------------------------
- ✅ `lamb_symmetric_residual`：残差函数（**复数开方**，三个区段统一），已用"残差必须随 c_ph 变化"守住；
- ✅ `solve_symmetric_mode(f, guess=...)`：**单点** Newton 求解（给初值时可靠）；
- ✅ `plate_velocity` / `cutoff_frequencies`：解析锚点；
- ❌ `s0_curve`（**全频段分支跟踪**）：**未实现**，调用即 raise。
  原因：S1 的相速度从 `>c_L` 降向 `c_T`，中途与 S0 靠拢，"连续性 + 3%" 不足以区分，
  实测会滑到 S1（高频落到 3130≈c_T）。需要模态计数或 (fd, c_ph) 二维延拓。
- ❌ `A0`：`c_ph<c_T` 需双曲形式，同样未实现。

⚠️ 早先的错误做法（两次，都记在这里）：① 用 `sqrt(max(p²,0))` 把虚部压成 0 ⇒ 残差恒为 ±1、一个根都找不到；
② 用等距全局扫描找变号 ⇒ 振荡混叠出假根（A0 恒等于扫描下界）。

解析锚点（测试用）
------------------
- `S0` 低频极限 = 板波速 `c_p = 2c_T√(1 − c_T²/c_L²)`
- `S0` 高频极限 → `c_L`（实测 5 MHz 时 6290 / 6300）
- 截止频率：`k→0` 时 `sin(qh)=0` ⇒ `f_n = n·c_T/(2h)`
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "Plate",
    "ALUMINUM",
    "STEEL",
    "lamb_symmetric_residual",
    "solve_symmetric_mode",
    "s0_curve",
    "a0_curve",
    "cutoff_frequencies",
    "plate_velocity",
    "A0_NOT_IMPLEMENTED_REASON",
]

A0_NOT_IMPLEMENTED_REASON = (
    "【已解决 · WO-277 第 3 批】A0 原先未实现：c_ph<c_T 时 p、q 同时为纯虚数，sin/cos 退化为 "
    "sinh/cosh 并迅速溢出，需改用双曲形式。现已在 acoustics/dispersion_branches.py 用三区段"
    "实数式（tanh 恒等变形）实现，本模块的 a0_curve 直接委托过去。此常量仅留作历史说明。"
)


@dataclass(frozen=True)
class Plate:
    """各向同性板：纵/横波速、密度、厚度（`thickness = 2h`）。"""

    c_L: float  # noqa: N815 —— 物理标准记号（纵波 c_L / 横波 c_T），改名反而脱离文献
    c_T: float  # noqa: N815
    rho: float
    thickness: float

    @property
    def h(self) -> float:
        return self.thickness / 2.0

    @property
    def c_plate(self) -> float:
        """板波（extensional）速度，S0 的低频极限。"""
        return float(2.0 * self.c_T * np.sqrt(max(0.0, 1.0 - (self.c_T / self.c_L) ** 2)))


ALUMINUM = Plate(c_L=6300.0, c_T=3100.0, rho=2700.0, thickness=5.0e-3)
STEEL = Plate(c_L=5900.0, c_T=3200.0, rho=7850.0, thickness=5.0e-3)


def lamb_symmetric_residual(c_ph: float, f: float, plate: Plate) -> float:
    """对称模态行列式残差（按 `(k²+|q|²)²` 缩放，保号且量级平稳）。

    ⚠️ **必须用复数开方**：`c_ph < c_L` 时 `p² < 0`。
    把它当实数硬取 0 会让残差退化成常数（实测整段回到 ±1，一个根都找不到）。
    """
    omega = 2.0 * np.pi * f
    k = omega / c_ph

    p = np.sqrt(complex((omega / plate.c_L) ** 2 - k**2, 0.0))
    q = np.sqrt(complex((omega / plate.c_T) ** 2 - k**2, 0.0))
    # 固定分支：虚部取非负（否则 sin/cos 的符号会随分支翻转）
    if p.imag < 0:
        p = -p
    if q.imag < 0:
        q = -q

    h = plate.h
    a = (k**2 - q**2) ** 2 * np.sin(q * h) * np.cos(p * h)
    b = 4.0 * k**2 * p * q * np.cos(q * h) * np.sin(p * h)
    scale = (k**2 + abs(q) ** 2) ** 2
    return float(np.real(a + b) / scale)


def _newton_symmetric(
    c0: float,
    f: float,
    plate: Plate,
    *,
    iters: int = 80,
    tol: float = 1e-12,
) -> float | None:
    """Newton 抛光（数值导数）。失败返回 None。"""
    c = float(c0)
    if c <= 0:
        return None
    lo, hi = plate.c_T * 1.0001, plate.c_L * 0.9999  # S 模态物理上只能落在这个区间
    for _ in range(iters):
        d = lamb_symmetric_residual(c, f, plate)
        dc = max(c * 1e-7, 1e-4)
        der = (lamb_symmetric_residual(c + dc, f, plate) - lamb_symmetric_residual(c - dc, f, plate)) / (2.0 * dc)
        if der == 0 or not np.isfinite(der):
            return None
        step = -d / der
        # ⚠️ **步长夹紧**：不加这段时 Newton 会跳到相邻模态（实测出现 6345、6539 > c_L
        # 和 4468 的低值），分支跟踪随即整体跑偏。
        step = float(np.clip(step, -0.05 * c, 0.05 * c))
        c_new = c + step
        if not np.isfinite(c_new) or not (lo < c_new < hi):
            c_new = 0.5 * (c + np.clip(c_new, lo, hi)) if np.isfinite(c_new) else 0.5 * c
        if abs(c_new - c) < tol * max(c, 1e-6):
            if lo < c_new < hi and abs(lamb_symmetric_residual(c_new, f, plate)) < 1e-7:
                return c_new
            return None
        c = c_new
    if lo < c < hi and abs(lamb_symmetric_residual(c, f, plate)) < 1e-7:
        return c
    return None


def solve_symmetric_mode(
    f: float,
    plate: Plate = ALUMINUM,
    *,
    guess: float | None = None,
) -> float | None:
    """在固定 `f` 上解对称模态的一个根（默认从 S0 的解析极限起步）。"""
    c0 = plate.c_plate if guess is None else float(guess)
    return _newton_symmetric(c0, f, plate)


def s0_curve(freqs, plate: Plate = ALUMINUM):
    """S0 分支（**委托** `acoustics.dispersion_branches.s0_curve`，WO-277 第 3 批收口）。

    历史：本函数曾长期 `raise NotImplementedError`——「Newton + 连续性跟踪」试了 7 种
    做法全部失败（详见 `docs/P1-2-频散求根-施工备忘-2026-10-22.md`）。
    真正的解法是**根数对账 + `S0 = 对称族最小根`**，实现落在 `dispersion_branches`；
    这里只做委托，让旧调用点照旧可用。

    实测锚点：10 kHz→5397（=`c_plate`）、1 MHz→2932、2 MHz→2895、5 MHz→2894（≈`c_R`）。
    注意 **S0 的高频极限是 `c_R` 不是 `c_L`**（早期误判导致把 L 支当成 S0）。
    """
    from acoustics.dispersion_branches import s0_curve as _impl  # 延迟导入，避免循环

    return _impl(freqs, plate)


def a0_curve(freqs, plate: Plate = ALUMINUM):
    """A0 分支（**委托** `acoustics.dispersion_branches.a0_curve`）。

    用**反对称方程**独立求解，不是"在对称族根里挑第二小"：
    两族在高频几乎重合（5 MHz 都 ≈2894），**只能靠族别区分**。
    """
    from acoustics.dispersion_branches import a0_curve as _impl  # 延迟导入，避免循环

    return _impl(freqs, plate)


def cutoff_frequencies(plate: Plate, mode: str = "S", n_max: int = 5) -> list[float]:
    """对称模态截止频率（解析）：`f_n = n·c_T/(2h)`，`n = 1, 2, …`（S0 无截止）。"""
    if not mode.lower().startswith("s"):
        raise ValueError("本模块只实现对称(S)模态的截止频率")
    return [n * plate.c_T / (2.0 * plate.h) for n in range(1, n_max + 1)]


def plate_velocity(plate: Plate = ALUMINUM) -> float:
    """板波速度（S0 低频极限）。"""
    return plate.c_plate
