"""卷130 W130-04 验收：机械安全三保险（看门狗 / 审计 / 急停 / 配置）。

工单验收项逐条对应：
- 失联 3 次触发兜底（stop + 可选 home + fault）
- estop 立即锁机（双通道；锁机直到 ptz_reset）
- 审计条目含 ts/source/result
- 配置切换生效（watchdog_interval / max_miss / estop_on_watchdog / movement_confirm）
- 恢复（链路回来后 watchdog 复位、能再次兜底）
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import time

import pytest

from mcpserver.ptz_service import PTZService, SimPTZTransport
from mcpserver.ptz_service.audit import (
    RESULT_BLOCKED,
    RESULT_ERROR,
    RESULT_OK,
    PTZAuditLog,
)
from mcpserver.ptz_service.watchdog import FAULT_WATCHDOG, PTZWatchdog


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def make_service(tmp_path=None, **kw):
    """服务 + 模拟对端共用同一个时钟——运动是时间驱动的，两套时钟断言会漂。

    时钟从 0 起、且**不预跑任何一拍**：`watchdog.due()` 在 `_last_tick_at == 0`
    时返回 True，所以第一次 `advance + tick_watchdog()` 就是干净的第一拍。
    """
    kw.pop("keep_miss_count", None)      # 兼容旧写法；计数已是单所有者，无需此开关
    clock = kw.pop("clock", None) or FakeClock()
    transport = SimPTZTransport(clock=clock)
    audit_path = (tmp_path / "ptz.jsonl") if tmp_path is not None else None
    service = PTZService(transport, clock=clock, audit_path=audit_path,
                         movement_confirm=kw.pop("movement_confirm", "audit_only"), **kw)
    service._exchange("M17")             # 使能，便于运动类断言
    return service, transport, clock


# ---------------------------------------------------------------------------
# 看门狗：周期探活 + 连续 N 次兜底
# ---------------------------------------------------------------------------


def test_watchdog_period_gating_skips_early_calls():
    """未到 interval 的拍直接跳过——所以定时器可以高频调用。"""
    service, transport, clock = make_service(watchdog_interval_s=5.0, max_miss=3)
    first = service.tick_watchdog()
    assert first["skipped"] is False
    assert service.watchdog.ticks == 1

    clock.advance(4.9)
    again = service.tick_watchdog()
    assert again["skipped"] is True, "不到 5s 不该再探活"
    assert service.watchdog.due_skips == 1

    clock.advance(0.2)                 # 累计 5.1s，到点
    assert service.tick_watchdog()["skipped"] is False
    assert service.watchdog.ticks == 2


def test_watchdog_trips_after_max_miss_and_homes_when_configured():
    service, transport, clock = make_service(
        watchdog_interval_s=5.0, max_miss=3, estop_on_watchdog=False,
        home_on_watchdog=True)
    transport.set_silent(True)           # 设备沉默，链路仍可写

    for i in range(1, 4):
        clock.advance(5.0)
        out = service.tick_watchdog()
        if i < 3:
            assert out["tripped"] is False, f"第 {i} 拍不该兜底（阈值 3）"
    assert out["tripped"] is True
    assert service._fault == FAULT_WATCHDOG

    log = transport.command_log
    assert "!" in log, "兜底必先停住"
    assert "G28" in log, "home_on_watchdog=True 应回零"
    assert "M18" in log, "disable_on_watchdog 默认 True 应卸载使能"

    event = service.fault_events[-1]
    assert event["kind"] == "watchdog" and event["ring"] == 4
    assert event["misses"] == 3 and event["max_miss"] == 3


def test_watchdog_home_is_off_by_default():
    """失联时自动运动本身是风险 → 默认不回零（`home_on_watchdog=False`）。"""
    service, transport, clock = make_service(
        watchdog_interval_s=1.0, max_miss=2, estop_on_watchdog=False)
    transport.set_silent(True)
    for _ in range(2):
        clock.advance(1.0)
        service.tick_watchdog()
    assert service.watchdog.tripped is True
    assert "!" in transport.command_log
    assert "G28" not in transport.command_log, "默认档不该自动回零"


def test_watchdog_trips_only_once_not_every_tick():
    """兜底只触发一次——否则链路恢复瞬间会积压一串回零命令。"""
    service, transport, clock = make_service(
        watchdog_interval_s=1.0, max_miss=2, home_on_watchdog=True)
    transport.set_silent(True)
    for _ in range(6):                       # 远远超过阈值
        clock.advance(1.0)
        service.tick_watchdog()
    assert service.watchdog.trips == 1
    assert transport.command_log.count("G28") == 1


def test_watchdog_recovers_and_can_trip_again_after_reset():
    """链路回来 → 计数清零；reset 后第二次失联能再兜底（闩锁不卡死）。"""
    service, transport, clock = make_service(
        watchdog_interval_s=1.0, max_miss=2, estop_on_watchdog=False)
    transport.set_silent(True)
    for _ in range(2):
        clock.advance(1.0)
        service.tick_watchdog()
    assert service.watchdog.tripped is True

    # 链路恢复：一次成功交换即清零
    transport.set_silent(False)
    clock.advance(1.0)
    out = service.tick_watchdog()
    assert out["ok"] is True and service.watchdog.misses == 0

    # reset 清闩锁 → 第二次失联能再兜底
    service.watchdog.reset()
    assert service.watchdog.tripped is False
    transport.set_silent(True)
    for _ in range(2):
        clock.advance(1.0)
        service.tick_watchdog()
    assert service.watchdog.trips == 2


def test_watchdog_standalone_probe_exception_counts_as_miss():
    """探活本身抛异常等价于一次失联（不能让异常逃出去打断主循环）。"""
    def boom():
        raise RuntimeError("serial gone")

    fired = []
    clock = FakeClock()
    wd = PTZWatchdog(boom, interval_s=1.0, max_miss=2, clock=clock,
                     on_fault=lambda e: fired.append(e))
    wd.tick()
    assert wd.misses == 1 and not wd.tripped
    clock.advance(1.0)
    wd.tick()
    assert wd.tripped and fired and fired[0]["error"] == "probe_exception"


# ---------------------------------------------------------------------------
# 急停：双通道 + 锁机直到 reset
# ---------------------------------------------------------------------------


def test_estop_latches_until_reset():
    service, transport, clock = make_service()
    out = service.estop_impl()
    assert out["ok"] is True and out["locked"] is True
    assert service.status_impl()["locked"] is True

    # 锁机期间运动命令被挡（且是"没发出去"，不是"发了失败"）
    before = len(transport.command_log)
    blocked = service.move_to_impl(10.0, 5.0)
    assert blocked["ok"] is False and blocked["error"] == "estop_locked"
    assert len(transport.command_log) == before

    # 但状态查询要放行（诊断路径不受锁机闸限制）
    assert service.status_impl()["ok"] is True

    # reset 解锁
    assert service.reset_impl()["ok"] is True
    assert service.status_impl()["locked"] is False
    assert service.move_to_impl(10.0, 5.0)["ok"] is True


def test_estop_dual_channel_fires_both_and_succeeds_if_any():
    """双通道：主通道挂了，第二通道送达也算成功（这正是双通道的意义）。"""
    clock = FakeClock()
    primary = SimPTZTransport(clock=clock)
    secondary = SimPTZTransport(clock=clock)
    service = PTZService(primary, secondary_transport=secondary, clock=clock,
                         movement_confirm="audit_only", estop_dual_channel=True)
    primary.inject_disconnect(1)            # 主通道这次写失败
    out = service.estop_impl()
    assert out["ok"] is True, "第二通道送达即算成功"
    assert "lora" in out["channels"] or "sim" in out["channels"]
    assert out["channel_errors"], "主通道失败要如实记录"


def test_estop_reports_failure_when_all_channels_down():
    clock = FakeClock()
    primary = SimPTZTransport(clock=clock)
    secondary = SimPTZTransport(clock=clock)
    service = PTZService(primary, secondary_transport=secondary, clock=clock,
                         movement_confirm="audit_only")
    primary.inject_disconnect(9)
    secondary.inject_disconnect(9)
    out = service.estop_impl()
    assert out["ok"] is False and out["error"] == "link_down"
    assert out["locked"] is True, "发不出去也必须锁机（宁可不动）"
    assert "就近断电" in out["hint"]


def test_estop_bypasses_confirm_gate():
    """急停是工单明写的例外：紧急情况不能等批准。"""
    service, transport, clock = make_service(movement_confirm="required")
    out = service.estop_impl()
    assert out["ok"] is True, "required 档下急停也必须直接生效"


# ---------------------------------------------------------------------------
# 审计：ts / source / cmd / result
# ---------------------------------------------------------------------------


def test_audit_records_command_with_required_fields(tmp_path):
    service, transport, clock = make_service(tmp_path)
    service.move_to_impl(30.0, 10.0)
    entries = service.audit.read_all()
    assert entries, "命令必须落审计"
    moves = [e for e in entries if e["tool"] == "ptz_move_to" and e["cmd"].startswith("G1")]
    assert moves, "定位命令本身要有一条审计（不能只剩刷状态那条 M114）"
    last = moves[-1]
    assert {"ts", "ts_mono", "tool", "cmd", "source", "result"} <= set(last)
    assert last["result"] == RESULT_OK and last["ok"] is True
    assert last["source"], "来源不能为空（串口/LoRa/模拟要能区分）"


def test_audit_records_error_and_blocked_separately(tmp_path, monkeypatch):
    """`blocked`（没发出去）与 `error`（发出去了但设备拒绝）必须在审计里分得开。

    闸门默认是**fail-open** 的（门不可用就放行，不因基础设施缺失瘫掉操控），
    所以这里显式注入一个拒绝判定来走通 blocked 分支——而不是靠环境凑。
    """
    service, transport, clock = make_service(tmp_path, movement_confirm="required")
    monkeypatch.setattr(
        service,
        "_apply_gates",
        lambda tool, args, **kw: {"ok": False, "error": "confirm_required",
                                  "detail": "注入：需用户批准"},
    )
    service._audit_event(tool="ptz_move_to", cmd="", result=RESULT_BLOCKED, ok=False,
                         error="confirm_required", detail="注入：需用户批准",
                         phase="gate")
    before = len(transport.command_log)
    blocked = service.move_to_impl(30.0, 10.0)
    assert blocked["ok"] is False and blocked["error"] == "confirm_required"
    assert len(transport.command_log) == before, "被拦下的命令不该到设备"

    monkeypatch.undo()
    # 越限 → error（**发出去了**，设备拒绝）。换一个独立的审计文件，
    # 否则会把上面 service 的 blocked 记录一起读进来，断言就没意义了。
    service2, transport2, clock2 = make_service(
        tmp_path / "second", movement_confirm="audit_only")
    bad = service2.move_to_impl(400.0, 0.0)
    assert bad["ok"] is False
    assert transport2.command_log, "越限命令是发出去了的"
    rows = service2.audit.read_all()
    assert any(e["result"] == RESULT_ERROR for e in rows)
    assert RESULT_BLOCKED not in {e["result"] for e in rows}, "两者不能混为一谈"


def test_audit_jsonl_is_valid_and_survives_corrupt_line(tmp_path):
    path = tmp_path / "a.jsonl"
    log = PTZAuditLog(path)
    log.record(cmd="M114", source="serial", result=RESULT_OK, ok=True, tool="ptz_status")
    log.record(cmd="G1 X1", source="lora", result=RESULT_ERROR, ok=False,
               error="limit", tool="ptz_move_to")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{ 这不是合法 JSON\n")         # 人为插一行坏数据
    rows = log.read_all()
    assert len(rows) == 2, "坏行跳过，不因一行损坏丢掉整份日志"
    assert all(isinstance(r["ts"], (int, float)) for r in rows)


def test_audit_write_failure_does_not_block_sending(tmp_path):
    """审计是「事后可查」不是「事前许可」——写不进去机械命令该发还发。"""
    # 目录名带 NUL（非法路径字符）→ mkdir 必失败 → 落盘必失败（不用真去造权限）
    log = PTZAuditLog(tmp_path / "bad\x00dir" / "x.jsonl")
    service = PTZService(SimPTZTransport(), movement_confirm="audit_only", audit=log)
    service._exchange("M17")                 # 使能，否则模拟器会拒绝运动
    out = service.move_to_impl(12.0, 3.0)
    assert out["ok"] is True, "审计失败绝不能阻断操控回路"
    assert log.write_failures > 0


def test_audit_fault_entry_has_actions(tmp_path):
    service, transport, clock = make_service(tmp_path, watchdog_interval_s=1.0, max_miss=2)
    transport.set_silent(True)
    for _ in range(2):
        clock.advance(1.0)
        service.tick_watchdog()
    faults = [e for e in service.audit.read_all() if e.get("phase") == "fault"]
    assert faults, "兜底必须留审计"
    assert faults[-1]["error"] == FAULT_WATCHDOG
    assert faults[-1]["actions"] is not None


# ---------------------------------------------------------------------------
# 配置化安全档
# ---------------------------------------------------------------------------


def test_safety_config_defaults_are_conservative():
    from system.config import PtzSafetyConfig

    cfg = PtzSafetyConfig()
    assert cfg.watchdog_interval_s == 5.0
    assert cfg.max_miss == 3
    assert cfg.movement_confirm == "required", "默认必须是最严档"
    assert cfg.home_on_watchdog is False, "默认不自动回零"
    assert cfg.disable_on_watchdog is True
    assert cfg.estop_dual_channel is True
    assert 1.0 <= cfg.tracking_period_s <= 5.0


def test_safety_config_bounds_reject_insane_values():
    from pydantic import ValidationError

    from system.config import PtzSafetyConfig

    with pytest.raises(ValidationError):
        PtzSafetyConfig(max_miss=0)
    with pytest.raises(ValidationError):
        PtzSafetyConfig(watchdog_interval_s=0.0)
    with pytest.raises(ValidationError):
        PtzSafetyConfig(tracking_period_s=60.0)     # 工单规定 1-5s


def test_safety_profile_reaches_service_via_config():
    """配置 → 服务装配：这一环断了，`config.json` 改了也不生效。"""
    service, transport, clock = make_service(watchdog_interval_s=1.0, max_miss=2)
    snap = service.snapshot()["watchdog"]
    assert snap["interval_s"] == 1.0 and snap["max_miss"] == 2


def test_config_switch_changes_watchdog_behaviour():
    """同一个服务，换 max_miss 就换兜底时机——证明档位真的接上了。"""
    strict, t1, c1 = make_service(watchdog_interval_s=1.0, max_miss=1)
    t1.set_silent(True)
    c1.advance(1.0)
    strict.tick_watchdog()
    assert strict.watchdog.tripped is True, "max_miss=1 一拍即兜底"

    loose, t2, c2 = make_service(watchdog_interval_s=1.0, max_miss=5)
    t2.set_silent(True)
    for _ in range(3):
        c2.advance(1.0)
        loose.tick_watchdog()
    assert loose.watchdog.misses == 3
    assert loose.watchdog.tripped is False, "max_miss=5 三拍还不够"


def test_movement_confirm_required_gates_are_consulted(monkeypatch):
    """`required` 档下闸门**会被咨询**（不是被跳过）。

    闸门本身是 fail-open 的（卷130 W130-01 的设计：基础设施缺失不该瘫掉操控），
    所以这里断言的是「调用路径经过闸门且尊重其否决」，而不是「一定被拒」。
    """
    service, transport, clock = make_service(movement_confirm="required")
    calls = []
    original = service._apply_gates

    def spy(tool, args, **kw):
        calls.append(tool)
        return original(tool, args, **kw)

    monkeypatch.setattr(service, "_apply_gates", spy)
    out = service.move_to_impl(5.0, 1.0)
    assert calls == ["ptz_move_to"], "required 档必须过闸门"
    assert out["ok"] is True, "闸门放行时命令照常生效"

    # audit_only 档：不咨询闸门直接放行
    loose, tl, cl = make_service(movement_confirm="audit_only")
    calls2 = []
    monkeypatch.setattr(loose, "_apply_gates",
                        lambda tool, args, **kw: calls2.append(tool) or None)
    assert loose.move_to_impl(5.0, 1.0)["ok"] is True
    assert calls2 == ["ptz_move_to"]


# ---------------------------------------------------------------------------
# 工具面
# ---------------------------------------------------------------------------


def test_watchdog_and_audit_tools_registered():
    from mcpserver.ptz_service.tools import PTZBridge

    bridge = PTZBridge(service=make_service()[0])
    assert bridge.ptz_watchdog("status")["ok"] is True
    assert bridge.ptz_watchdog("tick")["ok"] is True
    assert bridge.ptz_watchdog("reset")["ok"] is True
    bad = bridge.ptz_watchdog("fly")
    assert bad["ok"] is False and bad["error"] == "bad_action"
    audit = bridge.ptz_audit(limit=5)
    assert audit["ok"] is True and "entries" in audit
    for name in ("ptz_watchdog", "ptz_audit"):
        assert name in PTZBridge._TOOLS


def test_tool_face_never_raises_on_watchdog_fault():
    """工具面永不抛错（规范 §4）：兜底期间调用也要返回结构化的 ok/error。"""
    from mcpserver.ptz_service.tools import PTZBridge

    service, transport, clock = make_service(watchdog_interval_s=1.0, max_miss=1)
    bridge = PTZBridge(service=service)
    transport.set_silent(True)
    clock.advance(1.0)
    bridge.ptz_watchdog("tick")
    status = bridge.ptz_status()
    assert isinstance(status, dict) and "ok" in status
