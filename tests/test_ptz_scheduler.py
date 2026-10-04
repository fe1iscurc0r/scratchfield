"""卷130 W130-03 验收：云台任务编排（TLE 跟踪 / 扇扫循环 / 记忆位 / 安全联动）。

工单验收项逐条对应：
- 跟踪任务发出正确移动序列
- 扇扫循环正确
- 记忆位存取（本地 JSON）
- 中断 → 回零（可配置 hold/home）
- `pytest` 全绿（≥5 用例）

**关于 TLE 精度**：`sgp4` 未安装时本模块会**拒绝启动跟踪任务**（`no_propagator`），
这是刻意的——宁可报错也不返回"看着像角度其实是编的"数值。测试覆盖两条路径：
有 sgp4 走真 SGP4，没有则用显式 `tracking_source="simple"` 跑编排链路。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
from datetime import datetime, timedelta, timezone

import pytest

from mcpserver.ptz_service import (
    FAIL_HOLD,
    FAIL_HOME,
    TASK_GOTO_MEM,
    TASK_SCAN,
    TASK_TRACK,
    PTZScheduler,
    PTZService,
    SimPTZTransport,
    SiteLocation,
    Tle,
    make_propagator,
    sgp4_available,
)
from mcpserver.ptz_service.scheduler import MemoryStore

#: 示例 TLE（ISS 形态的两行根数；用于几何/编排验证，不用于真实指向）
TLE_L1 = "1 25544U 98067A   26261.50000000  .00016717  00000-0  10270-3 0  9003"
TLE_L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
SITE = SiteLocation(39.9042, 116.4074, 50.0)


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def _service(tmp_path, *, tracking_source: str = "simple", **kw):
    clock = FakeClock()
    sim = SimPTZTransport(clock=clock)
    svc = PTZService(sim, clock=clock, wall_clock=clock,
                     movement_confirm="audit_only",
                     tracking_source=tracking_source,
                     memory_path=tmp_path / "memory.json",
                     audit_path=tmp_path / "audit.ndjson", **kw)
    svc._exchange("M17")                       # 使能
    return svc, clock


# ---------------------------------------------------------------------------
# 几何 / TLE
# ---------------------------------------------------------------------------


def test_tle_parse_and_epoch():
    tle = Tle.parse("ISS", f"{TLE_L1}\n{TLE_L2}")
    assert tle.line1.startswith("1 ") and tle.line2.startswith("2 ")
    assert tle.epoch is not None and tle.epoch.tzinfo is not None
    # YYDDD 滚动世纪：26 → 2026，261 → 9 月 18 日
    assert tle.epoch.year == 2026 and tle.epoch.month == 9


def test_tle_parse_rejects_garbage():
    for bad in ("", "hello", TLE_L1, TLE_L2, f"{TLE_L2}\n{TLE_L1}"):
        with pytest.raises(ValueError):
            Tle.parse("x", bad)


def test_look_angles_are_geometrically_sane():
    """不变量：方位 [0,360)、俯仰 [-90,90]、斜距在 LEO 合理区间。"""
    tle = Tle.parse("ISS", f"{TLE_L1}\n{TLE_L2}")
    prop = make_propagator(tle, "simple")
    assert prop.available
    for minutes in range(0, 24 * 60, 53):
        az, el, rng = prop.look_angles(SITE, tle.epoch + timedelta(minutes=minutes))
        assert 0.0 <= az < 360.0, az
        assert -90.0 <= el <= 90.0, el
        assert 300.0 < rng < 15000.0, rng


def test_sgp4_available_matches_import():
    """`sgp4_available()` 必须如实反映 import 结果（可装可不装，不能编）。"""
    try:
        import sgp4  # noqa: F401,PLC0415
        assert sgp4_available() is True
    except ImportError:
        assert sgp4_available() is False


@pytest.mark.skipif(not sgp4_available(), reason="未安装 sgp4（MIT）")
def test_sgp4_reaches_pass_geometry():
    """真 SGP4：24 小时内应出现过境（高仰角、近距离）。"""
    tle = Tle.parse("ISS", f"{TLE_L1}\n{TLE_L2}")
    prop = make_propagator(tle, "sgp4")
    assert prop.available
    best_el, best_rng = -90.0, 1e9
    for minutes in range(0, 24 * 60, 2):
        _az, el, rng = prop.look_angles(SITE, tle.epoch + timedelta(minutes=minutes))
        if el > best_el:
            best_el, best_rng = el, rng
    assert best_el > 30.0, f"24 小时内应有高仰角过境，实测 {best_el:.1f}°"
    assert best_rng < 1500.0, f"高仰角时斜距应 <1500km，实测 {best_rng:.0f}km"


def test_track_refuses_without_propagator(tmp_path):
    """**核心安全断言**：没有传播器时拒绝启动，不给假角度。"""
    svc, _clock = _service(tmp_path, tracking_source="sgp4")
    if sgp4_available():
        pytest.skip("本机装了 sgp4；此用例验的是缺失时的拒绝路径")
    out = svc.task_add_impl(TASK_TRACK, {"tle_line1": TLE_L1, "tle_line2": TLE_L2})
    assert out["ok"] is False
    assert out["error"] == "no_propagator"
    assert out["task"]["state"] == "failed"
    assert "sgp4" in out["hint"]


# ---------------------------------------------------------------------------
# 跟踪任务：发出正确移动序列
# ---------------------------------------------------------------------------


def test_track_emits_moves_at_the_configured_cadence(tmp_path):
    """跟踪节拍 1–5s：每过一个周期产出一条指令，且角度随时间变化。"""
    svc, clock = _service(tmp_path, tracking_source="simple", tracking_period_s=1.0)
    out = svc.task_add_impl(TASK_TRACK, {"name": "ISS", "tle_line1": TLE_L1,
                                         "tle_line2": TLE_L2})
    assert out["ok"] is True
    tid = out["task"]["task_id"]

    emitted = []
    for _ in range(6):
        res = svc.tick_scheduler()
        emitted.extend(res["instructions"])
        clock.advance(1.0)                     # 正好过一个节拍

    assert len(emitted) == 6, f"6 个节拍应产 6 条指令，实得 {len(emitted)}"
    assert all(i["kind"] == "track" for i in emitted)
    # 角度在动（不是每次都同一个点）
    angles = {(round(i["az"], 3), round(i["el"], 3)) for i in emitted}
    assert len(angles) >= 4, f"跟踪点应随时间变化，实得 {len(angles)} 个不同点"

    rep = svc.task_report_impl(tid)
    assert rep["ok"] is True and rep["points"] == 6
    assert rep["propagator"] == "simple"
    assert rep["site"]["lat_deg"] == pytest.approx(39.9042)


def test_track_respects_period_gating(tmp_path):
    """周期内的高频 tick **不产出**指令——否则会用同一点刷爆链路。"""
    svc, clock = _service(tmp_path, tracking_source="simple", tracking_period_s=3.0)
    svc.task_add_impl(TASK_TRACK, {"tle_line1": TLE_L1, "tle_line2": TLE_L2})
    first = svc.tick_scheduler()
    assert first["sent"] == 1
    for _ in range(5):                         # 都在 3s 周期内
        clock.advance(0.1)
        assert svc.tick_scheduler()["sent"] == 0
    clock.advance(3.0)
    assert svc.tick_scheduler()["sent"] == 1    # 到点后才再发


def test_tracking_period_is_clamped_to_workorder_range(tmp_path):
    """工单规定 1–5 s 可配：越界值要被夹住，而不是照单全收。"""
    assert PTZScheduler(tracking_period_s=0.01).tracking_period_s == 1.0
    assert PTZScheduler(tracking_period_s=999.0).tracking_period_s == 5.0
    assert PTZScheduler(tracking_period_s=3.0).tracking_period_s == 3.0


# ---------------------------------------------------------------------------
# 跟踪中断 → 可配置的 hold / home
# ---------------------------------------------------------------------------


def test_track_failure_holds_by_default(tmp_path):
    """默认 `hold`：中断后任务结束但**不发任何动作**（机构原地保持）。"""
    svc, clock = _service(tmp_path, tracking_source="simple", track_fail_action=FAIL_HOLD)
    out = svc.task_add_impl(TASK_TRACK, {"tle_line1": TLE_L1, "tle_line2": TLE_L2,
                                         "max_link_errors": 2})
    tid = out["task"]["task_id"]
    # 让链路"通但有故障"的方式：直接把 scheduler 里的传播器换成一个必炸的
    class Boom:
        kind = "boom"

        def look_angles(self, *a, **k):
            raise RuntimeError("TLE 源挂了")

    svc.scheduler._propagators[tid] = Boom()
    clock.advance(5.0)
    emitted = []
    for _ in range(5):
        emitted.extend(svc.tick_scheduler()["instructions"])
        clock.advance(5.0)

    assert emitted == [], "hold 策略下发动作数应为 0"
    task = svc.scheduler.get_task(tid)
    assert task["state"] == "done"
    assert "tle_failure" in task["error"]


def test_track_failure_homes_when_configured(tmp_path):
    """`home`：中断时产出一条回零指令——**可配置**是工单明写的。"""
    svc, clock = _service(tmp_path, tracking_source="simple", track_fail_action=FAIL_HOME)
    out = svc.task_add_impl(TASK_TRACK, {"tle_line1": TLE_L1, "tle_line2": TLE_L2,
                                         "max_link_errors": 1})
    tid = out["task"]["task_id"]

    class Boom:
        kind = "boom"

        def look_angles(self, *a, **k):
            raise RuntimeError("boom")

    svc.scheduler._propagators[tid] = Boom()
    clock.advance(5.0)
    emitted = []
    for _ in range(3):
        emitted.extend(svc.tick_scheduler()["instructions"])
        clock.advance(5.0)
    assert len(emitted) == 1 and emitted[0]["kind"] == "home", emitted
    assert "track_interrupted" in emitted[0]["reason"]


def test_default_fail_action_is_hold_and_illegal_falls_back(tmp_path):
    assert PTZScheduler().track_fail_action == FAIL_HOLD
    assert PTZScheduler(track_fail_action="teleport").track_fail_action == FAIL_HOLD
    assert PTZScheduler(track_fail_action="HOME").track_fail_action == FAIL_HOME


# ---------------------------------------------------------------------------
# 扇扫循环
# ---------------------------------------------------------------------------


def test_scan_loop_visits_start_to_end_repeatedly(tmp_path):
    """扇扫循环：0→30 步 10 = 4 点/轮，连续多轮。"""
    svc, clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 30, "step": 10,
                                        "dwell": 0.0})
    assert out["ok"] is True
    tid = out["task"]["task_id"]

    points = []
    for _ in range(10):                        # 10 次 tick = 10 个点（无驻留）
        points.extend(round(i["az"], 3) for i in svc.tick_scheduler()["instructions"])
        clock.advance(0.01)

    assert points == [0.0, 10.0, 20.0, 30.0, 0.0, 10.0, 20.0, 30.0, 0.0, 10.0], points
    assert svc.scheduler.get_task(tid)["state"] == "running"   # 无限循环


def test_scan_loop_honours_dwell(tmp_path):
    """驻留：每个点之间要等够 dwell 秒。"""
    svc, clock = _service(tmp_path)
    svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 20, "step": 10, "dwell": 2.0})
    assert svc.tick_scheduler()["sent"] == 1        # 第一个点
    for _ in range(10):
        clock.advance(0.1)
        assert svc.tick_scheduler()["sent"] == 0    # 驻留中
    clock.advance(2.0)
    assert svc.tick_scheduler()["sent"] == 1        # 驻留结束


def test_scan_loops_limit_stops_the_task(tmp_path):
    """`loops=N` 跑满 N 轮就结束——`loops_done` 与实发点数必须自洽。"""
    svc, clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 20, "step": 10,
                                        "dwell": 0.0, "loops": 2})
    tid = out["task"]["task_id"]
    sent = 0
    for _ in range(20):
        sent += svc.tick_scheduler()["sent"]
        clock.advance(0.01)
    task = svc.scheduler.get_task(tid)
    assert sent == 6, sent                      # 3 点 × 2 轮
    assert task["state"] == "done"
    assert task["loops_done"] == 2
    assert task["moves"] == 6


def test_scan_rejects_bad_params(tmp_path):
    svc, _clock = _service(tmp_path)
    assert svc.task_add_impl(TASK_SCAN, {"start_az": 0})["error"] == "missing_scan_params"
    assert svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 10,
                                         "step": 0})["error"] == "bad_step"


def test_scan_duration_s_ends_the_task(tmp_path):
    """`schedule.duration_s` 到期结束——无限循环要有刹车。"""
    svc, clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 40, "step": 10,
                                        "dwell": 0.0},
                            {"duration_s": 0.5})
    tid = out["task"]["task_id"]
    for _ in range(5):
        svc.tick_scheduler()
        clock.advance(0.1)
    clock.advance(1.0)
    svc.tick_scheduler()
    assert svc.scheduler.get_task(tid)["state"] == "done"


# ---------------------------------------------------------------------------
# 记忆位（本地 JSON 持久化）
# ---------------------------------------------------------------------------


def test_memory_positions_persist_across_instances(tmp_path):
    """记忆位必须**掉电不丢**：新实例读同一文件应看到旧位。"""
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    store.set("park", 180.0, 45.0)
    assert path.exists()

    reopened = MemoryStore(path)
    got = reopened.get("park")
    assert got is not None and got["az"] == 180.0 and got["el"] == 45.0
    assert reopened.list_slots() == ["park"]

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["slots"]["park"]["az"] == 180.0


def test_memory_corrupt_file_does_not_break_startup(tmp_path):
    """坏文件不阻断启动——记忆位丢了是麻烦，服务起不来是事故。"""
    path = tmp_path / "memory.json"
    path.write_text("{not json at all", encoding="utf-8")
    store = MemoryStore(path)
    assert store.list_slots() == []
    assert store.load_errors == 1
    store.set("a", 1.0, 2.0)                   # 仍可写
    assert MemoryStore(path).get("a") is not None


def test_memory_delete_and_missing_slot(tmp_path):
    store = MemoryStore(tmp_path / "memory.json")
    store.set("a", 1.0, 2.0)
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert MemoryStore(tmp_path / "memory.json").list_slots() == []


def test_goto_mem_task_moves_to_the_stored_point(tmp_path):
    svc, clock = _service(tmp_path)
    svc.memory_set_impl("park", 123.0, 33.0)
    out = svc.task_add_impl(TASK_GOTO_MEM, {"slot": "park"})
    assert out["ok"] is True
    emitted = svc.tick_scheduler()["instructions"]
    assert len(emitted) == 1
    assert emitted[0]["az"] == 123.0 and emitted[0]["el"] == 33.0
    assert emitted[0]["kind"] == "goto"
    assert svc.scheduler.get_task(out["task"]["task_id"])["state"] == "done"


def test_goto_mem_rejects_unknown_slot(tmp_path):
    svc, _clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_GOTO_MEM, {"slot": "nope"})
    assert out["ok"] is False and out["error"] == "slot_not_found"


def test_task_schema_matches_workorder(tmp_path):
    """任务模型必须含工单规定的四个字段。"""
    svc, _clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 10, "step": 5})
    task = out["task"]
    for key in ("task_id", "type", "params", "schedule"):
        assert key in task, f"任务模型缺字段 {key}"
    assert task["type"] == TASK_SCAN


def test_bad_task_type_rejected(tmp_path):
    svc, _clock = _service(tmp_path)
    out = svc.task_add_impl("teleport", {})
    assert out["ok"] is False and out["error"] == "bad_type"


# ---------------------------------------------------------------------------
# 安全联动（W130-03 ×W130-04）
# ---------------------------------------------------------------------------


def test_estop_lock_aborts_all_tasks_and_sends_nothing(tmp_path):
    """**最高优先级断言**：锁机时自动任务既不发指令、也被停掉。

    自动任务若能绕过锁机，`ptz_estop` 就不是最高优先了。
    """
    svc, clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 90, "step": 30,
                                        "dwell": 0.0})
    tid = out["task"]["task_id"]
    svc.tick_scheduler()
    assert svc.scheduler.get_task(tid)["state"] == "running"

    svc.estop_impl()
    res = svc.tick_scheduler()
    assert res["locked"] is True
    assert res["sent"] == 0
    assert res["instructions"] == []
    assert svc.scheduler.get_task(tid)["state"] == "aborted"

    # 复位后可以重新开始（不是永久禁用）
    svc.reset_impl()
    assert svc.tick_scheduler()["locked"] is False


def test_stop_all_and_stop_single_task(tmp_path):
    svc, clock = _service(tmp_path)
    a = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 90, "step": 30,
                                      "dwell": 0.0})["task"]["task_id"]
    b = svc.task_add_impl(TASK_SCAN, {"start_az": 10, "end_az": 50, "step": 20,
                                      "dwell": 0.0})["task"]["task_id"]
    stopped = svc.task_stop_impl(a)
    assert stopped["ok"] and stopped["task"]["state"] == "aborted"
    assert svc.scheduler.get_task(b)["state"] == "running"

    allstop = svc.task_stop_impl("")           # 空 = 停全部
    assert allstop["count"] == 1
    assert svc.scheduler.get_task(b)["state"] == "aborted"


def test_watchdog_fault_stops_automation(tmp_path):
    """看门狗兜底时自动任务也必须停——否则兜底的回零会被跟踪任务立刻顶掉。"""
    svc, clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 90, "step": 30,
                                        "dwell": 0.0})
    tid = out["task"]["task_id"]
    svc.transport.set_silent(True)
    for _ in range(svc.max_miss + 1):
        svc.tick_watchdog()
        clock.advance(svc.watchdog_interval_s + 0.1)
    assert svc.watchdog.tripped is True
    # 看门狗触发后编排的推进必须停掉在跑的任务
    svc.tick_scheduler()
    assert svc.scheduler.get_task(tid)["state"] != "running"


def test_automation_wins_arbitration_when_no_manual(tmp_path):
    """无手动干预时，自动任务能拿到控制权（不是被仲裁永久挡住）。"""
    svc, _clock = _service(tmp_path)
    out = svc.task_add_impl(TASK_SCAN, {"start_az": 0, "end_az": 20, "step": 10,
                                        "dwell": 0.0})
    assert out["ok"]
    assert svc.tick_scheduler()["sent"] >= 1


# ---------------------------------------------------------------------------
# 工具面
# ---------------------------------------------------------------------------


def test_task_tools_are_registered_and_never_raise(tmp_path):
    from mcpserver.ptz_service.tools import PTZBridge

    svc, _clock = _service(tmp_path)
    bridge = PTZBridge(service=svc)
    for name in ("ptz_task", "ptz_track_source", "ptz_memory"):
        assert name in PTZBridge._TOOLS

    assert bridge.ptz_task("list")["ok"] is True
    assert bridge.ptz_task("nonsense")["ok"] is False
    assert bridge.ptz_task("report", task_id="missing")["ok"] is False

    # 各种畸形输入都不能抛错
    assert bridge.ptz_task("add", type="track", params={"tle_line1": "x",
                                                        "tle_line2": "y"})["ok"] is False
    assert bridge.ptz_task("add", type="track", params=None)["ok"] is False
    assert bridge.ptz_track_source()["ok"] is True
    assert bridge.ptz_memory("delete", slot="nope")["ok"] is False
    assert bridge.ptz_task("remove", task_id="")["ok"] is False


def test_scheduler_snapshot_reports_capability(tmp_path):
    svc, _clock = _service(tmp_path)
    snap = svc.snapshot()["scheduler"]
    assert "sgp4_available" in snap
    assert snap["tracking_source"] == "simple"
    assert snap["site"]["lat_deg"] == pytest.approx(39.9042)
    assert snap["memory_slots"] == []
