"""ptz_service MCP 桥（卷130 W130-01）——ptz_* 工具面。

对齐 `docs/mcpserver-工具编写规范.md`：签名即 schema、工具面永不抛错（ok=False 降级）、
工具名带 `ptz_` 前缀；agent 目录型（entryPoint 见 `agent-manifest.json`）。

回显文本与固件逐字一致（`ok` / `error:limit` / `error:unknown`）——**这里不翻译**。
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .service import PTZService
from .transport import PTZTransport, open_transport

logger = logging.getLogger(__name__)

CAPABILITY: Dict[str, Any] = {
    "name": "ptz_service",
    "displayName": "PTZ 云台执行器服务（Lumo↔机械）",
    "description": ("把天线云台/转台做成 Lumo 可调的工具：定位、扇扫、回零、停止、状态；"
                    "含连接抽象（串口/LoRa 双后端）、确认门与 Scope 隔离、心跳兜底与审计。"),
    "version": "0.1.0",
    "license": "MIT",
    "vendor": "自研（上承卷129 hardware/antenna-rotator 命令面；参考 ros2_control/LeRobot 机制不整抄）",
    "_from_adapter": "ptz_service",
    "degradation_mode": "无串口/无 LoRa 时后端降级为 sim；工具仍存在，调用返回 ok=False 并附提示",
}

#: 服务单例（一个进程一份，独占链路）
_SERVICE_LOCK = threading.Lock()
_SERVICE: PTZService | None = None


def _transport_spec() -> str:
    """`PTZ_TRANSPORT`：`sim`（默认）/ `COM3` / `COM3@9600` / `/dev/ttyUSB0@115200`。"""
    return os.environ.get("PTZ_TRANSPORT", "sim").strip() or "sim"


def _safety_config() -> Dict[str, Any]:
    """读 `config.ptz_safety`（卷130 W130-04 §4）。配置不可用时给保守默认。

    这里刻意把「读配置」做成一个可单测的纯函数：配置来源变了（环境变量/文件/DB）
    只改这一处，服务构造逻辑不动。
    """
    try:
        from system.config import get_config  # noqa: PLC0415

        cfg = get_config().ptz_safety
        return {
            "watchdog_interval_s": float(getattr(cfg, "watchdog_interval_s", 5.0)),
            "max_miss": int(getattr(cfg, "max_miss", 3)),
            "estop_on_watchdog": bool(getattr(cfg, "estop_on_watchdog", True)),
            "home_on_watchdog": bool(getattr(cfg, "home_on_watchdog", False)),
            "disable_on_watchdog": bool(getattr(cfg, "disable_on_watchdog", True)),
            "movement_confirm": str(getattr(cfg, "movement_confirm", "required")),
            "default_timeout_s": float(getattr(cfg, "command_timeout_s", 2.0)),
            "audit_path": str(getattr(cfg, "audit_path", "") or "") or None,
            "estop_dual_channel": bool(getattr(cfg, "estop_dual_channel", True)),
            "tracking_period_s": float(getattr(cfg, "tracking_period_s", 3.0)),
            "tracking_source": str(getattr(cfg, "tracking_source", "sgp4")),
            "gps_source": str(getattr(cfg, "gps_source", "manual")),
            "gps_port": str(getattr(cfg, "gps_port", "") or ""),
            "site_lat_deg": float(getattr(cfg, "site_lat_deg", 39.9042)),
            "site_lon_deg": float(getattr(cfg, "site_lon_deg", 116.4074)),
            "site_alt_m": float(getattr(cfg, "site_alt_m", 50.0)),
            "memory_path": str(getattr(cfg, "memory_path", "") or "") or None,
            "track_fail_action": str(getattr(cfg, "track_fail_action", "hold")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ptz_service] 读 ptz_safety 配置失败，用默认: %s", exc)
        return {}


def _build_service() -> PTZService:
    """按配置装配服务：主通道 + （可配的）LoRa 第二通道 + 安全档 + 任务编排。"""
    safety = _safety_config()
    # 环境变量优先（现场快速覆盖，不改 config.json）
    if os.environ.get("PTZ_MOVEMENT_CONFIRM"):
        safety["movement_confirm"] = os.environ["PTZ_MOVEMENT_CONFIRM"]
    if os.environ.get("PTZ_TRACKING_SOURCE"):
        safety["tracking_source"] = os.environ["PTZ_TRACKING_SOURCE"]
    transport = open_transport(_transport_spec())
    secondary = None
    spec2 = os.environ.get("PTZ_TRANSPORT_LORA", "").strip()
    if spec2:
        try:
            secondary = open_transport(spec2)
        except Exception as exc:  # noqa: BLE001 - 第二通道起不来不该拖垮主通道
            logger.warning("[ptz_service] LoRa 第二通道不可用: %s", exc)
    # W130-03：记忆位落盘路径。留空则默认放到 <user_data>/ptz/memory.json
    if not safety.get("memory_path"):
        safety["memory_path"] = _default_memory_path()
    if not safety.get("audit_path"):
        safety["audit_path"] = None      # 让 PTZAuditLog 用自己的默认
    return PTZService(transport, secondary_transport=secondary, **safety)


def _default_memory_path() -> str:
    """记忆位默认路径 `<data_dir>/ptz/memory.json`（与审计同一 data 根）。

    **落盘位置要稳定**——记忆位是安装时标定的结果，路径随进程变等于每次都要重标。
    """
    try:
        from system.config import get_data_dir  # noqa: PLC0415

        return str(Path(get_data_dir()) / "ptz" / "memory.json")
    except Exception:  # noqa: BLE001
        return str(Path.cwd() / ".ptz" / "memory.json")


def get_service(reset: bool = False) -> PTZService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or reset:
            _SERVICE = _build_service()
        return _SERVICE


def healthcheck() -> bool:
    """恒 True：无硬件是降级不是不可用（规范 §4.3）。"""
    return True


class PTZBridge:
    """云台 agent 的 MCP 入口。"""

    def __init__(self, service: PTZService | None = None,
                 transport: PTZTransport | None = None):
        self._override = service or (PTZService(transport) if transport else None)

    def _svc(self) -> PTZService:
        return self._override or get_service()

    # ---- 工具 ----

    def ptz_move_to(self, az: float, el: float, speed: float | None = None,
                    timeout_s: float = 0.0, agent_id: str = "",
                    session_id: str = "") -> Dict[str, Any]:
        return _wrap(self._svc().move_to_impl(az, el, speed, timeout_s,
                                             agent_id=agent_id, session_id=session_id))

    def ptz_scan(self, start_az: float, end_az: float, step: float, dwell: float = 1.0,
                 speed: float | None = None, agent_id: str = "",
                 session_id: str = "") -> Dict[str, Any]:
        return _wrap(self._svc().scan_impl(start_az, end_az, step, dwell, speed,
                                          agent_id=agent_id, session_id=session_id))

    def ptz_home(self, timeout_s: float = 0.0, agent_id: str = "",
                 session_id: str = "") -> Dict[str, Any]:
        return _wrap(self._svc().home_impl(timeout_s, agent_id=agent_id, session_id=session_id))

    def ptz_status(self) -> Dict[str, Any]:
        return _wrap(self._svc().status_impl())

    def ptz_stop(self, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        return _wrap(self._svc().stop_impl(agent_id=agent_id, session_id=session_id))

    def ptz_estop(self) -> Dict[str, Any]:
        return _wrap(self._svc().estop_impl())

    def ptz_reset(self, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        return _wrap(self._svc().reset_impl(agent_id=agent_id, session_id=session_id))

    def ptz_heartbeat(self) -> Dict[str, Any]:
        return _wrap(self._svc().heartbeat())

    def ptz_watchdog(self, action: str = "tick") -> Dict[str, Any]:
        """看门狗（W130-04 §1）：`tick` 按节拍推进 / `status` 看快照 / `reset` 复位。

        定时器调 `tick` 即可——`due()` 会跳过未到点的拍，所以高频调用是安全的。
        """
        svc = self._svc()
        act = str(action or "tick").strip().lower()
        if act == "tick":
            return _wrap(svc.tick_watchdog())
        if act == "status":
            return _wrap({"ok": True, **svc.watchdog.snapshot()})
        if act == "reset":
            svc.watchdog.reset()
            return _wrap({"ok": True, **svc.watchdog.snapshot()})
        return {"ok": False, "source": "ptz_service", "error": "bad_action",
                "hint": "action 取 tick / status / reset"}

    def ptz_audit(self, limit: int = 50) -> Dict[str, Any]:
        """审计尾巴（W130-04 §2）：最近若干条命令/结果/fault。"""
        return _wrap(self._svc().audit_tail(limit))

    def ptz_lora(self, cmd: str, timeout_s: float = 0.0) -> Dict[str, Any]:
        """经 LoRa 第二通道（W130-02）发一条命令面指令。

        `cmd` 用卷129 命令面原文（`G1 X30 Y10` / `G28` / `!` / `M112`…）——
        **这里不做任何改写**：回显文本与固件逐字一致是跨层协议。
        """
        svc = self._svc()
        line = str(cmd or "").strip()
        if not line:
            return {"ok": False, "source": "ptz_service", "error": "empty_cmd",
                    "hint": "传命令面原文，例如 G1 X30 Y10 / G28 / ! / M112"}
        try:
            return _wrap(svc.send_via_secondary(line, timeout_s))
        except Exception as exc:  # noqa: BLE001 - 工具面永不抛错
            return {"ok": False, "source": "ptz_service", "error": type(exc).__name__,
                    "detail": str(exc), "hint": "检查帧长度（LoRa 上限 64B）与命令面语法"}

    def ptz_arbitration(self, action: str = "status", source: str = "") -> Dict[str, Any]:
        """双路仲裁（W130-02 §4）：`status` 看快照 / `release` 释放控制权。

        last-wins 语义下"释放"用于：遥控端主动让位、或空闲超时后清掉来源标记。
        """
        arb = self._svc().arbiter
        act = str(action or "status").strip().lower()
        if act == "status":
            return _wrap({"ok": True, **arb.snapshot()})
        if act == "release":
            arb.release(source)
            return _wrap({"ok": True, "released": True, **arb.snapshot()})
        if act == "release_if_idle":
            freed = arb.release_if_idle(30.0)
            return _wrap({"ok": True, "released": freed, **arb.snapshot()})
        return {"ok": False, "source": "ptz_service", "error": "bad_action",
                "hint": "action 取 status / release / release_if_idle"}

    def ptz_task(self, action: str = "list", type: str = "",
                 params: Dict[str, Any] | None = None,
                 schedule: Dict[str, Any] | None = None, task_id: str = "",
                 state: str = "", start: bool = True, agent_id: str = "",
                 session_id: str = "") -> Dict[str, Any]:
        """任务编排（W130-03）：`add` 建任务 / `list` 列任务 / `stop` 停任务 / `report` 误差报告。

        `type` 取 `track`（TLE 跟踪）/ `scan`（扇扫循环）/ `goto_mem`（走记忆位）。
        `params` 随类型不同：
        - track：`tle_line1`/`tle_line2`（必填）、`name`、`speed`、`max_prop_errors`
        - scan：`start_az`/`end_az`/`step`（必填）、`dwell`、`el`、`loops`（0=无限）
        - goto_mem：`slot`（必填）、`speed`
        `schedule`：`duration_s`（跑多久）/ `start_at`（ISO 8601 定时启动）
        """
        svc = self._svc()
        act = str(action or "list").strip().lower()
        try:
            if act == "add":
                return _wrap(svc.task_add_impl(type, params, schedule, start=start,
                                               task_id=task_id, agent_id=agent_id,
                                               session_id=session_id))
            if act == "list":
                return _wrap(svc.task_list_impl(state))
            if act == "stop":
                return _wrap(svc.task_stop_impl(task_id, agent_id=agent_id,
                                                session_id=session_id))
            if act == "report":
                return _wrap(svc.task_report_impl(task_id))
            if act == "tick":
                return _wrap(svc.tick_scheduler())
            if act == "remove":
                removed = svc.scheduler.remove_task(task_id)
                return _wrap({"ok": removed, "task_id": task_id, "removed": removed,
                              **({} if removed else {"error": "task_not_found"})})
        except Exception as exc:  # noqa: BLE001 - 工具面永不抛错
            return {"ok": False, "source": "ptz_service", "error": type(exc).__name__,
                    "detail": str(exc), "hint": "检查 type/params 是否符合该任务类型的要求"}
        return {"ok": False, "source": "ptz_service", "error": "bad_action",
                "hint": "action 取 add / list / stop / report / tick / remove"}

    def ptz_track_source(self) -> Dict[str, Any]:
        """跟踪数据源状态：sgp4 是否可用、观测站坐标、TLE 龄期告警。"""
        from .tracking import sgp4_available  # noqa: PLC0415

        svc = self._svc()
        snap = svc.scheduler.snapshot()
        return _wrap({"ok": True, "sgp4_available": sgp4_available(),
                      **snap,
                      **({} if sgp4_available() else {
                          "hint": "未装 sgp4（MIT 许可）：pip install sgp4 后可精确跟踪；"
                                  "临时自测可设 PTZ_TRACKING_SOURCE=simple（精度远低）"})})

    def ptz_memory(self, action: str = "list", slot: str = "", az: float = 0.0,
                   el: float = 0.0, agent_id: str = "", session_id: str = "") -> Dict[str, Any]:
        svc = self._svc()
        act = str(action or "list").strip().lower()
        if act == "list":
            return _wrap(svc.memory_list_impl())
        if act == "set":
            return _wrap(svc.memory_set_impl(slot, az, el, agent_id=agent_id,
                                            session_id=session_id))
        if act == "get":
            return _wrap(svc.memory_get_impl(slot))
        if act == "delete":
            return _wrap(svc.memory_delete_impl(slot))
        if act in ("goto", "recall"):
            return _wrap(svc.goto_memory_impl(slot, agent_id=agent_id, session_id=session_id))
        return {"ok": False, "source": "ptz_service", "error": "bad_action",
                "hint": "action 取 list / set / get / delete / goto"}

    def ptz_config(self) -> Dict[str, Any]:
        return _wrap({"ok": True, "snapshot": self._svc().snapshot()})

    # ---- handoff ----

    _TOOLS = {
        "ptz_move_to": "ptz_move_to",
        "ptz_scan": "ptz_scan",
        "ptz_home": "ptz_home",
        "ptz_status": "ptz_status",
        "ptz_stop": "ptz_stop",
        "ptz_estop": "ptz_estop",
        "ptz_reset": "ptz_reset",
        "ptz_heartbeat": "ptz_heartbeat",
        "ptz_watchdog": "ptz_watchdog",
        "ptz_audit": "ptz_audit",
        "ptz_lora": "ptz_lora",
        "ptz_arbitration": "ptz_arbitration",
        "ptz_task": "ptz_task",
        "ptz_track_source": "ptz_track_source",
        "ptz_memory": "ptz_memory",
        "ptz_config": "ptz_config",
    }

    async def handle_handoff(self, task: Dict[str, Any]) -> str:
        import asyncio
        import json

        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps({"status": "error",
                               "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                               "data": {}}, ensure_ascii=False)
        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_") and k not in ("tool_name", "agentType",
                                                                "service_name")}
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ptz_service] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error",
                               "message": f"{type(exc).__name__}: {exc}", "data": {}},
                              ensure_ascii=False)
        ok = bool(data.get("ok"))
        return json.dumps({"status": "success" if ok else "error",
                           "message": "ok" if ok else str(data.get("error") or "failed"),
                           "data": data}, ensure_ascii=False, default=str)


def _wrap(out: Dict[str, Any]) -> Dict[str, Any]:
    result = {"source": "ptz_service", "ok": bool(out.get("ok"))}
    for key, value in out.items():
        if key != "ok":
            result[key] = value
    if not result["ok"] and "hint" not in result:
        result["hint"] = "用 ptz_status 查设备状态；锁机需 ptz_reset"
    return result


__all__ = ["CAPABILITY", "PTZBridge", "get_service", "healthcheck"]
