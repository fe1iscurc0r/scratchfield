"""板波分支跟踪（工单 277 · 第 1 批）。

为什么单独一个模块
------------------
`acoustics/dispersion.py` 里 `s0_curve` 是**故意 raise NotImplementedError** 的，
并且被 `tests/test_dispersion.py` 的两条"未实现断言"锁死。
工单 276 的 P1-2 就卡在这里。为避免"改一处破一片"，分支跟踪单独放本模块：
旧模块保持"残差 + 单点求解 + 解析锚点"，本模块负责**枚举 + 对账 + 分支身份**，
等第 3 批再统一收口（改测试 + 委托）。

地基（2026-10-22 实测校正，此前 7 次失败都源于此）
--------------------------------------------------
1. **S0 的高频极限是 `c_R`（Rayleigh）不是 `c_L`**：
   `ALUMINUM` 下 1 MHz → 2932、2 MHz → 2895、5 MHz → 2894（≈c_R）。
   以前把 1 MHz 的 5532、2 MHz 的 6459 当成 S0，是**认错了支**（那是纵向截止族 L 支）。
2. **截止频率有两族**（`k→0` 时对称方程化为 `q⁴·sin(qh)·cos(ph)=0`）：
   - 剪切族：`f = n·c_T/(2h)`
   - 纵向族：`f = (2m−1)·c_L/(4h)`
3. **根数公式**（实测 1/1/3/6/13 全部吻合）::

       N_S(f) = 1 + ⌊f·2h/c_T⌋ + ⌊(2·f·2h/c_L + 1)/2⌋

   `1` 是 S0（无截止）；两项分别数剪切族与纵向族。
4. **`c_ph → c_T` 是退化解**（两项同时趋零）⇒ 残差恒近 0，是个巨大的吸引盆；
   任何"以残差最小为判据"的求解都会滑进去。

三个区段（`p² = ω²/cL² − k²`、`q² = ω²/cT² − k²`）
--------------------------------------------------
| 区段 | 条件 | 对称(S) | 反对称(A) |
|---|---|---|---|
| ① | `c < c_T` | `(k²+β²)²tanh(βh) − 4k²αβ·tanh(αh)` | `4k²αβ·tanh(βh) − (k²+β²)²tanh(αh)` |
| ② | `c_T < c < c_L` | `(k²−q²)²sin(qh) − 4k²αq·cos(qh)tanh(αh)` | `4k²αq·sin(qh) − (k²−q²)²cos(qh)tanh(αh)` |
| ③ | `c > c_L` | `(k²−q²)²sin(qh)cos(ph) + 4k²pq·cos(qh)sin(ph)` | `4k²pq·sin(qh)cos(ph) + (k²−q²)²cos(qh)sin(ph)` |

①② 已做恒等变形（整体除以 `cosh(αh)` / `cosh(αh)cosh(βh)`），`sinh/cosh` 全化为 `tanh`
⇒ **数值上不会溢出**（直接算 `cosh` 在低频大 `c` 处会爆）。
"""

from __future__ import annotations

import numpy as np

from acoustics.dispersion import ALUMINUM, Plate

__all__ = [
    "lamb_residual",
    "cutoff_families",
    "is_near_cutoff",
    "expected_mode_count",
    "branch_roots",
    "s0_curve",
    "a0_curve",
    "CR_ALUMINUM",
]

# 铝的 Rayleigh 波速（S0/A0 的高频渐近）。由表面波方程数值解给出，用于窗口下界。
CR_ALUMINUM = 2894.0


