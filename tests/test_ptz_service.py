"""卷130 W130-01 验收：PTZ 执行器服务（工具面 / 连接抽象 / 安全门 / 状态缓存 / 心跳兜底）。

工单 W130-01 的验收项逐条对应：
- 模拟对端收到正确命令帧
- 心跳超时触发 stop
- Scope 隐藏 / 未经授权角色调 move 被拒
- 幂等 no-op
- LoRa 帧校验失败拒收 + 重传上限
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json
import time

import pytest

from mcpserver.ptz_service import (
    LoopbackRadioLink,
    LoraBridgeTransport,
    PTZBridge,
    PTZService,
    SimPTZTransport,
    decode_frame,
    encode_command,
    encode_reply,
    open_transport,
)
from mcpserver.ptz_service import service as svc_mod


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def make_service(**kw) -> tuple[PTZService, SimPTZTransport]:
    """服务 + 模拟对端共用同一个时钟——运动是时间驱动的，两套时钟断言会漂。"""
    clock = kw.pop("clock", None)
    transport = SimPTZTransport(**({"clock": clock} if clock is not None else {}))
    service = PTZService(transport, clock=clock or time.monotonic,
                         movement_confirm=kw.pop("movement_confirm", "audit_only"), **kw)
    service._exchange("M17")          # 使能，便于运动类断言
    return service, transport


# ---------------------------------------------------------------------------
# 连接抽象
# ---------------------------------------------------------------------------


def test_open_transport_backends():
    assert isinstance(open_transport("sim"), SimPTZTransport)
    assert isinstance(open_transport(""), SimPTZTransport)
    serial = open_transport("COM7@9600")
    assert serial.backend == "serial" and serial.port == "COM7" and serial.baudrate == 9600
    with pytest.raises(ValueError):
        open_transport("COM7@300")     # 工单规定 9600~115200


def test_lora_frame_checksum_and_length_guard():
    frame = encode_command("G1 X30 Y10 F5")
    assert frame.endswith(b"\n")
    body = decode_frame(frame)
    assert body is not None and body.startswith("PTZ ")
    # 校验和错 → 拒收
    bad = bytearray(frame)
    bad[-3] = ord("Z") if bad[-3] != ord("Z") else ord("Y")
    assert decode_frame(bytes(bad)) is None
    # 超 64B → 拒发
    with pytest.raises(ValueError):
        encode_command("X" * 80)


def test_lora_reply_decoding_keeps_firmware_echo_verbatim():
    from mcpserver.ptz_service.transport import decode_reply as dr

    assert dr(decode_frame(encode_reply("ok")) or "") == "ok"
    assert dr(decode_frame(encode_reply("error:limit")) or "") == "error:limit"


def test_lora_transport_retries_twice_then_gives_up():
    """工单要求：超时重传 2 次（合计最多 3 次尝试），失败如实报错。"""
    link = LoopbackRadioLink(drop_rate=1.0)
    t = LoraBridgeTransport(link, max_retry=2, timeout_s=0.0)
    with pytest.raises(Exception) as exc:
        t.send("M114")
    assert "已尝试 3 次" in str(exc.value)
    assert len(link.sent) == 3
    assert t.retries == 3


def test_lora_transport_rejects_corrupt_reply():
    link = LoopbackRadioLink(corrupt_rate=1.0)
    t = LoraBridgeTransport(link, max_retry=2, timeout_s=0.0)
    with pytest.raises(Exception):
        t.send("M114")
    assert t.bad_frames == 3          # 3 次尝试、每次都校验失败 → 全部计为拒收
    assert len(link.sent) == 3


# ---------------------------------------------------------------------------
# 工具面与命令语义
# ---------------------------------------------------------------------------


def test_move_sends_firmware_shaped_command():
    service, transport = make_service()
    out = service.move_to_impl(30.0, 10.0, speed=5.0)
    assert out["ok"] is True and out["noop"] is False
    moves = [l for l in transport.raw.lines if l.startswith("G1 ")]
    assert moves[-1] == "G1 X30.000 Y10.000 F5.000", transport.raw.lines
    assert service.state.snapshot()["known"] is True, "动作后应刷新状态缓存"


def test_move_is_idempotent_for_same_target():
    service, transport = make_service()
    first = service.move_to_impl(45.0, 0.0, speed=50.0)
    before = len(transport.raw.lines)
    second = service.move_to_impl(45.0, 0.0, speed=50.0)
    assert first["ok"] and first["noop"] is False
    assert second["ok"] is True and second["noop"] is True
    assert second["reason"] == "duplicate_target"
    assert len(transport.raw.lines) == before, "重复目标不得再下发（不空跑机构）"
    assert service.state.snapshot()["duplicate_moves"] == 1


def test_soft_limit_reject_surfaces_firmware_echo():
    service, _ = make_service()
    out = service.move_to_impl(400.0, 0.0)
    assert out["ok"] is False and out["error"] == "limit"      # 与固件回显逐字一致
    assert "hint" in out


def test_status_cache_and_sources():
    clock = FakeClock()
    service, _ = make_service(clock=clock)
    service.move_to_impl(10.0, 5.0, speed=50.0)
    clock.advance(1.0)                # 让运动走完（模拟对端是时间驱动的）
    status = service.status_impl()
    assert status["ok"] is True
    assert status["az_deg"] == 10.0 and status["el_deg"] == 5.0
    assert status["last_source"] == "sim"
    assert status["stale"] is False
    clock.advance(60.0)
    assert service.state.snapshot()["stale"] is True     # 超期要能看出来


def test_scan_walks_azimuth_by_step():
    service, transport = make_service()
    out = service.scan_impl(0.0, 30.0, 10.0, dwell=0.0)
    assert out["ok"] is True and out["count"] == 4
    assert out["points"] == [0.0, 10.0, 20.0, 30.0]
    moves = [l for l in transport.raw.lines if l.startswith("G1 ")]
    assert moves[-1].startswith("G1 X30.000 Y0.000"), moves[-1]
    bad = service.scan_impl(0.0, 30.0, 0.0)
    assert bad["ok"] is False and bad["error"] == "bad_step"


# ---------------------------------------------------------------------------
# 安全门（卷119 tool_gate / 卷124 Scope）
# ---------------------------------------------------------------------------


class _GateCfg:
    enabled = True
    audit_only = False
    sensitive_tools = ["ptz_move_to", "ptz_home", "ptz_scan", "ptz_stop"]
    sensitive_keywords = []
    allowlist = []
    breaker_threshold = 5
    breaker_window_seconds = 60


def test_confirm_gate_requires_approval_for_write_tools(monkeypatch):
    from apiserver.event_bus import tool_gate as tg

    monkeypatch.setattr(tg, "get_tool_gate_runtime", lambda: tg.ToolGateRuntime(_GateCfg()))
    service, transport = make_service(movement_confirm="required")
    before = len(transport.raw.lines)
    out = service.move_to_impl(20.0, 0.0)
    assert out["ok"] is False and out["error"] == "confirm_required"
    assert len(transport.raw.lines) == before, "未批准的机械命令不得下发"
    # 读操作不受确认门限制
    assert service.status_impl()["ok"] is True


def test_audit_only_mode_lets_write_tools_through(monkeypatch):
    from apiserver.event_bus import tool_gate as tg

    cfg = _GateCfg()
    cfg.audit_only = True
    monkeypatch.setattr(tg, "get_tool_gate_runtime", lambda: tg.ToolGateRuntime(cfg))
    service, _ = make_service(movement_confirm="required")
    assert service.move_to_impl(20.0, 0.0)["ok"] is True


def test_scope_denied_blocks_move(monkeypatch):
    from mcpserver import scope as scope_mod

    monkeypatch.setattr(scope_mod, "tool_visible",
                        lambda name, **kw: (False, "role_not_allowed"))
    service, transport = make_service(movement_confirm="required")
    before = len(transport.raw.lines)
    out = service.move_to_impl(20.0, 0.0)
    assert out["ok"] is False and out["error"] == "scope_denied"
    assert len(transport.raw.lines) == before


# ---------------------------------------------------------------------------
# 心跳兜底（W130-04 第三环的最小可用部分）
# ---------------------------------------------------------------------------


def test_watchdog_trips_stop_after_consecutive_misses():
    service, transport = make_service(max_miss=3, estop_on_watchdog=True)
    transport.inject_disconnect(99)          # 链路全断
    for _ in range(3):
        service.heartbeat()
    assert service._fault == "watchdog_timeout"
    assert service.fault_events and service.fault_events[-1]["kind"] == "watchdog"
    assert service.fault_events[-1]["misses"] >= 3
    # 兜底动作：停住（!）并在配置要求时卸载使能（M18）。
    # 链路全断时这些命令**自己就发不出去** → `actions` 为空、`attempted` 非空；
    # 这个差别正是「设备侧看门狗必须独立存在」的证据，不是缺陷。
    event = service.fault_events[-1]
    assert event["attempted"], "兜底至少要尝试过动作"
    assert any(a.startswith("stop") for a in event["attempted"])
    assert event["actions"] == [] and event["actions_failed"]


def test_watchdog_failsafe_actions_delivered_on_live_link():
    """链路活着但设备不回应探活时，兜底命令是能真正**送达设备**的。

    注意断言落在 `command_log`（设备收到什么）而不是 `actions`（主机收到回显）：
    `PTZTransport.send` 的契约是「一行命令换一行回显」，设备沉默时它按超时抛错，
    所以 `actions` 仍然是空的——但那不代表命令没送到。这正是
    「兜底是否生效」必须看设备侧证据、不能只看主机侧返回值的例子。
    """
    service, transport = make_service(max_miss=2, estop_on_watchdog=True)
    transport.set_silent(True)               # 设备沉默，但链路仍然可写
    for _ in range(2):
        service.heartbeat()
    event = service.fault_events[-1]
    assert event["misses"] >= 2
    log = transport.command_log
    assert "!" in log, "兜底必须先停住（进给保持）"
    assert "M18" in log, "estop_on_watchdog=True 时应卸载使能"
    assert event["attempted"] == ["stop", "home", "disable"]


def test_heartbeat_recovers_when_link_returns():
    service, transport = make_service(max_miss=2)
    assert service.heartbeat()["ok"] is True
    assert service.heartbeat()["misses"] == 0


# ---------------------------------------------------------------------------
# 急停 / 复位 / 记忆位
# ---------------------------------------------------------------------------


def test_estop_locks_and_reset_unlocks():
    service, transport = make_service(movement_confirm="required")
    out = service.estop_impl()
    assert out["ok"] is True and out["locked"] is True
    assert "M112" in transport.raw.lines
    # 锁机后运动被拒（不受确认门影响——先撞锁机闸）
    blocked = service.move_to_impl(10.0, 0.0)
    assert blocked["ok"] is False and blocked["error"] == "estop_locked"
    assert service.reset_impl()["ok"] is True
    assert service.snapshot()["locked"] is False


def test_memory_slots_round_trip():
    service, _ = make_service()
    assert service.memory_set_impl("north", 0.0, 30.0)["ok"] is True
    assert service.memory_list_impl()["slots"] == ["north"]
    got = service.memory_get_impl("north")
    assert got["ok"] and got["az"] == 0.0 and got["el"] == 30.0
    assert service.goto_memory_impl("north")["ok"] is True
    assert service.memory_get_impl("nope")["error"] == "slot_not_found"


# ---------------------------------------------------------------------------
# MCP 桥
# ---------------------------------------------------------------------------


def test_capability_card_and_tool_prefix():
    from mcpserver.ptz_service.tools import CAPABILITY, healthcheck

    for key in ("name", "displayName", "description", "version", "license", "vendor"):
        assert key in CAPABILITY
    assert CAPABILITY["name"] == CAPABILITY["_from_adapter"] == "ptz_service"
    assert healthcheck() is True
    names = sorted(PTZBridge._TOOLS)
    assert all(n.startswith("ptz_") for n in names), "工具名必须带 ptz_ 前缀"


def test_bridge_handoff_ok_and_error():
    service, _ = make_service()
    bridge = PTZBridge(service=service)
    payload = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "ptz_status"})))
    assert payload["status"] == "success" and payload["data"]["ok"] is True
    bad = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "可用" in bad["message"]
    wrong = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "ptz_move_to"})))
    assert wrong["status"] == "error" and "参数错误" in wrong["message"]


def test_bridge_memory_action_dispatch():
    service, _ = make_service()
    bridge = PTZBridge(service=service)
    assert bridge.ptz_memory(action="set", slot="east", az=90.0, el=10.0)["ok"] is True
    assert bridge.ptz_memory(action="list")["slots"] == ["east"]
    assert bridge.ptz_memory(action="goto", slot="east")["ok"] is True
    assert bridge.ptz_memory(action="bogus")["error"] == "bad_action"


def test_service_snapshot_shape():
    service, _ = make_service()
    snap = service.snapshot()
    assert set(snap) >= {"backend", "connected", "last_source", "locked", "fault",
                         "watchdog", "movement_confirm", "state", "memory_slots"}
    assert svc_mod.WRITE_TOOLS and "ptz_move_to" in svc_mod.WRITE_TOOLS
