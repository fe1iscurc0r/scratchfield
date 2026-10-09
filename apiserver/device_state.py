"""设备状态感知层（卷131 W131-05）。

IC-705 / ESP32 / GPS 等硬件设备的状态进入 Lumo 的感知层。

设计（工单 W131-05）：
- DeviceStateStore：register / get_state / update_state / heartbeat（超时→offline）
- event_bus 接入：状态变更 emit lumo.device.state_changed（W131-06 补的 topic）
- 感知注入：system prompt 可选注入 {device_online: [...], device_offline: [...]}
- agentic_tool_loop 感知：run_agentic_loop 接收可选 device_context，
  工具执行前可查设备在线状态（如 GPS 离线不开 TLE 跟踪）
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from apiserver.event_bus import Topics, get_bus

# 心跳超时（秒）：超过未上报/心跳 → offline
DEFAULT_HEARTBEAT_TIMEOUT = 120.0


@dataclass
class DeviceState:
    """设备感知状态（只含感知所需字段，不含原始数据）。"""
    name: str
    online: bool = False
    last_seen: float = 0.0
    key_metrics: dict = field(default_factory=dict)  # 频率/功率/SWR/电池 等摘要
    offline_reason: str = ""


class DeviceStateStore:
    """设备状态注册表（进程级，线程安全）。"""

    def __init__(self, heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT):
        self._devices: dict[str, DeviceState] = {}
        self._factories: dict[str, Callable[[], dict]] = {}  # 设备适配器（可选）
        self._timeout = heartbeat_timeout
        self._lock = threading.Lock()

    # ---------- 注册 ----------
    def register(self, name: str, device: Any = None) -> None:
        """登记设备。device 可为适配器（暴露 get_metrics()），也可为 None（纯状态位）。"""
        with self._lock:
            if name not in self._devices:
                self._devices[name] = DeviceState(name=name)
                self._factories[name] = (
                    getattr(device, "get_metrics", None) if device else None)

    # ---------- 状态读写 ----------
    def update_state(self, name: str, metrics: dict) -> None:
        """设备上报状态（由设备路由或 agent 调用）；状态翻转 emit 事件。"""
        with self._lock:
            dev = self._devices.get(name)
            if dev is None:
                dev = self._devices[name] = DeviceState(name=name)
            was_online = dev.online
            dev.online = True
            dev.last_seen = time.time()
            # 只保留感知所需字段（数值/短字符串），原始大报文不进感知层
            dev.key_metrics = {
                k: v for k, v in metrics.items()
                if isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) <= 32)
            } if metrics else {}
            dev.offline_reason = ""
        if not was_online:
            self._emit(name, "online")

    def heartbeat(self, name: str) -> None:
        """设备心跳（不带指标，只刷在线时间）。"""
        with self._lock:
            dev = self._devices.get(name)
            if dev:
                dev.last_seen = time.time()
                if not dev.online:
                    dev.online = True
                    dev.offline_reason = ""
                    need_emit = True
                else:
                    need_emit = False
        if dev and need_emit:
            self._emit(name, "online")

    def get_state(self, name: str) -> DeviceState | None:
        """读状态（读时惰性判超时——无需后台线程，超时即 offline 并 emit）。"""
        with self._lock:
            dev = self._devices.get(name)
            if dev is None:
                return None
            if dev.online and (time.time() - dev.last_seen) > self._timeout:
                dev.online = False
                dev.offline_reason = "heartbeat_timeout"
                went_offline = True
            else:
                went_offline = False
        if went_offline:
            self._emit(name, "offline")
        return dev

    # ---------- 感知注入 ----------
    def perception_snapshot(self) -> dict:
        """给 system prompt / agentic loop 的感知快照（工单 W131-05.3）。"""
        online, offline = [], []
        for name in list(self._devices):
            st = self.get_state(name)
            if st is None:
                continue
            (online if st.online else offline).append(name)
        return {"device_online": online, "device_offline": offline}

    def list_devices(self) -> list[dict]:
        """全部设备状态（运维/测试用）。"""
        return [
            {"name": d.name, "online": d.online, "last_seen": d.last_seen,
             "key_metrics": d.key_metrics, "offline_reason": d.offline_reason}
            for d in (self.get_state(n) for n in list(self._devices)) if d
        ]

    # ---------- event_bus ----------
    def _emit(self, device_name: str, change: str) -> None:
        """状态变更 → lumo.device.state_changed（供感知层订阅；emit 失败不阻断状态更新）。"""
        try:
            bus = get_bus()
            bus.emit(Topics.DEVICE_STATE_CHANGED, {
                "device": device_name, "change": change, "ts": time.time()})
        except Exception:
            pass  # 总线未就绪（如单元测试无 bus）不阻断


# 进程级单例
_store: DeviceStateStore | None = None


_store_lock = threading.Lock()


def get_device_state_store() -> DeviceStateStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = DeviceStateStore()
    return _store
