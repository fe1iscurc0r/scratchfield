"""工单 277 · 第 1 批验收：板波分支跟踪（枚举 + 根数对账 + S0 身份）。

核心判据是**根数对账**（整数拓扑量，容差 ±0）：
`len(branch_roots(f))` 必须等于 `N_S(f) = 1 + ⌊f/f_T⌋ + ⌊(2f/f_L+1)/2⌋`。
少一根 = 丢支，多一根 = 伪根，两者都是真 bug，不给容差。

截止邻带（`±2%`）不做根数断言（新生支 `c→∞`，计数依赖窗口上限）。
"""

from __future__ import annotations

import numpy as np
import pytest

from acoustics import dispersion_branches as db
from acoustics.dispersion import ALUMINUM

P = ALUMINUM

# (f, 期望根数) —— 全部为"净点"（距任一截止频率 > 2%）
NET_POINTS = [
    (1.0e5, 1),
    (2.5e5, 1),
    (5.0e5, 1),
    (9.0e5, 3),
    (1.0e6, 3),
    (1.5e6, 4),
    (2.0e6, 6),
    (3.0e6, 7),
]


# --------------------------------------------------------------------------- #
# 根数公式本身
# --------------------------------------------------------------------------- #
def test_expected_mode_count_matches_measured():
    """`N_S` 公式必须与实测根数一一吻合（实测 1/1/1/3/3/4/6/7）。"""
    for f, want in NET_POINTS:
        assert db.expected_mode_count(f, P) == want, f"f={f:.0f} 的 N_S 算错"
        assert db.branch_roots(f, P).size == want, f"f={f:.0f} 实测根数 ≠ N_S={want}"


def test_near_cutoff_returns_none():
    """截止邻带内 `N_S` 必须返回 None（不做断言）。剪切截止 620 kHz、纵向截止 1260 kHz。"""
    assert db.expected_mode_count(6.2e5, P) is None
    assert db.expected_mode_count(1.24e6, P) is None
    assert db.expected_mode_count(5.0e6, P) is None  # 距 4960 kHz 仅 0.8%
    assert db.expected_mode_count(1.0e6, P) == 3  # 净点照常


def test_cutoff_families_both_present():
    """两族截止：剪切 `n·c_T/2h`(620/1240/1860)、纵向 `(2m−1)·c_L/4h`(630/1890/3150)。

    纵向族第一截止在 **630 kHz**（不是 1260）——与实测 `N_S` 自洽：
    1 MHz 处 `N_S = 1 + 1 + 1 = 3`（S0 + S1(620k) + L1(630k)），实测正好 3 根。
    """
    fam = db.cutoff_families(P)
    assert fam["shear"][0] == pytest.approx(620e3, rel=1e-6)
    # 纵向族：(2m−1)·c_L/(4h) ⇒ 630 / 1890 / 3150 kHz
    assert fam["longitudinal"][0] == pytest.approx(630e3, rel=1e-6)
    assert fam["longitudinal"][1] == pytest.approx(1890e3, rel=1e-6)


# --------------------------------------------------------------------------- #
# S0 身份与锚点
# --------------------------------------------------------------------------- #
def test_s0_anchors():
    """S0 锚点：高频趋于 `c_R≈2894`（**不是** `c_L=6300`）。"""
    freq = np.array([1.0e4, 1.0e5, 5.0e5, 1.0e6, 2.0e6, 5.0e6])
    got = db.s0_curve(freq)

    assert 5396 <= got[0] <= 5399, f"10 kHz S0={got[0]:.1f} 应≈c_plate=5397.5"
    assert 5360 <= got[1] <= 5395, f"100 kHz S0={got[1]:.1f} 超出区间"
    assert 3690 <= got[2] <= 3900, f"500 kHz S0={got[2]:.1f}（文献 3841）"
    assert 2900 <= got[3] <= 2965, f"1 MHz S0={got[3]:.1f}（真值≈2932）"
    assert 2870 <= got[4] <= 2920, f"2 MHz S0={got[4]:.1f}（真值≈2895）"
    assert 2870 <= got[5] <= 2918, f"5 MHz S0={got[5]:.1f}（≈c_R=2894）"


