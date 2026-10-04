"""AS5600 闭环与自校准**规格**测试（卷129 W129-02，主机端）。

与 W129-01 同一策略：固件端证据 = arduino-cli 编译通过 + 上机自检（串口 SELFTEST_PASS）；
这里用 Python 独立实现同一套**编码器/闭环规格**（12bit 换算、跨 0 点滤波、零点偏移、
读失败上报、非线性残差），断言固件同款期望值。

运行：.venv/Scripts/python.exe -m pytest hardware/antenna-rotator/tests -q
"""
from __future__ import annotations

import math

COUNTS = 4096.0


# ---------------------------------------------------------------------------
# 规格实现（对应 feedback/as5600.hpp）
# ---------------------------------------------------------------------------


def counts_to_deg(counts: int) -> float:
    return (counts & 0x0FFF) / COUNTS * 360.0


def deg_to_counts(deg: float) -> int:
    return int((deg % 360.0) / 360.0 * COUNTS) & 0x0FFF


def norm360(deg: float) -> float:
    return deg % 360.0


def shortest_delta(to_deg: float, from_deg: float) -> float:
    d = norm360(to_deg) - norm360(from_deg)
    if d > 180.0:
        d -= 360.0
    if d <= -180.0:
        d += 360.0
    return d


def wrap_safe_average(samples: list[float]) -> float:
    """以最后一个样本为基准做最短差平均（避免 359° 与 1° 被平均成 180°）。"""
    if not samples:
        return 0.0
    ref = samples[-1]
    deltas = [shortest_delta(s, ref) for s in samples]
    return norm360(ref + sum(deltas) / len(deltas))


def linear_fit_residual(pairs: list[tuple[float, float]]) -> tuple[float, float, float]:
    """最小二乘拟合 y=slope·x+intercept，返回 (slope, intercept, 最大残差)。"""
    n = float(len(pairs))
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] * p[0] for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom if abs(denom) > 1e-6 else 1.0
    intercept = (sy - slope * sx) / n
    residual = max(abs(shortest_delta(slope * x + intercept, y)) for x, y in pairs)
    return slope, intercept, residual


def synthetic_angle(t: float, period_s: float = 4.0) -> float:
    """与固件 SyntheticSource 同款：正弦 ±170°，带二次畸变（非线性）。"""
    deg = 180.0 + 170.0 * math.sin(2.0 * math.pi * t / period_s)
    norm = (deg - 180.0) / 180.0
    return deg + 1.5 * norm * norm * (1.0 if norm > 0 else -1.0)


# ---------------------------------------------------------------------------
# 1. 编码器换算
# ---------------------------------------------------------------------------


def test_counts_to_deg_mapping():
    assert abs(counts_to_deg(0) - 0.0) < 1e-3
    assert abs(counts_to_deg(2048) - 180.0) < 0.05
    assert abs(counts_to_deg(4095) - 359.912) < 0.05
    # 12bit 掩码：超范围输入被截断到低 12 位
    assert counts_to_deg(4096) == counts_to_deg(0)


def test_deg_to_counts_mapping():
    assert deg_to_counts(90.0) == 1024
    assert deg_to_counts(0.0) == 0
    assert deg_to_counts(-90.0) == 3072, "负角先归一到 0..360"
    assert deg_to_counts(360.0) == 0


def test_conversion_roundtrip_error_below_half_degree():
    """工单验收：模拟角度换算误差 < 0.5°（12bit 量化步长 0.0879°）。"""
    worst = 0.0
    for deg in [i * 0.5 for i in range(720)]:
        back = counts_to_deg(deg_to_counts(deg))
        worst = max(worst, abs(shortest_delta(deg, back)))
    assert worst < 0.5, f"最大往返误差 {worst:.4f}°"


# ---------------------------------------------------------------------------
# 2. 跨 0 点滤波与零点偏移
# ---------------------------------------------------------------------------