def lamb_residual(c_ph: float, f: float, plate: Plate = ALUMINUM, *, mode: str = "S") -> float:
    """Rayleigh–Lamb 残差（三区段实数式，已消除溢出）。`mode` 取 `'S'` 或 `'A'`。"""
    omega = 2.0 * np.pi * f
    k = omega / c_ph
    q2 = (omega / plate.c_T) ** 2 - k**2  # q 实 ⇔ c_ph > c_T
    p2 = (omega / plate.c_L) ** 2 - k**2  # p 实 ⇔ c_ph > c_L
    h = plate.h
    sym = mode.upper().startswith("S")

    if q2 >= 0 and p2 >= 0:  # 区段③：两实
        p, q = np.sqrt(p2), np.sqrt(q2)
        a = (k**2 - q**2) ** 2 * np.sin(q * h) * np.cos(p * h)
        b = 4.0 * k**2 * p * q * np.cos(q * h) * np.sin(p * h)
        v = (
            a + b
            if sym
            else (
                4.0 * k**2 * p * q * np.sin(q * h) * np.cos(p * h) + (k**2 - q**2) ** 2 * np.cos(q * h) * np.sin(p * h)
            )
        )
        scale = (k**2 + q**2) ** 2
    elif q2 >= 0 > p2:  # 区段②：q 实、p=iα
        q, al = np.sqrt(q2), np.sqrt(-p2)
        tanh = np.tanh(al * h)
        if sym:
            v = (k**2 - q**2) ** 2 * np.sin(q * h) - 4.0 * k**2 * al * q * np.cos(q * h) * tanh
        else:
            # ⚠️ 第二项是 **+**：A 族在区段② 推导为
            #   4k²αq·sin(qh) + (k²−q²)²·cos(qh)tanh(αh) = 0
            # 写成减号会挪动根位、造出伪根（实测 1 MHz 本该 1 根、却解出 4 根）
            v = 4.0 * k**2 * al * q * np.sin(q * h) + (k**2 - q**2) ** 2 * np.cos(q * h) * tanh
        scale = (k**2 + q**2) ** 2
    else:  # 区段①：两虚 ⇒ 除以公共 i 后再除以 cosh(αh)cosh(βh)
        al, be = np.sqrt(-p2), np.sqrt(-q2)
        if sym:
            v = (k**2 + be**2) ** 2 * np.tanh(be * h) - 4.0 * k**2 * al * be * np.tanh(al * h)
        else:
            v = 4.0 * k**2 * al * be * np.tanh(be * h) - (k**2 + be**2) ** 2 * np.tanh(al * h)
        scale = (k**2 + be**2) ** 2

    return float(v / scale) if scale and np.isfinite(v) else float("nan")


def cutoff_families(plate: Plate = ALUMINUM, *, n_max: int = 12) -> dict[str, list[float]]:
    """截止频率族（共四组，两族 × 两种取整条件）。

    `k→0` 时：

    - **对称**：`q⁴·sin(qh)·cos(ph)=0` ⇒ `sin(qh)=0`（剪切 `n·c_T/2h`）
      或 `cos(ph)=0`（纵向 `(2m−1)·c_L/4h`）
    - **反对称**：`q⁴·cos(qh)·sin(ph)=0` ⇒ `sin(ph)=0`（纵向 `n·c_L/2h`）
      或 `cos(qh)=0`（剪切 `(2m−1)·c_T/4h`）

    ⚠️ **漏掉任何一组，根数就对不上**：A 族的"多余根"其实就是
    `(2m−1)·c_T/4h`（310/930/1550 kHz）这批剪切四分之一族，不是伪根也不是复模态投影。
    """
    fT = plate.c_T / (2.0 * plate.h)
    fL = plate.c_L / (2.0 * plate.h)
    return {
        "shear": [n * fT for n in range(1, n_max + 1)],  # 对称：n·c_T/2h
        "longitudinal": [(2 * m - 1) * fL / 2.0 for m in range(1, n_max + 1)],  # 对称：(2m−1)·c_L/4h
        "longitudinal_n": [n * fL for n in range(1, n_max + 1)],  # 反对称：n·c_L/2h
        "shear_quarter": [(2 * m - 1) * fT / 2.0 for m in range(1, n_max + 1)],  # 反对称：(2m−1)·c_T/4h
    }


def is_near_cutoff(f: float, plate: Plate = ALUMINUM, *, tol: float = 0.02) -> bool:
    """是否落在**任一族**截止频率的 `±tol` 邻带内。

    落在邻带内时根数依赖窗口上限（新生支 `c→∞`），不做断言。
    """
    fam = cutoff_families(plate)
    every = fam["shear"] + fam["longitudinal"] + fam["longitudinal_n"] + fam["shear_quarter"]
    return any(abs(f - fc) / fc < tol for fc in every)


def expected_mode_count(
    f: float,
    plate: Plate = ALUMINUM,
    *,
    mode: str = "S",
    tol: float = 0.02,
) -> int | None:
    """给定频率下该族应有的**模态数**（含基阶）。

    - 对称：`N_S = 1 + ⌊f/f_T⌋ + ⌊(f/(f_L/2) + 1)/2⌋`
    - 反对称：`N_A = 1 + ⌊f/f_L⌋ + ⌊(f/(f_T/2) + 1)/2⌋`

    `f_T = c_T/2h`、`f_L = c_L/2h`。第一项是**无截止的基阶**（S0 / A0）；
    后两项分别数该族的两个截止族。截止邻带内返回 `None`。

    实测（ALUMINUM）：`N_S` = 1/1/1/3/3/4/6/7（100k…3M）、
    `N_A` = 1/1/1/2/3/4/5/8/12（10k…5M），与枚举根数逐一吻合。
    """
    if is_near_cutoff(f, plate, tol=tol):
        return None
    f_T = plate.c_T / (2.0 * plate.h)
    f_L = plate.c_L / (2.0 * plate.h)
    if mode.upper().startswith("S"):
        return 1 + int(np.floor(f / f_T)) + int(np.floor((f / (f_L / 2.0) + 1.0) / 2.0))
    return 1 + int(np.floor(f / f_L)) + int(np.floor((f / (f_T / 2.0) + 1.0) / 2.0))