def test_s0_monotone_nonincreasing():
    """S0 从 `c_plate` 单调降到 `c_R`（全程不增）。"""
    freq = np.geomspace(1.0e5, 5.0e6, 40)
    got = db.s0_curve(freq)
    ok = np.isfinite(got)
    vals = got[ok]
    assert vals.size >= 30, f"有效点过少：{vals.size}/40（拒绝对数不应超过 25%）"
    d = np.diff(vals)
    assert np.all(d <= 1e-3 * vals[:-1]), f"S0 非单调，最大上升 {d.max():.1f} m/s"
    assert vals.max() <= P.c_plate * 1.002, "S0 超过 c_plate（身份错误）"


def test_a0_anchors():
    """A0 锚点：10 kHz≈700、500 kHz≈2740（文献 2762）、1 MHz≈2869。"""
    freq = np.array([1.0e4, 5.0e5, 1.0e6])
    got = db.a0_curve(freq)
    assert 660 <= got[0] <= 720, f"10 kHz A0={got[0]:.1f}"
    assert 2680 <= got[1] <= 2820, f"500 kHz A0={got[1]:.1f}（文献 2762）"
    assert 2840 <= got[2] <= 2900, f"1 MHz A0={got[2]:.1f}"


def test_a0_increasing_to_rayleigh():
    """A0 单调升向 `c_R`（与 S0 在高频靠拢，这是厚板极限的正确物理）。"""
    freq = np.array([1.0e4, 1.0e5, 2.5e5, 5.0e5, 1.0e6, 5.0e6])
    got = db.a0_curve(freq)
    assert np.all(np.diff(got) > 0), f"A0 非单调：{[round(v) for v in got]}"
    assert abs(got[-1] - db.CR_ALUMINUM) / db.CR_ALUMINUM < 0.01


# --------------------------------------------------------------------------- #
# 反向断言（必须被抓住的错误行为）
# --------------------------------------------------------------------------- #
def test_nan_input_does_not_invent_numbers():
    """守卫 1：输入 nan 的位置必须输出 nan（不许插值补数）。"""
    out = db.s0_curve(np.array([1.0e6, np.nan, 2.0e6]))
    assert out.shape == (3,)
    assert np.isfinite(out[0]) and np.isfinite(out[2])
    assert np.isnan(out[1])


def test_count_mismatch_refuses_to_answer():
    """守卫 6：根数不齐时必须返回 nan —— 600 kHz（距剪切截止 620 kHz 仅 3.2%）。

    实测该点解出 3 根（3261 + 伪根 7444/43854），而 `N_S=1` ⇒ **拒绝出数**。
    这条正是"宁缺不猜"的判据。
    """
    assert db.branch_roots(6.0e5, P).size > db.expected_mode_count(6.0e5, P)
    assert np.isnan(db.s0_curve(np.array([6.0e5]))[0])


def test_pseudo_root_never_selected_as_s0():
    """守卫 7：600 kHz 的伪根 7444 绝不能被当成 S0。"""
    roots = db.branch_roots(6.0e5, P)
    assert roots[0] < 3400, f"S0 应是 3261 附近的根，实际 min={roots[0]:.0f}"
    assert not any(abs(r - 7444) < 50 and r == roots[0] for r in roots)


def test_no_serial_branch_jump():
    """守卫 3：不得串到 L1 支（1 MHz 的 5532、2 MHz 的 6459 都是 L 支，不是 S0）。"""
    s1 = db.s0_curve(np.array([1.0e6]))[0]
    s2 = db.s0_curve(np.array([2.0e6]))[0]
    assert abs(s1 - 5532) > 100, "1 MHz 串到了 L1 支(5532)"
    assert abs(s2 - 6459) > 100, "2 MHz 串到了 L1 支(6459)"


def test_never_returns_transverse_degenerate_solution():
    """守卫 4：`c_T` 是退化解吸引盆，输出不得落在 `c_T ±0.5%`。"""
    freq = np.geomspace(1.0e5, 5.0e6, 40)
    for c in db.s0_curve(freq)[np.isfinite(db.s0_curve(freq))]:
        assert abs(c - P.c_T) > 5e-3 * P.c_T, f"落入 c_T 吸引盆：{c:.1f}"


def test_no_overflow_or_invalid_values():
    """守卫 5：全程不得触发溢出/无效值警告（tanh 恒等变形的作用）。"""
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for f in (1.0e4, 1.0e5, 1.0e6, 5.0e6):
            r = db.lamb_residual(P.c_T * 1.5, f, P, mode="S")
            assert np.isfinite(r)
            assert np.all(np.isfinite(db.branch_roots(f, P)))


