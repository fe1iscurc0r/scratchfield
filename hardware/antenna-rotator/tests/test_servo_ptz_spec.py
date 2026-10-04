"""舵机 PTZ **规格**测试（卷129 W129-03，主机端）。

固件端证据 = arduino-cli 编译通过 + 上机自检；这里独立实现同一套规格：
脉宽映射、平滑渐变步进、限位拒绝、堵转判定、多轴并行到位。

运行：.venv/Scripts/python.exe -m pytest hardware/antenna-rotator/tests -q
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 规格实现（对应 servo_ptz/servo_axis.hpp）
# ---------------------------------------------------------------------------


class ServoCal:
    def __init__(self, min_us=500, max_us=2500, min_deg=0.0, max_deg=180.0):
        self.min_us, self.max_us = min_us, max_us
        self.min_deg, self.max_deg = min_deg, max_deg

    def deg_to_us(self, deg: float) -> int:
        clamped = min(max(deg, self.min_deg), self.max_deg)
        ratio = (clamped - self.min_deg) / (self.max_deg - self.min_deg)
        return int(self.min_us + ratio * (self.max_us - self.min_us))


class ServoAxis:
    def __init__(self, cal: ServoCal, step_deg=2.5, tolerance_deg=0.5, stall_a=0.0, invert=False):
        self.cal, self.step_deg = cal, step_deg
        self.tolerance_deg, self.stall_a, self.invert = tolerance_deg, stall_a, invert
        self.current = 0.0
        self.target = 0.0
        self.fault: str | None = None
        self.writes = 0

    def attach(self, deg: float) -> None:
        self.current = min(max(deg, self.cal.min_deg), self.cal.max_deg)
        self.target = self.current
        self.writes += 1

    def set_target(self, deg: float) -> tuple[bool, str | None]:
        if deg != deg:  # NaN
            self.fault = "invalid"
            return False, "invalid"
        if deg < self.cal.min_deg or deg > self.cal.max_deg:
            self.fault = "limit"
            return False, "limit"
        if self.fault == "stall":
            # 堵转必须显式清除，设新目标不能自动恢复
            return False, "stall"
        self.target = deg
        self.fault = None
        return True, None

    def clear_fault(self) -> None:
        self.fault = None

    def tick(self) -> bool:
        if self.fault:
            return False
        diff = self.target - self.current
        if abs(diff) <= self.tolerance_deg:
            self.current = self.target
            self.writes += 1
            return False
        step = (1 if diff > 0 else -1) * min(self.step_deg, abs(diff))
        self.current += step
        self.writes += 1
        return True

    def sample_current(self, amps: float) -> bool:
        if self.stall_a > 0 and amps > self.stall_a:
            self.fault = "stall"
            return False
        return True

    @property
    def moving(self) -> bool:
        return abs(self.target - self.current) > self.tolerance_deg


# ---------------------------------------------------------------------------
# 1. 脉宽映射
# ---------------------------------------------------------------------------


def test_pulse_mapping_and_clamping():
    cal = ServoCal()
    assert cal.deg_to_us(0.0) == 500
    assert cal.deg_to_us(90.0) == 1500
    assert cal.deg_to_us(180.0) == 2500
    assert cal.deg_to_us(-20.0) == 500, "下限外夹紧"
    assert cal.deg_to_us(400.0) == 2500, "上限外夹紧"


def test_pulse_mapping_custom_range():
    cal = ServoCal(min_us=1000, max_us=2000, min_deg=-90.0, max_deg=90.0)
    assert cal.deg_to_us(-90.0) == 1000
    assert cal.deg_to_us(0.0) == 1500
    assert cal.deg_to_us(90.0) == 2000


# ---------------------------------------------------------------------------
# 2. 平滑渐变（无突跳）
# ---------------------------------------------------------------------------


def test_smooth_gradient_step_bounded():
    axis = ServoAxis(ServoCal())
    axis.attach(0.0)
    ok, _ = axis.set_target(60.0)
    assert ok
    last, max_step, ticks = 0.0, 0.0, 0
    while axis.tick() and ticks < 1000:
        max_step = max(max_step, abs(axis.current - last))
        last = axis.current
        ticks += 1
    assert max_step <= 2.5001, f"单步不得超 2.5°，实际 {max_step:.3f}°"
    assert ticks == 24, f"60°/2.5° 应为 24 拍，实际 {ticks}"
    assert abs(axis.current - 60.0) < 1e-3
    assert not axis.moving


def test_tolerance_snap_avoids_residual():
    axis = ServoAxis(ServoCal(), step_deg=2.5, tolerance_deg=0.5)
    axis.attach(0.0)
    axis.set_target(1.0)  # 0.4° 残差落在容限内
    axis.tick()
    assert axis.current == 1.0, "容限内直接咬合到目标"


# ---------------------------------------------------------------------------
# 3. 限位与堵转
# ---------------------------------------------------------------------------


def test_limit_rejection_keeps_position():
    axis = ServoAxis(ServoCal())
    axis.attach(30.0)
    ok, reason = axis.set_target(200.0)
    assert not ok and reason == "limit"
    assert axis.fault == "limit"
    assert axis.current == 30.0, "被拒后位置不变"
    axis.tick()
    assert axis.current == 30.0, "fault 状态下不推进"


def test_invalid_target_rejected():
    axis = ServoAxis(ServoCal())
    ok, reason = axis.set_target(float("nan"))
    assert not ok and reason == "invalid"


def test_stall_detection_stops_motion():
    axis = ServoAxis(ServoCal(), stall_a=1.2)
    axis.attach(10.0)
    assert axis.sample_current(0.5) is True
    assert axis.sample_current(1.8) is False, "超阈值触发堵转"
    assert axis.fault == "stall"
    ok, reason = axis.set_target(20.0)
    assert ok is False and reason == "stall", "堵转未清除前不接受新目标"
    axis.tick()
    assert axis.current == 10.0, "堵转后不再动作"
    axis.clear_fault()
    assert axis.set_target(20.0)[0] is True, "显式清除后可恢复"
    axis.tick()
    assert axis.current > 10.0, "恢复后正常运动"


# ---------------------------------------------------------------------------
# 4. 多轴并行
# ---------------------------------------------------------------------------


def test_multi_axis_parallel_reach():
    cal = ServoCal()
    pan, tilt = ServoAxis(cal), ServoAxis(cal)
    pan.attach(10.0)
    tilt.attach(10.0)
    assert pan.set_target(100.0)[0] and tilt.set_target(40.0)[0]
    waited = 0
    while (pan.moving or tilt.moving) and waited <= 3000:
        pan.tick()
        tilt.tick()
        waited += 20
    assert waited <= 3000, "两轴应在超时内到位"
    assert abs(pan.current - 100.0) < 0.01 and abs(tilt.current - 40.0) < 0.01
    assert not pan.moving and not tilt.moving


def test_multi_axis_partial_reject_still_moves_other():
    cal = ServoCal()
    pan, tilt = ServoAxis(cal), ServoAxis(cal)
    pan.attach(10.0)
    tilt.attach(10.0)
    results = [pan.set_target(200.0), tilt.set_target(40.0)]
    assert results[0][0] is False and results[0][1] == "limit"
    assert results[1][0] is True, "一轴越限不影响另一轴"
    while tilt.moving:
        tilt.tick()
    assert abs(tilt.current - 40.0) < 0.01
