"""设备注册客户端最小探针（卷102 W102-02 · Apache-2.0 可参考，纯 Python 独立实现）。

模拟 qbee-agent 的设备端注册/心跳/清单上报骨架：
bootstrap（注册）→ heartbeat（心跳/状态）→ inventory（清单）→ command（远程命令记录）。
服务端用本地 MockDeviceHub 字典代，不依赖网络。

源结构对照（qbee-io/qbee-agent）：
- app/agent/bootstrap.go:38 Bootstrap(ctx, cfg) 注册引导；:53 无 CA 证书禁止 bootstrap 的防守语义
- app/agent/api.go:121 checkIn 心跳上报到 device hub
- app/agent/inventory.go:30 doInventories 多项清单收集（system/ports/docker 分类）
本探针为最小语义骨架：设备 ID 稳定派生、心跳字段固定、状态经 hub 记录可查。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockDeviceHub:
    """本地模拟设备中心：注册表 + 心跳/清单/命令流水。"""
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    hb_records: list[tuple[str, dict]] = field(default_factory=list)
    inventory_records: list[tuple[str, dict]] = field(default_factory=list)
    command_records: list[tuple[str, dict]] = field(default_factory=list)

    def upsert(self, device_id: str, **fields: Any) -> None:
        entry = self.devices.setdefault(device_id, {"device_id": device_id, "status": "registered"})
        entry.update(fields)

    def get(self, device_id: str) -> dict | None:
        return self.devices.get(device_id)


class DeviceAgent:
    """设备端注册客户端（对照 qbee-agent 语义的 Python 最小实现）。"""

    def __init__(self, device_id: str | None = None, bootstrap_key: str = "", now=None):
        # 稳定派生设备 ID：显式传入优先，否则以 bootstrap_key+时间粗指纹（生产应换硬件指纹）
        self.device_id = device_id or self._derive_fingerprint(bootstrap_key)
        self.bootstrap_key = bootstrap_key
        self._now = now or time.time
        self.registered = False

    @staticmethod
    def _derive_fingerprint(bootstrap_key: str) -> str:
        digest = hashlib.sha256(f"dev:{bootstrap_key}:{time.time_ns()}".encode()).hexdigest()
        return f"dev-{digest[:12]}"

    def bootstrap(self, hub: MockDeviceHub) -> None:
        """注册引导：无凭证拒绝（对照 bootstrap.go:53 的 CA 防守语义）。"""
        if not self.bootstrap_key:
            raise ValueError("缺少 bootstrap 密钥，无法注册")
        hub.upsert(self.device_id, bootstrap_at=self._now())
        self.registered = True

    def heartbeat(self, hub: MockDeviceHub, cpu: float, mem: float, status: str = "ok") -> dict:
        """心跳上报（对照 api.go:121 checkIn）：状态字段 + 中心侧 last_seen 更新。"""
        payload = {
            "cpu_percent": float(cpu),
            "mem_percent": float(mem),
            "status": status,
            "ts": self._now(),
        }
        hub.hb_records.append((self.device_id, payload))
        hub.upsert(self.device_id, last_seen=payload["ts"], status=status)
        return payload

    def report_inventory(self, hub: MockDeviceHub, facts: dict[str, Any]) -> None:
        """清单上报（对照 inventory.go:30 多项收集语义的单类简化）。"""
        hub.inventory_records.append((self.device_id, facts))
        hub.upsert(self.device_id, inventory=dict(facts))

    def handle_command(self, hub: MockDeviceHub, cmd: dict[str, Any]) -> None:
        """远程命令记录（配置下发/OTA 语义的退化实现：仅登记执行结果）。"""
        record = {"cmd": cmd.get("name", ""), "params": cmd.get("params", {}), "ts": self._now()}
        hub.command_records.append((self.device_id, record))
        hub.upsert(self.device_id, last_cmd=record)