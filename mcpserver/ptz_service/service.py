"""PTZ 编排服务（卷130 W130-01）——把云台做成 Lumo 可调的工具。

控制器与实体分离（借鉴 ros2_control 的 hardware_interface 思路，自研实现不整抄）：
本文件是控制器，`PTZTransport` 是硬件抽象，两者互不知道对方的实现细节。

三道闸门，缺一不可（工单 W130-01 §2）：

1. **Scope 隔离**（复用卷124 W124-01）：工具对角色可见才允许调用
2. **确认门**（复用卷119 W119-03 的 tool_gate waterfall）：机械命令是高危动作，
   `audit_only=False` 时敏感工具需批准才放行
3. **心跳兜底**（W130-04 第三环）：连续 N 次探活失败 → 自动 `ptz_stop` + fault 上报
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .arbitration import MODE_LAST_WINS, ChannelArbiter
from .audit import RESULT_BLOCKED, RESULT_ERROR, RESULT_OK, PTZAuditLog
from .rotator_core import protocol as cmd
from .scheduler import MemoryStore, MoveInstruction, PTZScheduler
from .state_store import PTZStateStore
from .tracking import SiteLocation
from .transport import PTZTransport, TransportError
from .watchdog import FAULT_WATCHDOG, PTZWatchdog

logger = logging.getLogger(__name__)

#: 写操作（高危动作）——统一走确认门；读操作不走
WRITE_TOOLS = ("ptz_move_to", "ptz_scan", "ptz_home", "ptz_stop", "ptz_estop", "ptz_reset")
READ_TOOLS = ("ptz_status", "ptz_memory_get")


class GateDecision:
    """确认门/Scope 的判定结果。"""

    def __init__(self, allowed: bool, error: str = "", detail: str = "", hint: str = ""):
        self.allowed = allowed
        self.error = error
        self.detail = detail
        self.hint = hint


def check_scope(tool_name: str, *, agent_id: str = "", session_id: str = "",
                role: str = "") -> GateDecision:
    """Scope 隔离（卷124）。模块不可用或未配置角色时**按默认可见**处理，不误伤。"""
    try:
        from .. import scope  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return GateDecision(True)
    try:
        visible, reason = scope.tool_visible(tool_name, role=role or None,
                                             agent_id=agent_id or None,
                                             session_id=session_id or None)
    except Exception:  # noqa: BLE001
        return GateDecision(True)
    if visible:
        return GateDecision(True)
    return GateDecision(False, "scope_denied",
                        f"工具 {tool_name} 对当前角色不可见（{reason}）",
                        "ptz 工具默认只对桌面端/管理员角色开放；让管理员在 scope 配置里加白名单")


def check_tool_gate(tool_name: str, args: Dict[str, Any]) -> GateDecision:
    """确认门 + 熔断门（卷119 W119-03）。

    `audit_only=True` 是灰度档：只记不拦。生产档下敏感工具需批准——
    这里返回 `confirm_required`，由上层会话走「用户确认」流程后重放同一条调用。
    """
    try:
        from apiserver.event_bus.tool_gate import get_tool_gate_runtime  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return GateDecision(True)      # 门不可用时放行（不因基础设施缺失而瘫掉操控）
    try:
        runtime = get_tool_gate_runtime()
        if not runtime.enabled:
            return GateDecision(True)
        hit, reason = runtime.is_sensitive(tool_name)
        if hit and not runtime.audit_only:
            runtime.audit({"phase": "ptz_confirm_required", "ts": time.time(),
                           "tool": tool_name, "args": args, "reason": reason})
            return GateDecision(False, "confirm_required", reason,
                                "机械命令需用户确认后重放；或把该工具加入 tool_gate.allowlist")
        tripped, streak = runtime.breaker_tripped(tool_name)
        if tripped and not runtime.audit_only:
            return GateDecision(False, "breaker_open", f"连续失败 {streak} 次已熔断",
                                "稍后再试；持续失败请先 ptz_status 查设备状态")
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ptz_service] tool_gate 判定异常，放行: %s", exc)
    return GateDecision(True)


def record_result(tool_name: str, ok: bool, duration_s: float = 0.0) -> None:
    """回填执行结果（熔断计数 + 审计 post）。失败静默，不影响操控回路。"""
    try:
        from apiserver.event_bus.tool_gate import record_tool_result  # noqa: PLC0415

        record_tool_result(tool_name, ok, duration_s=duration_s)
    except Exception:  # noqa: BLE001
        pass


class PTZService:
    """云台编排服务：控制器侧唯一入口。"""

    def __init__(self, transport: PTZTransport, *, clock=time.monotonic,
                 watchdog_interval_s: float = 5.0, max_miss: int = 3,
                 estop_on_watchdog: bool = True, default_timeout_s: float = 2.0,
                 movement_confirm: str = "required",
                 scope_role: str = "", sleep: Callable[[float], None] | None = None,
                 audit: PTZAuditLog | None = None, audit_enabled: bool = True,
                 audit_path: Any = None, home_on_watchdog: bool = False,
                 disable_on_watchdog: bool = True,
                 secondary_transport: PTZTransport | None = None,
                 estop_dual_channel: bool = True,
                 arbiter: ChannelArbiter | None = None,
                 arbitration_mode: str = MODE_LAST_WINS,
                 scheduler: Any | None = None,
                 tracking_period_s: float = 3.0,
                 tracking_source: str = "sgp4",
                 track_fail_action: str = "hold",
                 memory_path: Any = None,
                 site_lat_deg: float = 39.9042,
                 site_lon_deg: float = 116.4074,
                 site_alt_m: float = 50.0,
                 wall_clock: Callable[[], float] = time.time):
        self.transport = transport
        self.state = PTZStateStore(clock=clock)
        self.clock = clock
        self.wall_clock = wall_clock
        self.watchdog_interval_s = float(watchdog_interval_s)
        self.max_miss = int(max_miss)
        self.estop_on_watchdog = bool(estop_on_watchdog)
        self.home_on_watchdog = bool(home_on_watchdog or estop_on_watchdog)
        self.disable_on_watchdog = bool(disable_on_watchdog)
        self.default_timeout_s = float(default_timeout_s)
        self.movement_confirm = str(movement_confirm or "required")
        self.scope_role = scope_role
        self._sleep = sleep or time.sleep
        #: 第二通道（LoRa）。急停双通道：串口和无线**都认**——任一通则锁机。
        #: 只走一条路的急停在「那一条正好就是断的那条」时完全失效。
        self.secondary_transport = secondary_transport
        self.estop_dual_channel = bool(estop_dual_channel)

        self._lock = threading.RLock()
        self._inflight = False
        self._fault = ""
        self._locked = False          # estop 后的锁机标志（需 ptz_reset 解除）
        self._estop_channels: List[str] = []
        self._last_heartbeat = 0.0
        self._last_source = ""
        self._last_audit_source = ""  # 最近一次**发起**命令的来源（含 lora 第二通道）
        self.memory: Dict[str, Dict[str, float]] = {}
        self.fault_events: List[Dict[str, Any]] = []
        self.heartbeat_total = 0
        self.command_count = 0

        self.audit = audit or PTZAuditLog(audit_path, enabled=audit_enabled)
        #: 双路仲裁（W130-02 §4）：last-wins + last_source 供 `ptz_status` 显示。
        #: 时钟用 wall clock——仲裁判的是「谁的指令更晚」，这是跨进程的事件序，
        #: 不能用 monotonic（进程重启后归零，跨进程比较就没意义了）。
        self.arbiter = arbiter or ChannelArbiter(arbitration_mode, clock=wall_clock)
        #: 看门狗与手动 heartbeat 共用一条路径——**没有第二套探活实现**
        self.watchdog = PTZWatchdog(
            self._probe_once, interval_s=self.watchdog_interval_s, max_miss=self.max_miss,
            on_fault=self._on_watchdog_fault, stop=self._failsafe_stop,
            home=self._failsafe_home, disable=self._failsafe_disable,
            home_on_watchdog=self.home_on_watchdog,
            disable_on_watchdog=self.disable_on_watchdog, clock=clock)
        #: 任务编排（W130-03）。任务**不持有链路**——它们只产出「该发什么」，
        #: 由本服务经 `_exchange` 下发，因此照样过仲裁/审计/锁机/看门狗。
        #: 这是刻意的：编排层不能有特权通道。
        self.scheduler = scheduler or PTZScheduler(
            clock=wall_clock, wall_clock=lambda: datetime.fromtimestamp(
                wall_clock(), tz=timezone.utc),
            site=SiteLocation(site_lat_deg, site_lon_deg, site_alt_m),
            tracking_period_s=tracking_period_s, tracking_source=tracking_source,
            track_fail_action=track_fail_action,
            memory=MemoryStore(memory_path),
            arbiter=self.arbiter)

    @property
    def _misses(self) -> int:
        """兼容属性：连失计数**只有一个来源**（看门狗），不在这里再存一份。"""
        return self.watchdog.misses

    # ------------------------------------------------------------------
    # 内部：命令收发 / 心跳
    # ------------------------------------------------------------------

    def _apply_gates(self, tool_name: str, args: Dict[str, Any], *,
                     agent_id: str, session_id: str) -> Dict[str, Any] | None:
        if tool_name in WRITE_TOOLS and self.movement_confirm != "audit_only":
            decision = check_scope(tool_name, agent_id=agent_id, session_id=session_id,
                                   role=self.scope_role)
            if not decision.allowed:
                self._audit_event(tool=tool_name, cmd="", result=RESULT_BLOCKED, ok=False,
                                  error=decision.error, detail=decision.detail,
                                  phase="gate", args=args)
                return {"ok": False, "error": decision.error, "detail": decision.detail,
                        "hint": decision.hint}
            decision = check_tool_gate(tool_name, args)
            if not decision.allowed:
                self._audit_event(tool=tool_name, cmd="", result=RESULT_BLOCKED, ok=False,
                                  error=decision.error, detail=decision.detail,
                                  phase="gate", args=args)
                return {"ok": False, "error": decision.error, "detail": decision.detail,
                        "hint": decision.hint}
        return None

    def _exchange(self, line: str, timeout_s: float = 0.0, *,
                  allow_locked: bool = False, tool: str = "",
                  audit: bool = True, count_miss: bool = True,
                  source: str = "") -> Dict[str, Any]:
        """发一条命令并分类回显。

        `allow_locked`：只看状态与**解除锁机**的路径必须放行——否则急停锁机后
        `ptz_reset` 会被锁机闸自己挡住，永远解不开（死锁）。

        `count_miss`：链路失败时是否记一次失联。**看门狗探活必须传 False**
        ——那次失败由看门狗自己计（见 `_probe_once` 的注释）。

        `source`：本次的控制来源（serial/lora）。**只对写命令做仲裁**——
        状态查询不该抢控制权，否则一个高频心跳就能把遥控端的操作顶掉。
        """
        if self._locked and not allow_locked:
            if audit:
                self._audit_cmd(tool=tool, line=line, result=RESULT_BLOCKED,
                                ok=False, error="estop_locked",
                                detail="急停锁机中，命令未下发")
            return {"ok": False, "error": "estop_locked",
                    "hint": "急停已锁机；确认现场安全后调 ptz_reset 解除"}
        src = str(source or "").strip().lower()
        if src and src not in ("serial", "lora", "sim", "local"):
            src = ""
        if src:
            verdict = self.arbiter.claim(src, line)
            if not verdict.accepted:
                if audit:
                    self._audit_cmd(tool=tool, line=line, result=RESULT_BLOCKED, ok=False,
                                    error=verdict.reason, detail=verdict.detail)
                return {"ok": False, "error": verdict.reason, "detail": verdict.detail,
                        "last_source": self.arbiter.last_source,
                        "hint": "双路仲裁拒绝了这条指令（见 arbitration 快照）"}
            self._last_audit_source = src
        timeout = float(timeout_s or self.default_timeout_s)
        try:
            reply = self.transport.send(line, timeout)
        except TransportError as exc:
            if count_miss:
                self._note_miss("transport_error", str(exc))
            if audit:
                self._audit_cmd(tool=tool, line=line, result=RESULT_ERROR, ok=False,
                                error="link_down", detail=str(exc))
            return {"ok": False, "error": "link_down", "detail": str(exc),
                    "hint": "查链路（串口/LoRa）后重试；连续失败会触发心跳兜底"}
        self.command_count += 1
        self._last_heartbeat = self.clock()
        self.watchdog.note_ok()        # 一次成功交换即证明链路活着，清零看门狗连失
        kind, detail = cmd.classify(reply)
        # 状态行（M114/M115 的回显）**也是成功**——只认 `ok` 会把每次状态查询
        # 和心跳都判成失败，进而误触发兜底。这是实现时踩过的坑。
        ok = kind in (cmd.ReplyKind.OK, cmd.ReplyKind.STATUS)
        if kind is cmd.ReplyKind.STATUS:
            self.state.absorb(reply, source=self.transport.last_source)
        result: Dict[str, Any] = {"ok": ok, "reply": reply, "kind": kind.value,
                                  "last_source": self.transport.last_source}
        if not ok:
            result["error"] = detail or "unknown"
            result["hint"] = ("用 ptz_status 查设备状态；越限需改目标角，"
                              "锁死故障需 ptz_reset")
        if audit:
            self._audit_cmd(tool=tool, line=line,
                            result=RESULT_OK if ok else RESULT_ERROR, ok=ok,
                            error="" if ok else (detail or "unknown"),
                            detail=str(reply)[:120])
        return result

    # ------------------------------------------------------------------
    # 审计（W130-04 §2）
    # ------------------------------------------------------------------

    def _audit_cmd(self, *, tool: str, line: str, result: str, ok: bool,
                   error: str = "", detail: str = "") -> None:
        """记一条命令审计。**审计失败不阻断操控**（`PTZAuditLog` 内部已吞 OSError）。"""
        try:
            self.audit.record(cmd=line, source=self._audit_source(), result=result,
                              ok=ok, error=error, detail=detail, tool=tool)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ptz_service] 审计记录失败（不阻断）: %s", exc)

    def _audit_source(self) -> str:
        """发起方来源：优先第二通道（LoRa 遥控），否则主通道 backend。"""
        return self._last_audit_source or self.transport.last_source or self.transport.backend

    def _audit_event(self, **kwargs: Any) -> None:
        """记一条非命令事件（兜底/急停/闸门拦截）。"""
        try:
            kwargs.setdefault("source", self._audit_source())
            self.audit.record(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ptz_service] 事件审计失败（不阻断）: %s", exc)

    # ------------------------------------------------------------------
    # 看门狗（W130-04 §1）——探活与兜底动作都收敛在这里
    # ------------------------------------------------------------------

    def _probe_once(self) -> Dict[str, Any]:
        """一拍探活：走一次状态交换（与 `heartbeat()` 同一条路径）。

        **关键：探活失败不在 `_exchange` 里计数**（`count_miss=False`）。
        看门狗自己会在 `tick()` 里根据这次探活的结果记一次失联；
        如果 `_exchange` 也记一次，同一次失败就被算成两次
        ——`max_miss=3` 会在第二拍就兜底，而事件里报的 `misses` 是 6。
        这是实现时踩到的坑：**同一个量只能有一个所有者**。
        """
        out = self._exchange(cmd.status(), allow_locked=True,
                             tool="ptz_watchdog_probe", count_miss=False)
        if out.get("ok"):
            return {"ok": True, "status": self.state.snapshot()}
        return {"ok": False, "error": out.get("error") or "link_down",
                "detail": out.get("detail") or ""}

    def _failsafe_stop(self) -> None:
        """兜底①：进给保持（平滑停下、保持使能）。**不用 M112**——链路抖动不该锁故障。"""
        self.transport.send(cmd.feed_hold(), 1.0)

    def _failsafe_home(self) -> None:
        """兜底②：回零（可配；默认关——失联时自动运动本身是风险）。"""
        self.transport.send(cmd.home(), 2.0)

    def _failsafe_disable(self) -> None:
        """兜底③：卸载使能（M18），防止长时间保持导致的持续堵转发热。"""
        self.transport.send(cmd.enable(False), 1.0)

    def _on_watchdog_fault(self, event: Dict[str, Any]) -> None:
        """看门狗 fault → **停掉自动任务** + 本地登记 + 审计 + 进卷119 event_bus。

        为什么必须停自动任务：兜底执行的是 stop/home/disable，而编排里的扇扫/跟踪
        下一拍就会再发一条 `G1`。若不停，**兜底刚把云台停住，跟踪任务立刻把它开回去**——
        兜底等于失效。这个先后关系是硬约束，不是可配置项。
        """
        self._fault = FAULT_WATCHDOG
        stopped = self.scheduler.stop_all(FAULT_WATCHDOG)
        self.fault_events.append(dict(event))
        self._audit_event(cmd="", tool="ptz_watchdog", result=RESULT_ERROR, ok=False,
                          error=FAULT_WATCHDOG, detail=str(event.get("detail") or ""),
                          phase="fault", extra={"actions": event.get("actions"),
                                                "misses": event.get("misses"),
                                                "tasks_stopped": stopped.get("stopped")})
        self._emit_fault_event({**dict(event), "tasks_stopped": stopped.get("stopped", [])})

    def _note_miss(self, error: str, detail: str) -> None:
        """非看门狗路径（如直接调用）的连失计数。

        这里**委托给看门狗自己的计数**（`note_miss`），而不是服务里再存一份——
        两份计数一定会在某个时序上不一致（实现时踩过：`_exchange` 走这条路、
        看门狗走 `tick()` 那条路，两边各自加，兜底事件里的 `misses` 就成了错的数）。
        """
        self.watchdog.note_miss(error, detail)

    def _refresh_state(self, tool: str = "") -> None:
        """动作成功后刷一次缓存——否则 `ptz_status` 读到的是空快照。

        状态行回显也是成功（见 `_exchange`），失败静默：刷缓存不该影响动作结果。
        `tool` 传动作名而不是留空：否则这条内部刷新的审计会把上一条真实命令的
        `tool` 字段盖掉（审计里就会看到 tool="" 的记录，分不清是谁触发的）。
        """
        try:
            self._exchange(cmd.status(), tool=tool)
        except Exception:  # noqa: BLE001
            pass

    def _trip_watchdog(self, error: str, detail: str) -> Dict[str, Any]:
        """（保留的显式入口）不经过周期判定直接触发兜底——测试与手动诊断用。

        正常路径由 `tick_watchdog()` 按节拍驱动；这里只是把同一个实现暴露出来，
        **不另写一套兜底逻辑**。
        """
        self.watchdog._trigger(error, detail)      # noqa: SLF001
        return {"ok": False, "error": error, "detail": detail,
                "misses": self.watchdog.misses, "actions": "stop+"
                + ("home+" if self.home_on_watchdog else "")
                + ("disable" if self.disable_on_watchdog else "")}

    def _emit_fault_event(self, event: Dict[str, Any]) -> None:
        """进卷119 event_bus（不可用时只留本地记录，不影响兜底动作已生效的事实）。"""
        try:
            from mcpserver.workflow.event_bus import get_event_bus  # noqa: PLC0415

            get_event_bus().emit("ptz.fault", dict(event))
        except Exception:  # noqa: BLE001
            pass

    def poll(self) -> Dict[str, Any]:
        """推进后端内部状态（模拟器跑看门狗）。真机为空。"""
        self.transport.poll()
        return {"ok": True}

    def tick_watchdog(self) -> Dict[str, Any]:
        """按节拍推进看门狗（W130-04 §1）。

        调用方（定时器 / 主循环 / 测试假钟）高频调用即可，`due()` 会跳过未到点的拍。
        **不在这里 sleep**——节拍由注入的 clock 决定，测试才能不花真实时间。
        """
        self.transport.poll()          # 真机空转；模拟器借它跑内部看门狗
        out = self.watchdog.tick()
        if out.get("tripped"):
            self._fault = FAULT_WATCHDOG
        return {**out, "fault": self._fault, "watchdog": self.watchdog.snapshot()}

    def heartbeat(self) -> Dict[str, Any]:
        """手动一拍心跳（探活一次）。

        与看门狗共用 `_probe_once`——**没有第二套探活实现**；
        但手动心跳会无视 `interval_s` 立刻执行（诊断不该等节拍）。
        """
        self.heartbeat_total += 1
        out = self._probe_once()
        if not out.get("ok"):
            self._note_miss(str(out.get("error") or "link_down"), str(out.get("detail") or ""))
            return {**out, "misses": self.watchdog.misses, "fault": self._fault,
                    "tripped": self.watchdog.tripped}
        self.watchdog._note_ok()       # noqa: SLF001 - 同模块协作
        return {"ok": True, "misses": 0, "status": self.state.snapshot(),
                "last_source": self._last_source or self.transport.last_source}

    # ------------------------------------------------------------------
    # 任务编排（W130-03）：任务产出指令，**下发仍走本服务的普通命令路径**
    # ------------------------------------------------------------------

    def tick_scheduler(self, *, send: bool = True) -> Dict[str, Any]:
        """推进任务编排一拍照，并（默认）把产出的指令真正下发。

        **为什么编排不自己发命令**：本服务是链路的唯一持有者。任务若自己持有
        传输对象，就绕开了仲裁、审计、看门狗与锁机闸——那等于给自动任务开了
        一条特权通道，`ptz_estop` 的锁机也拦不住它。所以任务只产出
        `MoveInstruction`，下发统一在这里走 `move_to_impl` / `home_impl`。

        `locked` 会把指令丢掉：**急停锁机期间自动任务绝不能把云台开回去**。
        """
        if self._locked:
            self.scheduler.stop_all("estop_locked")
            return {"ok": True, "locked": True, "sent": 0, "instructions": [],
                    "hint": "急停锁机中，自动任务已全部停止；先 ptz_reset"}
        if self._fault:
            # 故障未清（例如看门狗兜底后）：**不推进任何自动任务**。
            # 兜底刚把机构停住，跟踪/扇扫若继续发 G1 就等于把兜底顶掉。
            self.scheduler.stop_all(self._fault)
            return {"ok": True, "locked": False, "fault": self._fault, "sent": 0,
                    "instructions": [],
                    "hint": f"设备处于故障态（{self._fault}），自动任务已停止；"
                            "清故障用 ptz_reset"}

        instructions = self.scheduler.tick(
            locked=self._locked, link_up=self.transport.connected,
            current=self.state.snapshot())
        results: List[Dict[str, Any]] = []
        if send:
            for inst in instructions:
                results.append(self._dispatch_instruction(inst))
        return {
            "ok": True, "locked": self._locked, "sent": len(results),
            "instructions": [i.as_dict() for i in instructions],
            "results": results, "scheduler": self.scheduler.snapshot(),
        }

    def _dispatch_instruction(self, inst: MoveInstruction) -> Dict[str, Any]:
        """把一条编排指令转成真实命令。走的是与工具面**完全同一条路**。"""
        if inst.kind == "home":
            out = self.home_impl()
        else:
            out = self.move_to_impl(inst.az, inst.el, inst.speed)
        return {**out, "task_id": inst.task_id, "reason": inst.reason,
                "instruction_kind": inst.kind}

    # ------------------------------------------------------------------
    # 工具（*impl：同步纯函数，可直接 import）
    # ------------------------------------------------------------------

    def move_to_impl(self, az: float, el: float, speed: float | None = None,
                     timeout_s: float = 0.0, *, agent_id: str = "",
                     session_id: str = "") -> Dict[str, Any]:
        gate = self._apply_gates("ptz_move_to", {"az": az, "el": el, "speed": speed},
                                 agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        if self.state.is_duplicate(az, el):
            return {"ok": True, "noop": True, "reason": "duplicate_target",
                    "target": [float(az), float(el)],
                    "detail": "目标与上次一致，未下发（避免无意义的机械往返）"}
        line = cmd.move(az, el, speed)
        out = self._exchange(line, timeout_s, tool="ptz_move_to",
                             source=self.transport.last_source)
        if out.get("ok"):
            self.state.note_target(az, el, source=self.transport.last_source)
            self._last_source = self.arbiter.last_source or self.transport.last_source
            self._refresh_state("ptz_move_to")
        return {**out, "noop": False, "target": [float(az), float(el)]}

    def home_impl(self, timeout_s: float = 0.0, *, agent_id: str = "",
                  session_id: str = "") -> Dict[str, Any]:
        gate = self._apply_gates("ptz_home", {}, agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        out = self._exchange(cmd.home(), timeout_s, tool="ptz_home",
                             source=self.transport.last_source)
        if out.get("ok"):
            self.state.clear_target()
            self._last_source = self.arbiter.last_source or self._last_source
        return out

    def stop_impl(self, *, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        gate = self._apply_gates("ptz_stop", {}, agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        out = self._exchange(cmd.feed_hold(), tool="ptz_stop",
                             source=self.transport.last_source)
        if out.get("ok"):
            self.state.clear_target()
            self._last_source = self.arbiter.last_source or self._last_source
        return out

    def status_impl(self) -> Dict[str, Any]:
        # 锁机时也要能看状态——诊断路径不受锁机闸限制；
        # 也**不参与仲裁**（状态查询不该抢控制权）
        out = self._exchange(cmd.status(), allow_locked=True, tool="ptz_status")
        if not out.get("ok"):
            return {**out, "cached": self.state.snapshot()}
        return {"ok": True, "reply": out.get("reply"), **self.state.snapshot(),
                "fault": self._fault, "locked": self._locked,
                # 工单 W130-02 §4：`ptz_status` 必须显示 last_source
                "last_source": self.arbiter.last_source or self.transport.last_source,
                "last_source_age_s": self.arbiter.last_age_s,
                "arbitration": self.arbiter.snapshot()}

    def scan_impl(self, start_az: float, end_az: float, step: float, dwell: float = 1.0,
                  speed: float | None = None, *, agent_id: str = "",
                  session_id: str = "") -> Dict[str, Any]:
        """扇扫：按步长走一遍（工单 W130-01 的 ptz_scan；**循环**任务见 W130-03）。"""
        gate = self._apply_gates("ptz_scan",
                                 {"start_az": start_az, "end_az": end_az, "step": step},
                                 agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        if float(step) <= 0:
            return {"ok": False, "error": "bad_step", "hint": "step 需为正数"}
        direction = 1.0 if float(end_az) >= float(start_az) else -1.0
        count = int(abs(float(end_az) - float(start_az)) / float(step)) + 1
        points: List[float] = []
        errors: List[Dict[str, Any]] = []
        for i in range(count):
            az = float(start_az) + direction * float(step) * i
            points.append(round(az, 3))
            # 扇扫只动方位、俯仰保持（工单语义：频谱/方向图扫描是水平面切片）
            out = self._exchange(cmd.move(az, 0.0, speed), tool="ptz_scan")
            if not out.get("ok"):
                errors.append({"az": round(az, 3), "error": out.get("error")})
                break
        self.state.note_target(points[-1] if points else float(end_az), 0.0,
                               source=self.transport.last_source)
        return {"ok": not errors, "points": points, "count": len(points),
                "errors": errors, "dwell_s": float(dwell),
                "last_source": self.transport.last_source}

    # ---- 记忆位（W130-03：落到本地 JSON，掉电不丢） ----

    def memory_set_impl(self, slot: str, az: float, el: float, *,
                        agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        gate = self._apply_gates("ptz_move_to", {"slot": slot}, agent_id=agent_id,
                                 session_id=session_id)
        if gate is not None:
            return gate
        key = str(slot or "").strip()
        if not key:
            return {"ok": False, "error": "bad_slot", "hint": "slot 不能为空"}
        try:
            saved = self.scheduler.memory.set(key, float(az), float(el))
        except ValueError as exc:
            return {"ok": False, "error": "bad_slot", "detail": str(exc)}
        # 保持"内存视图"同步：`snapshot()` 与自检都读 `self.memory`
        self.memory[key] = {"az": float(az), "el": float(el)}
        return {"ok": True, "slot": key, "saved": {"az": float(az), "el": float(el)},
                "persisted": saved.get("persisted", True)}

    def memory_get_impl(self, slot: str) -> Dict[str, Any]:
        key = str(slot or "").strip()
        found = self.scheduler.memory.get(key)
        if found is None:
            return {"ok": False, "error": "slot_not_found",
                    "hint": f"已存位：{', '.join(self.scheduler.memory.list_slots()) or '（空）'}"}
        return {"ok": True, "slot": key, "az": found["az"], "el": found["el"]}

    def memory_list_impl(self) -> Dict[str, Any]:
        slots = self.scheduler.memory.list_slots()
        return {"ok": True, "slots": slots, "count": len(slots),
                "path": str(self.scheduler.memory.path) if self.scheduler.memory.path else None}

    def memory_delete_impl(self, slot: str) -> Dict[str, Any]:
        key = str(slot or "").strip()
        existed = self.memory.pop(key, None) is not None
        removed = self.scheduler.memory.delete(key)
        if not (existed or removed):
            return {"ok": False, "error": "slot_not_found", "slot": key,
                    "hint": f"已存位：{', '.join(self.scheduler.memory.list_slots()) or '（空）'}"}
        return {"ok": True, "slot": key, "deleted": True}

    def goto_memory_impl(self, slot: str, speed: float | None = None, *,
                         agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        found = self.memory_get_impl(slot)
        if not found.get("ok"):
            return found
        return self.move_to_impl(found["az"], found["el"], speed,
                                 agent_id=agent_id, session_id=session_id)

    # ---- 急停 / 复位（W130-04） ----

    def estop_impl(self, *, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        """急停（W130-04 §3）：最高优先，**绕过确认门与锁机闸**，执行后锁机。

        两点设计取舍：

        1. **为什么绕过确认门**：紧急情况不能等批准。这一条是工单明写的例外，
           而且它只是「停下来」——最坏结果是云台停在原地，不是危险动作。
        2. **为什么双通道都发**（`estop_dual_channel`）：急停最怕的正是
           「你走的那条链路正好就是断的那条」。串口与 LoRa 各发一遍，
           **任一通则锁机**（只要有一路送达，机械就停住了）。
        """
        self._locked = True
        channels: List[str] = []
        errors: List[Dict[str, str]] = []

        def _fire(name: str, tr: PTZTransport | None) -> None:
            if tr is None:
                return
            try:
                reply = tr.send(cmd.estop(), self.default_timeout_s)
                channels.append(name)
                self._last_audit_source = tr.last_source or tr.backend
                self._audit_cmd(tool="ptz_estop", line=cmd.estop(), result=RESULT_OK,
                                ok=True, detail=f"channel={name} reply={reply}")
            except Exception as exc:  # noqa: BLE001 - 一路失败不阻断另一路（这正是双通道的意义）
                errors.append({"channel": name, "error": str(exc)})
                self._audit_cmd(tool="ptz_estop", line=cmd.estop(), result=RESULT_ERROR,
                                ok=False, error="channel_failed",
                                detail=f"channel={name} {exc}")

        _fire(self.transport.last_source or self.transport.backend, self.transport)
        if self.estop_dual_channel and self.secondary_transport is not None:
            _fire(self.secondary_transport.last_source or self.secondary_transport.backend,
                  self.secondary_transport)

        self.state.clear_target()
        self._estop_channels = channels
        if not channels:
            self._fault = "estop_link_down"
            self.fault_events.append({"ts": round(time.time(), 3), "kind": "estop",
                                      "error": "link_down", "detail": str(errors)})
            return {"ok": False, "error": "link_down", "detail": errors, "locked": True,
                    "channels": [],
                    "hint": "所有通道都没送达，急停帧没发出去——请就近断电"}
        return {"ok": True, "locked": True, "channels": channels,
                "channel_errors": errors,
                "detail": f"已锁机（通道: {', '.join(channels)}），需 ptz_reset 才能再动"}

    def reset_impl(self, *, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        """解除急停锁机 + 显式清故障（$X）+ 复位看门狗。"""
        gate = self._apply_gates("ptz_reset", {}, agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        # 解除锁机的路径必须放行，否则被自己的锁机闸挡住（死锁）
        out = self._exchange(cmd.clear_fault(), allow_locked=True, tool="ptz_reset")
        if out.get("ok"):
            self._locked = False
            self._fault = ""
            self._estop_channels = []
            # 看门狗的闩锁必须一起清：否则链路恢复后它仍然认为自己处于兜底态，
            # 第二次失联就不会再触发（这是"只触发一次"设计的必然副作用）。
            self.watchdog.reset()
        return {**out, "locked": self._locked}

    # ---- 诊断 ----

    def snapshot(self) -> Dict[str, Any]:
        return {
            "backend": self.transport.backend,
            "connected": self.transport.connected,
            "last_source": self.arbiter.last_source or self.transport.last_source,
            "locked": self._locked,
            "fault": self._fault,
            "misses": self.watchdog.misses,
            "commands": self.command_count,
            "heartbeats": self.heartbeat_total,
            "watchdog": self.watchdog.snapshot(),
            "arbitration": self.arbiter.snapshot(),
            "movement_confirm": self.movement_confirm,
            "state": self.state.snapshot(),
            "memory_slots": self.scheduler.memory.list_slots(),
            "fault_events": list(self.fault_events),
            "transport": self.transport.describe(),
            "estop_channels": list(self._estop_channels),
            "secondary_transport": (self.secondary_transport.describe()
                                    if self.secondary_transport is not None else None),
            "audit": self.audit.stats(),
            "scheduler": self.scheduler.snapshot(),
        }

    # ------------------------------------------------------------------
    # 第二通道（LoRa）：显式走无线发一条命令
    # ------------------------------------------------------------------

    def send_via_secondary(self, line: str, timeout_s: float = 0.0) -> Dict[str, Any]:
        """经第二通道（LoRa 桥）发一条命令，并以 `source="lora"` 参与仲裁。

        为什么要单独一个入口而不是自动选路：**选路是操作决策，不是技术细节**。
        自动"哪条通走哪条"会让现场分不清命令到底走了哪条路（排查时最关键的信息）。
        所以由调用方显式指定通道，`last_source` 如实记录。
        """
        if self.secondary_transport is None:
            return {"ok": False, "error": "no_secondary_channel",
                    "hint": "未配置第二通道（PTZ_TRANSPORT_LORA 或 config）"}
        verdict = self.arbiter.claim("lora", line)
        if not verdict.accepted:
            self._audit_cmd(tool="ptz_lora", line=line, result=RESULT_BLOCKED, ok=False,
                            error=verdict.reason, detail=verdict.detail)
            return {"ok": False, "error": verdict.reason, "detail": verdict.detail,
                    "last_source": self.arbiter.last_source}
        self._last_audit_source = "lora"
        timeout = float(timeout_s or self.default_timeout_s)
        try:
            reply = self.secondary_transport.send(line, timeout)
        except TransportError as exc:
            self._audit_cmd(tool="ptz_lora", line=line, result=RESULT_ERROR, ok=False,
                            error="link_down", detail=str(exc))
            return {"ok": False, "error": "link_down", "detail": str(exc),
                    "channel": "lora",
                    "hint": "LoRa 链路不通；主通道（串口）未受影响"}
        kind, detail = cmd.classify(reply)
        ok = kind in (cmd.ReplyKind.OK, cmd.ReplyKind.STATUS)
        self._audit_cmd(tool="ptz_lora", line=line, result=RESULT_OK if ok else RESULT_ERROR,
                        ok=ok, error="" if ok else (detail or "unknown"),
                        detail=str(reply)[:120])
        return {"ok": ok, "reply": reply, "kind": kind.value, "channel": "lora",
                "last_source": self.arbiter.last_source,
                **({"error": detail or "unknown", "hint": "用 ptz_status 查设备状态"}
                   if not ok else {})}

    # ------------------------------------------------------------------
    # 任务编排（W130-03）工具面
    # ------------------------------------------------------------------

    def task_add_impl(self, type: str, params: Dict[str, Any] | None = None,
                      schedule: Dict[str, Any] | None = None,
                      start: bool = True, task_id: str = "",
                      agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        """加一个任务（`track` / `scan` / `goto_mem`），默认立即启动。"""
        gate = self._apply_gates("ptz_scan", {"type": type, "params": params or {}},
                                 agent_id=agent_id, session_id=session_id)
        if gate is not None:
            return gate
        added = self.scheduler.add_task(type, params, schedule, task_id=task_id)
        if not added.get("ok"):
            return added
        self._audit_event(tool="ptz_task", cmd=f"add {type}", result=RESULT_OK, ok=True,
                          phase="task_add", args=params or {})
        out: Dict[str, Any] = {"ok": True, "task": added["task"]}
        if start:
            started = self.scheduler.start_task(added["task"]["task_id"])
            out = {**out, "started": bool(started.get("ok")),
                   "task": started.get("task", added["task"]),
                   "scheduler": self.scheduler.snapshot()}
            if not started.get("ok"):
                out["ok"] = False
                out["error"] = started.get("error", "start_failed")
                out["detail"] = started.get("detail", "")
                out["hint"] = started.get("hint", "")
        return out

    def task_list_impl(self, state: str = "") -> Dict[str, Any]:
        tasks = self.scheduler.list_tasks(state)
        return {"ok": True, "tasks": tasks, "count": len(tasks),
                "scheduler": self.scheduler.snapshot()}

    def task_stop_impl(self, task_id: str = "", *, agent_id: str = "",
                       session_id: str = "") -> Dict[str, Any]:
        """停一个任务；`task_id` 为空则停全部。"""
        gate = self._apply_gates("ptz_stop", {"task_id": task_id}, agent_id=agent_id,
                                 session_id=session_id)
        if gate is not None:
            return gate
        if not str(task_id or "").strip():
            out = self.scheduler.stop_all("stopped_by_call")
            self._audit_event(tool="ptz_task", cmd="stop all", result=RESULT_OK, ok=True,
                              phase="task_stop")
            return {**out, "scheduler": self.scheduler.snapshot()}
        out = self.scheduler.stop_task(task_id)
        self._audit_event(tool="ptz_task", cmd=f"stop {task_id}",
                          result=RESULT_OK if out.get("ok") else RESULT_ERROR,
                          ok=bool(out.get("ok")), error="" if out.get("ok") else out.get("error", ""),
                          phase="task_stop")
        return {**out, "scheduler": self.scheduler.snapshot()}

    def task_report_impl(self, task_id: str) -> Dict[str, Any]:
        """跟踪误差报告（工单要求「跟踪误差上报」）。"""
        return self.scheduler.report(task_id)

    def audit_tail(self, limit: int = 50) -> Dict[str, Any]:
        """最近若干条审计（内存，不读盘）。"""
        return {"ok": True, "entries": self.audit.tail(limit),
                "count": len(self.audit.tail(limit)), "path": str(self.audit.path)}


__all__ = ["PTZService", "GateDecision", "check_scope", "check_tool_gate", "record_result",
           "WRITE_TOOLS", "READ_TOOLS"]