def _grid(f: float, plate: Plate, *, lo: float, hi: float, ppc: int = 14) -> np.ndarray:
    """按局部振荡周期自适应布点（`d(qh)/dc = h·ω²/(q·c³)`），消除混叠。"""
    omega = 2.0 * np.pi * f
    cs = [lo]
    c = lo
    while c < hi and len(cs) < 60000:
        q2 = (omega / plate.c_T) ** 2 - (omega / c) ** 2
        q = np.sqrt(q2) if q2 > 0 else 0.0
        step = (2.0 * np.pi / max(plate.h * (omega**2 / (q * c**3)), 1e-12)) / ppc if q > 0 else hi / 400.0
        c += float(np.clip(step, 1e-3, hi / 60.0))
        cs.append(min(c, hi))
    return np.asarray(cs, dtype=float)


def _polish(c0: float, f: float, plate: Plate, mode: str, *, tol: float = 1e-9) -> float | None:
    """Newton 抛光（数值导数，步长夹紧），失败返回 None。"""
    c = float(c0)
    for _ in range(60):
        d = lamb_residual(c, f, plate, mode=mode)
        if not np.isfinite(d):
            return None
        dc = max(c * 1e-7, 1e-6)
        der = (lamb_residual(c + dc, f, plate, mode=mode) - lamb_residual(c - dc, f, plate, mode=mode)) / (2.0 * dc)
        if not np.isfinite(der) or der == 0:
            return None
        cn = c + float(np.clip(-d / der, -0.02 * c, 0.02 * c))
        if not np.isfinite(cn) or cn <= 0:
            return None
        if abs(cn - c) < 1e-12 * max(c, 1e-6):
            return cn if abs(lamb_residual(cn, f, plate, mode=mode)) < tol else None
        c = cn
    return c if abs(lamb_residual(c, f, plate, mode=mode)) < tol else None


def branch_roots(
    f: float,
    plate: Plate = ALUMINUM,
    *,
    mode: str = "S",
    c_max_factor: float = 8.0,
) -> np.ndarray:
    """给定频率下 `(0.03·c_T, 8·c_L)` 内的**全部**根（升序）。

    窗口下界取 `0.03·c_T`（覆盖 A0 低频小速度），上界 `8·c_L`（覆盖 5 MHz 时的第 13 支，实测 12608）。
    枚举后对 `(0.85·c_R, c_T)` 内的 `|v|` 局部极小做**相切根补充**——
    区段①的 S0 是相切根（两项巨量抵消，`v≈0` 但**不变号**），纯符号扫描会漏。
    """
    lo, hi = 0.03 * plate.c_T, c_max_factor * plate.c_L
    cs = _grid(f, plate, lo=lo, hi=hi)
    # 在区段边界 c_T / c_L 两侧插入**微扰点**（±1e-6），把跨边界的区间压到可忽略宽度：
    # 这样既不会把"跳变"当成根，也不会因为一个宽跨边界区间漏掉真根
    # （实测：不插点时 S 族在 2/3 MHz 各少一根）。
    eps = 1e-6
    bumps = [plate.c_T * (1 - eps), plate.c_T * (1 + eps), plate.c_L * (1 - eps), plate.c_L * (1 + eps)]
    cs = np.unique(np.concatenate([cs, np.asarray(bumps)]))
    cs = cs[(cs >= lo) & (cs <= hi)]
    vals = np.array([lamb_residual(float(c), f, plate, mode=mode) for c in cs])

    # 区段边界的 q²/p² 变号处**必须跳过**：三区段公式在此换段，函数发生跳变，
    # 那个"符号变化"不是根，是人为不连续（实测 A 族在每一条频率上都解出一个
    # 恰好等于 c_T 的假根，就是被这个跳变骗出来的）。
    omega = 2.0 * np.pi * f
    q2s = (omega / plate.c_T) ** 2 - (omega / cs) ** 2
    p2s = (omega / plate.c_L) ** 2 - (omega / cs) ** 2
    same_region = (np.signbit(q2s[:-1]) == np.signbit(q2s[1:])) & (np.signbit(p2s[:-1]) == np.signbit(p2s[1:]))

    roots: list[float] = []
    for i in range(cs.size - 1):
        if not same_region[i]:
            continue  # 跨区段 ⇒ 跳过（跳变不是根）
        v0, v1 = vals[i], vals[i + 1]
        if not (np.isfinite(v0) and np.isfinite(v1)) or v0 * v1 > 0:
            continue
        a, b, fa = float(cs[i]), float(cs[i + 1]), float(v0)
        for _ in range(80):
            m = 0.5 * (a + b)
            fm = lamb_residual(m, f, plate, mode=mode)
            if fa * fm <= 0:
                b = m
            else:
                a, fa = m, fm
        roots.append(0.5 * (a + b))

    # 相切根补充：在 (0.85·c_R, c_T) 找 |v| 局部极小再抛光
    if mode.upper().startswith("S"):
        band = (cs > 0.85 * CR_ALUMINUM) & (cs < plate.c_T)
        idx = np.where(band)[0]
        for j in idx[1:-1]:
            if not (np.isfinite(vals[j]) and abs(vals[j]) < abs(vals[j - 1]) and abs(vals[j]) < abs(vals[j + 1])):
                continue
            r = _polish(float(cs[j]), f, plate, mode)
            if r is not None and plate.c_T * 0.85 < r < plate.c_T:
                roots.append(r)

    out: list[float] = []
    for r in sorted(roots):
        if not out or abs(r - out[-1]) / max(r, 1.0) > 1e-5:
            out.append(r)
    return np.asarray(out, dtype=float)