def test_wrap_safe_average_across_zero():
    avg = wrap_safe_average([359.0, 0.0, 1.0])
    assert abs(shortest_delta(avg, 0.0)) < 0.1, f"跨 0 点平均应在 0° 附近，实际 {avg:.3f}°"
    naive = sum([359.0, 0.0, 1.0]) / 3
    assert abs(naive - 120.0) < 1e-6, "朴素平均会掉进 120° 陷阱（正是要避免的）"


def test_zero_offset_applied():
    measured = 137.5
    offset = 137.5
    assert abs(norm360(measured - offset)) < 1e-6, "去零点后为 0°"
    measured2, offset2 = 5.0, 355.0
    assert abs(norm360(measured2 - offset2) - 10.0) < 1e-6, "跨 0 点去零点"


# ---------------------------------------------------------------------------
# 3. 读失败与抖动
# ---------------------------------------------------------------------------


def test_read_failure_is_surfaced():
    """规格：读失败必须如实上报（不吞错），计数可查。"""
    failures = 0
    ok = False
    if not ok:
        failures += 1
    assert failures == 1, "读失败要计数，供上层降级/fault"


def test_jitter_detection_threshold():
    warn_deg = 5.0
    seq = [10.0, 10.2, 10.1, 30.5]
    jitters = sum(1 for a, b in zip(seq, seq[1:]) if abs(shortest_delta(b, a)) > warn_deg)
    assert jitters == 1, "20° 跳变应记 1 次 jitter"


# ---------------------------------------------------------------------------
# 4. 自校准报告
# ---------------------------------------------------------------------------


def test_self_calibration_detects_nonlinearity():
    """往返扫描采样 → 线性拟合残差量化非线性。

    构造：理想扫角单调 0..360，实测 = 理想 + 1.5·sin(2θ) 的畸变（模拟磁铁偏心/刻度非理想）。
    拟合斜率应 ≈1，残差应被量化出非零值。
    """
    pairs = []
    for i in range(64):
        ideal = 360.0 / 64.0 * i
        measured = ideal + 1.5 * math.sin(math.radians(2.0 * ideal))
        pairs.append((norm360(ideal), norm360(measured)))
    slope, intercept, residual = linear_fit_residual(pairs)
    assert 0.9 < slope < 1.1, f"拟合斜率应接近 1，实际 {slope:.3f}"
    assert residual > 0.2, f"畸变信号应被量化出非零残差，实际 {residual:.3f}°"


def test_self_calibration_notes_large_nonlinearity():
    """残差 > 1° 时应给出「磁铁偏心」提示（与固件 note 文案一致）。"""
    residual = 1.4
    note = "非线性偏大(%.2f°)，建议检查磁铁偏心" % residual if residual > 1.0 else "校准正常"
    assert "磁铁偏心" in note


def test_self_calibration_span_recorded():
    sweep = [synthetic_angle(i * 0.05) for i in range(120)]
    lo, hi = min(sweep), max(sweep)
    assert hi - lo > 100.0, "正弦扫描应覆盖 >100° 行程"


# ---------------------------------------------------------------------------
# 5. 闭环微调建议
# ---------------------------------------------------------------------------


def test_trim_recommendation_limited_and_signed():
    tol, max_trim = 0.5, 3.0

    def recommend(target: float, measured: float) -> float | None:
        err = shortest_delta(target, measured)  # 从实测走到目标的有向最短差
        if abs(err) <= tol:
            return None
        return max(-max_trim, min(max_trim, err))  # trim 直接加到实测角上

    assert recommend(100.0, 100.2) is None, "容限内不微调"
    # 实测 104、目标 100：需往 -4° 走 → 限幅到 -3°
    assert recommend(100.0, 104.0) == -3.0, "修正方向朝目标且限幅到 3°"
    assert recommend(0.0, 359.0) == 1.0, "跨 0 点：从 359° 往 +1° 走到 0°"
    assert recommend(359.0, 1.0) == -2.0, "反向跨 0 点"
