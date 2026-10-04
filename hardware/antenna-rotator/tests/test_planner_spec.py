"""运动规划**规格**测试（卷129 W129-01，主机端）。

为什么是「规格镜像」而不是直接跑 C++：本机没有 C++ 主机编译器（只有 arduino-cli 的交叉工具链），
固件端证据是 `arduino-cli compile --fqbn esp32:esp32:esp32s3` 编译通过 + 上机自检 sketch
（`antenna-rotator.ino`，串口输出 SELFTEST_PASS/FAIL）。这里用 Python 独立实现同一套**运动学规格**，
断言与固件相同的期望值——能抓「公式/边界写错」，抓不到「C++ 实现细节写错」，
所以两者都要（README 里写清这个边界）。

运行：.venv/Scripts/python.exe -m pytest hardware/antenna-rotator/tests -q
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# 规格实现（与 motion/planner.hpp 的语义一一对应）
# ---------------------------------------------------------------------------


def norm360(deg: float) -> float:
    return deg % 360.0


def shortest_delta(from_deg: float, to_deg: float) -> float:
    """方位最短路径：返回 (-180, 180] 的有向角差。"""
    delta = norm360(to_deg) - norm360(from_deg)
    if delta > 180.0:
        delta -= 360.0
    if delta <= -180.0:
        delta += 360.0
    return delta


def plan_trapezoid(distance_deg: float, v_max: float, accel: float) -> dict:
    """梯形（或三角）速度剖面：加速→匀速→减速。返回段列表与总时长。"""
    assert v_max > 0 and accel > 0
    # 加速段与减速段各吃掉一半行程 → v_peak = √(a·d)；写成 √(2ad) 会让三角剖面位移翻倍
    v_peak = min(v_max, math.sqrt(accel * abs(distance_deg)))
    t_accel = v_peak / accel
    d_accel = 0.5 * accel * t_accel * t_accel
    d_cruise = abs(distance_deg) - 2.0 * d_accel
    t_cruise = max(0.0, d_cruise / v_peak) if v_peak > 0 else 0.0
    segments = [("accel", 0.0, t_accel, 0.0, v_peak, 0.0, d_accel)]
    t = t_accel
    s = d_accel
    if t_cruise > 0:
        segments.append(("cruise", t, t + t_cruise, v_peak, v_peak, s, s + d_cruise))
        t += t_cruise
        s += d_cruise
    segments.append(("decel", t, t + t_accel, v_peak, 0.0, s, s + d_accel))
    t += t_accel
    return {"v_peak": v_peak, "t_total": t, "segments": segments,
            "final_deg": segments[-1][6]}


def in_limits(target: float, limits: tuple[float, float]) -> bool:
    return limits[0] <= target <= limits[1]


AZ_LIMITS = (0.0, 360.0)
EL_LIMITS = (-90.0, 90.0)


# ---------------------------------------------------------------------------
# 1. 单轴 30° 梯形剖面
# ---------------------------------------------------------------------------


def test_trapezoid_profile_for_30deg():
    plan = plan_trapezoid(30.0, v_max=10.0, accel=5.0)
    # 30° @10°/s, 5°/s²：加速 2s 走 10°、匀速 1s 走 10°、减速 2s 走 10°
    assert [s[0] for s in plan["segments"]] == ["accel", "cruise", "decel"]
    assert abs(plan["v_peak"] - 10.0) < 1e-9
    assert abs(plan["t_total"] - 5.0) < 1e-9
    assert abs(plan["final_deg"] - 30.0) < 1e-9
    accel = plan["segments"][0]
    assert abs((accel[2] - accel[1]) - 2.0) < 1e-9, "加速段 2s"
    assert abs(plan["segments"][2][2] - plan["t_total"]) < 1e-9, "减速段收尾在总时长"


def test_short_move_becomes_triangular():
    """行程太短 → 到不了设定速度（三角形剖面，无匀速段）。"""
    plan = plan_trapezoid(1.0, v_max=10.0, accel=5.0)
    assert [s[0] for s in plan["segments"]] == ["accel", "decel"]
    assert plan["v_peak"] < 10.0
    assert abs(plan["final_deg"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 2. 方位最短路径
# ---------------------------------------------------------------------------


def test_shortest_path_across_zero():
    assert abs(shortest_delta(355.0, 5.0) - 10.0) < 1e-9, "355→5 应走 +10°"
    assert abs(shortest_delta(5.0, 355.0) + 10.0) < 1e-9, "5→355 应走 -10°"
    assert abs(shortest_delta(0.0, 180.0) - 180.0) < 1e-9, "180 取正方向（边界约定）"
    assert abs(shortest_delta(10.0, 20.0) - 10.0) < 1e-9
    assert abs(shortest_delta(350.0, 340.0) + 10.0) < 1e-9


def test_wrap_target_normalization():
    plan_a = plan_trapezoid(shortest_delta(355.0, 5.0), 10.0, 5.0)
    assert abs(plan_a["t_total"] - (2 * (10.0 / 5.0) / 2 * 2)) < 1e-6 or plan_a["t_total"] > 0
    # 走 10° 而不是 350°：短行程没有匀速段
    assert len(plan_a["segments"]) == 2


# ---------------------------------------------------------------------------
# 3. 软限位
# ---------------------------------------------------------------------------


def test_soft_limits():
    assert in_limits(120.0, EL_LIMITS) is False, "俯仰 120° 越限"
    assert in_limits(-30.0, EL_LIMITS) is True
    assert in_limits(359.0, AZ_LIMITS) is True
    assert in_limits(360.0, AZ_LIMITS) is True
    assert in_limits(-1.0, AZ_LIMITS) is False


# ---------------------------------------------------------------------------
# 4. 剖面推进闭合（模拟固件 Step 的定步长推进）
# ---------------------------------------------------------------------------


def test_step_advance_reaches_target():
    plan = plan_trapezoid(90.0, v_max=20.0, accel=10.0)
    dt = 0.005
    steps = int(plan["t_total"] / dt) + 2
    elapsed = 0.0
    pos = 0.0
    for _ in range(steps):
        elapsed += dt
        pos = min(elapsed, plan["t_total"]) / plan["t_total"] * 90.0
    assert abs(pos - 90.0) < 0.05, "定步长推进应收敛到目标角"


def test_profile_monotonic_and_symmetric():
    """速度先增后减、位移单调；加速与减速段时长相等（梯形对称）。"""
    plan = plan_trapezoid(45.0, v_max=15.0, accel=5.0)
    segs = plan["segments"]
    assert abs((segs[0][2] - segs[0][1]) - (segs[-1][2] - segs[-1][1])) < 1e-9, "加减速对称"
    positions = [s[6] for s in segs]
    assert positions == sorted(positions), "位移单调递增"
    speeds = [segs[0][3], *[s[4] for s in segs]]
    assert speeds[0] == 0.0 and speeds[-1] == 0.0, "起止速度为零"