def s0_curve(freqs, plate: Plate = ALUMINUM, *, c_max_factor: float = 8.0) -> np.ndarray:
    """S0 分支：**身份规则 = 对称族最小根**（不做"离上一点最近"）。

    三道守卫，缺一条就会重蹈前 7 次的覆辙：

    1. **根数对账**（`N_S` 可算时）：`len(roots) != N_S` ⇒ 该点返回 `nan`（宁缺不猜）。
    2. **截止邻带**（`N_S` 无定义时）：不算根数，改用**身份区间守卫**：
       `0.85·c_R ≤ min(root) ≤ 1.002·c_plate`。这样 5 MHz（`5000 kHz` 距剪切截止 4960 仅 0.8%）
       仍能给出 2894，而串到 L 支（5532/6459）会被区间挡掉。
    3. **恒等守卫**：任何情况下都要求 `|c − c_T| > 5e-3·c_T`（`c_T` 是退化解吸引盆）。

    实测锚点：10 kHz→5397（=`c_plate`）、1 MHz→2932、2 MHz→2895、5 MHz→2894（≈`c_R`）。
    """
    fs = np.asarray(freqs, dtype=float)
    out = np.full(fs.shape, np.nan)
    lo_ok = 0.85 * CR_ALUMINUM
    hi_ok = 1.002 * plate.c_plate

    for i, f in enumerate(fs.ravel()):
        if not np.isfinite(f):
            continue  # nan 不造数
        want = expected_mode_count(float(f), plate)
        roots = branch_roots(float(f), plate, mode="S", c_max_factor=c_max_factor)
        if roots.size == 0:
            continue
        if want is not None and roots.size != want:
            continue  # 根数不齐 ⇒ 拒绝
        c0 = float(roots[0])
        if not (lo_ok <= c0 <= hi_ok):
            continue  # 身份区间守卫
        if abs(c0 - plate.c_T) <= 5e-3 * plate.c_T:
            continue  # 退化解吸引盆
        out.ravel()[i] = c0
    return out


def a0_curve(freqs, plate: Plate = ALUMINUM, *, c_max_factor: float = 8.0) -> np.ndarray:
    """A0 分支：反对称族中 `< c_T` 的**最小根**（与 S0 一样的三道守卫）。

    A0 与 S0 在高频几乎重合（`fd→∞` 两者都 → `c_R`），**必须靠族别区分**：
    这里用的是**反对称方程**，不是"在对称族根里挑第二小"。

    守卫与 `s0_curve` 同构：根数对账（`N_A`）/ 截止邻带下用身份区间 / `c_T` 邻域排除。
    """
    fs = np.asarray(freqs, dtype=float)
    out = np.full(fs.shape, np.nan)
    lo_ok, hi_ok = 0.85 * CR_ALUMINUM * 0.2, plate.c_T

    for i, f in enumerate(fs.ravel()):
        if not np.isfinite(f):
            continue
        want = expected_mode_count(float(f), plate, mode="A")
        roots = branch_roots(float(f), plate, mode="A", c_max_factor=c_max_factor)
        if roots.size == 0:
            continue
        if want is not None and roots.size != want:
            continue  # 根数不齐 ⇒ 拒绝
        below = roots[roots < plate.c_T]
        if below.size == 0:
            continue
        c0 = float(below[0])
        if not (lo_ok <= c0 <= hi_ok):
            continue
        if abs(c0 - plate.c_T) <= 5e-3 * plate.c_T:
            continue
        out.ravel()[i] = c0
    return out