# --------------------------------------------------------------------------- #
# 第 2 批：A0 族别判定 + 区段边界回归
# --------------------------------------------------------------------------- #
def test_boundary_insert_keeps_s_counts():
    """回归守卫：在 `c_T`/`c_L` 两侧插入微扰点后，**S 族根数必须仍对**。

    背景：只加"跨区段跳过"而不插微扰点时，跨 `c_L` 的宽区间会吞掉真根
    （实测 2 MHz 从 6 根掉到 5 根、3 MHz 从 7 掉到 6）。插点把该区间压到 1e-6 量级后恢复。
    """
    assert db.branch_roots(2.0e6, P).size == 6
    assert db.branch_roots(3.0e6, P).size == 7


def test_a0_high_frequency_reaches_rayleigh():
    """A0 高频同样趋于 `c_R≈2894`（与 S0 靠拢），且始终 `< c_T`。"""
    freq = np.array([1.0e6, 2.0e6, 5.0e6])
    got = db.a0_curve(freq)
    for f, c in zip(freq, got, strict=True):
        assert np.isfinite(c), f"{f / 1e6:.0f} MHz 的 A0 未解出"
        assert c < P.c_T, f"{f / 1e6:.0f} MHz A0={c:.1f} 应 < c_T=3100"
        assert abs(c - db.CR_ALUMINUM) / db.CR_ALUMINUM < 0.02, f"{f / 1e6:.0f} MHz A0={c:.1f} 偏离 c_R"


def test_s0_and_a0_converge_but_only_mode_can_split_them():
    """S0 与 A0 在高频几乎重合 ⇒ **只能靠族别（对称/反对称方程）区分**，不能靠数值大小。

    实测 5 MHz：S0=2894、A0=2894（差 < 5 m/s）。若只按"根的大小"分族必然错。
    这条断言把"必须用 mode 参数"钉住。
    """
    s0 = db.s0_curve(np.array([5.0e6]))[0]
    a0 = db.a0_curve(np.array([5.0e6]))[0]
    assert abs(s0 - a0) < 5.0, f"5 MHz 处两族应几乎重合：S0={s0:.1f} / A0={a0:.1f}"
    # 同一频率下，两个族别各自解出的根集合不应相同（否则说明 mode 参数没生效）
    rs = db.branch_roots(5.0e6, P, mode="S")
    ra = db.branch_roots(5.0e6, P, mode="A")
    assert rs.size != ra.size or not np.allclose(rs[: ra.size], ra[: rs.size])


def test_a_family_counts_reconcile():
    """**A 族根数对账**（第 3 批完成）：`N_A = 1 + ⌊f/f_L⌋ + ⌊(f/(f_T/2)+1)/2⌋`。

    早先以为 A 族有"多余实根（复模态投影）"，实际是**漏了剪切四分之一族**
    `(2m−1)·c_T/(4h)`（310/930/1550 kHz）。补上这一族后根数全部吻合。
    """
    f_T = P.c_T / (2.0 * P.h)
    f_L = P.c_L / (2.0 * P.h)
    for f in (1.0e4, 1.0e5, 2.5e5, 5.0e5, 1.0e6, 1.5e6, 2.0e6, 3.0e6):
        want = None if db.is_near_cutoff(f, P) else (1 + int(f // f_L) + int((f / (f_T / 2.0) + 1.0) // 2.0))
        assert db.expected_mode_count(f, P, mode="A") == want
        if want is not None:
            assert db.branch_roots(f, P, mode="A").size == want, f"f={f:.0f} A 族根数不符"


def test_four_cutoff_families_present():
    """四组截止族必须齐（两族 × 两种取整条件）；漏一组根数就对不上。"""
    fam = db.cutoff_families(P)
    assert set(fam) == {"shear", "longitudinal", "longitudinal_n", "shear_quarter"}
    assert fam["shear"][0] == pytest.approx(620e3, rel=1e-6)
    assert fam["longitudinal"][0] == pytest.approx(630e3, rel=1e-6)
    assert fam["longitudinal_n"][0] == pytest.approx(1260e3, rel=1e-6)
    assert fam["shear_quarter"][0] == pytest.approx(310e3, rel=1e-6)


def test_a0_selection_ignores_extra_roots():
    """尽管 A 族有多余根，A0 仍稳：取 `< c_T` 的最小根，且三个锚点与文献吻合。"""
    freq = np.array([1.0e5, 5.0e5, 1.0e6])
    got = db.a0_curve(freq)
    assert 1850 <= got[0] <= 1900
    assert 2680 <= got[1] <= 2820  # 文献 2762
    assert 2840 <= got[2] <= 2900
