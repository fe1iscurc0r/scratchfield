"""工单 266 · P1-2 验收：板波频散（对称模态残差 + 单点求解 + 解析锚点）。

**本文件的验收范围刻意小于 WO-276 §3 的原设想**，原因如实写在下面：

| 项 | 状态 | 判据 |
|---|---|---|
| 残差函数（复数开方） | ✅ | 必须随 `c_ph` 真实变化；解点处 `|D|<1e-7` |
| 单点 Newton 求解 | ✅ | 10 kHz 处 ≈ 板波速（0.01%）；解落在 `(c_T, c_L)` |
| 板波速 / 截止频率 | ✅ | 解析式自检 |
| **全频段 S0 分支跟踪** | ✅ 已实现（WO-277） | 委托 `dispersion_branches`；锚点见下 |
| **A0 模态** | ✅ 已实现（WO-277） | 反对称方程；500 kHz=2740（文献 2762） |

WO-277 第 3 批已收口：原先"未实现断言"改为**断言结果正确**。
"""

from __future__ import annotations

import numpy as np
import pytest

from acoustics import dispersion as dp

P = dp.ALUMINUM


# --------------------------------------------------------------------------- #
# 残差函数（复数开方前提）
# --------------------------------------------------------------------------- #
def test_residual_varies_with_cph():
    """回归守卫：残差必须随 `c_ph` **真的变化**。

    早先用 `sqrt(max(p²,0))`（把虚部压成 0）时，残差在整个区间恒为 ±1，
    "等距扫描找变号"一个根都找不到、Newton 也无效。这条断言锁住复数开方这个前提。
    """
    f = 1.0e5
    cs = np.linspace(P.c_T * 1.05, P.c_L * 0.95, 200)
    vals = np.array([dp.lamb_symmetric_residual(float(c), f, P) for c in cs])

    assert np.all(np.isfinite(vals))
    assert vals.std() > 1e-3, f"残差几乎不随 c_ph 变化（std={vals.std():.2e}），复数开方可能被改坏"
    assert np.any(np.abs(vals) < 0.5), "区间内应存在残差接近零的区域"


def test_residual_is_zero_at_solved_points():
    """解出的点必须真的让残差为零（不是"看起来像根"的点）。"""
    for f in (1.0e4, 1.0e5, 1.0e6):
        c = dp.solve_symmetric_mode(f, P)
        assert c is not None, f"f={f:.0f} 求解失败"
        assert abs(dp.lamb_symmetric_residual(c, f, P)) < 1e-7


# --------------------------------------------------------------------------- #
# 单点求解
# --------------------------------------------------------------------------- #
def test_solve_low_frequency_matches_plate_velocity():
    """10 kHz 处 S0 相速度 ≈ 板波速（判据 5%，实测 0.01%）。"""
    c = dp.solve_symmetric_mode(1.0e4, P)
    assert c is not None
    c_plate = dp.plate_velocity(P)
    assert abs(c - c_plate) / c_plate < 0.05


def test_solve_results_inside_transverse_longitudinal():
    """S 模态解必须落在 `(c_T, c_L)` 内——落到外面说明求到了别的分支。"""
    for f in (1.0e4, 5.0e4, 1.0e5, 3.0e5, 1.0e6, 3.0e6):
        c = dp.solve_symmetric_mode(f, P)
        assert c is not None, f"f={f:.0f} 求解失败"
        assert P.c_T < c < P.c_L, f"f={f:.0f}: c={c:.1f} 越界 (c_T={P.c_T}, c_L={P.c_L})"


def test_s0_dips_below_plate_velocity():
    """S0 存在**浅极小值**（100 kHz 处低于板波速）。

    这是 S0 的真实物理特征（实测 5376.5 < 5397.5），不是数值抖动。
    钉住它，防止将来有人"为了让曲线好看"去改方程。
    """
    c_plate = dp.plate_velocity(P)
    c100k = dp.solve_symmetric_mode(1.0e5, P)
    assert c100k is not None
    assert c100k < c_plate, f"S0 在 100 kHz 未观察到凹陷：{c100k:.1f} ≥ {c_plate:.1f}"
    assert (c_plate - c100k) / c_plate < 0.01, "凹陷幅度过大，可能求错分支"


def test_plate_velocity_formula():
    """板波速公式自检：`2c_T√(1−c_T²/c_L²)`（铝 ≈ 5397.5 m/s）。"""
    assert dp.plate_velocity(P) == pytest.approx(5397.5, rel=1e-3)


def test_cutoffs_match_analytic_formula():
    """对称模态截止频率 = `n·c_T/(2h)`（解析式，判据 < 1%）。"""
    got = dp.cutoff_frequencies(P, "S", 4)
    want = [n * P.c_T / (2.0 * P.h) for n in range(1, 5)]
    for g, w in zip(got, want, strict=True):
        assert abs(g - w) / w < 0.01
    assert got[0] == pytest.approx(620e3, rel=1e-6)  # 3100/0.005


# --------------------------------------------------------------------------- #
# 收口（WO-277 第 3 批）：原有的两条"未实现断言"改为断言**结果正确**
# --------------------------------------------------------------------------- #
def test_s0_curve_now_delegates_and_matches_anchors():
    """收口：`s0_curve` 现委托 `dispersion_branches`，必须给出正确锚点。

    历史：这里原先断言"必须 raise"（防止半成品冒充成果）。WO-277 用
    「根数对账 + `S0=最小根`」做实之后，把断言改成**验证结果**——
    否则 raise 会变成掩盖"没做完"的挡箭牌。
    """
    got = dp.s0_curve(np.array([1.0e4, 1.0e6, 2.0e6, 5.0e6]))
    assert np.all(np.isfinite(got)), f"有点未解出：{got}"
    assert 5396 <= got[0] <= 5399, f"10 kHz S0={got[0]:.1f} 应 = c_plate=5397.5"
    assert 2900 <= got[1] <= 2965, f"1 MHz S0={got[1]:.1f}（真值 2932）"
    assert 2870 <= got[2] <= 2920, f"2 MHz S0={got[2]:.1f}（真值 2895）"
    assert abs(got[3] - 2894) / 2894 < 0.01, f"5 MHz S0={got[3]:.1f} 应 ≈ c_R=2894"


def test_a0_curve_available_and_matches_literature():
    """收口：A0 已实现（反对称方程），500 kHz 对齐文献 2762。"""
    assert hasattr(dp, "a0_curve"), "a0_curve 应已委托到 dispersion_branches"
    got = dp.a0_curve(np.array([1.0e5, 5.0e5, 1.0e6]))
    assert 1850 <= got[0] <= 1900
    assert 2680 <= got[1] <= 2820, f"500 kHz A0={got[1]:.1f}（文献 2762）"
    assert 2840 <= got[2] <= 2900
    # 历史说明串仍在，但语义已改为"已解决"
    assert "已解决" in dp.A0_NOT_IMPLEMENTED_REASON
