"""PTZ 云台执行器服务（卷130 W130-01 + W130-02 + W130-03 + W130-04）。

把天线云台/转台做成 Lumo 可调的工具——控制器与实体分离（借鉴 ros2_control
「hardware_interface 分离」的思路，自研实现不整抄）：

    tools.py       MCP 工具面（ptz_* 工具 + handoff），含三道闸门
    service.py     PTZService：命令收发、心跳兜底、急停锁机、记忆位
    transport.py   PTZTransport 抽象：SerialTransport / LoraBridgeTransport / SimPTZTransport
    state_store.py PTZStateStore：状态缓存 + 幂等判定
    watchdog.py    PTZWatchdog：W130-04 第三环（编排层通信心跳）
    audit.py       PTZAuditLog：W130-04 审计 JSONL（ts/source/cmd/result）
    scheduler.py   PTZScheduler：W130-03 任务编排（TLE 跟踪 / 扇扫循环 / 记忆位）
    tracking.py    W130-03 TLE 传播 + 观测站坐标（sgp4 优先，内置降级）

上游：卷129 `hardware/antenna-rotator/`（G 代码命令面）。
复用：卷119 W119-03 tool_gate（确认门）· 卷119 event_bus（fault 上报）·
卷124 W124-01 Scope（工具可见性）· 卷123（任务模型形态）。
"""
from __future__ import annotations

from .arbitration import (
    MODE_LAST_WINS,
    MODE_PRIORITY,
    SOURCE_LORA,
    SOURCE_SERIAL,
    ArbitrationResult,
    ChannelArbiter,
)
from .audit import RESULT_BLOCKED, RESULT_ERROR, RESULT_OK, PTZAuditLog
from .scheduler import (
    FAIL_HOLD,
    FAIL_HOME,
    TASK_GOTO_MEM,
    TASK_SCAN,
    TASK_TRACK,
    MemoryStore,
    MoveInstruction,
    PTZScheduler,
)
from .service import PTZService, check_scope, check_tool_gate
from .state_store import PTZStateStore
from .tools import CAPABILITY, PTZBridge, get_service, healthcheck
from .tracking import SiteLocation, Tle, TlePropagator, make_propagator, sgp4_available
from .transport import (
    LoopbackRadioLink,
    LoraBridgeTransport,
    PTZTransport,
    SerialTransport,
    SimPTZTransport,
    TransportError,
    TransportUnavailable,
    decode_frame,
    decode_reply,
    encode_command,
    encode_frame,
    encode_reply,
    open_transport,
)
from .watchdog import FAULT_LINK_DOWN, FAULT_WATCHDOG, PTZWatchdog

__all__ = [
    "PTZService", "PTZStateStore", "PTZBridge", "CAPABILITY", "get_service", "healthcheck",
    "check_scope", "check_tool_gate",
    "PTZTransport", "SerialTransport", "LoraBridgeTransport", "SimPTZTransport",
    "LoopbackRadioLink", "open_transport", "TransportError", "TransportUnavailable",
    "encode_frame", "decode_frame", "encode_command", "encode_reply", "decode_reply",
    "PTZWatchdog", "FAULT_WATCHDOG", "FAULT_LINK_DOWN",
    "PTZAuditLog", "RESULT_OK", "RESULT_ERROR", "RESULT_BLOCKED",
    "ChannelArbiter", "ArbitrationResult", "MODE_LAST_WINS", "MODE_PRIORITY",
    "SOURCE_SERIAL", "SOURCE_LORA",
    "PTZScheduler", "MoveInstruction", "MemoryStore",
    "TASK_TRACK", "TASK_SCAN", "TASK_GOTO_MEM", "FAIL_HOLD", "FAIL_HOME",
    "SiteLocation", "Tle", "TlePropagator", "make_propagator", "sgp4_available",
]
