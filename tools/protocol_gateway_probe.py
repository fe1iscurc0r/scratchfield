"""协议边缘终结最小探针（卷102 W102-03 · MIT 可参考，纯 Python 独立实现）。

模拟 iotgateway 的「设备协议 → 统一 MQTT 语义」转换骨架：
设备适配层（协议/寄存器映射）→ 转换层（原始值→物理量 JSON）→ 发布层（topic 映射）。

源结构对照（yjiong/iotgateway）：
- 适配接口/基础设备：internal/device/device.go:48 Devicer 接口、:59 Device 结构
- 具体协议设备：internal/device/ammeter/pmc340.go:19 PMC340
- MQTT 发布层：internal/handler/mqtt_handler.go:139 topic 拼接 ClientID/ServerID，data-up 语义
本探针不依赖 MQTT broker：用本地字典模拟寄存器与发布队列，只验证协议终结的数据语义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 寄存器区：模拟 Modbus RTU 从站的保持寄存器
MockRegisters = dict[int, int]


def modbus_read(registers: MockRegisters, addr: int, count: int) -> list[int]:
    """读取从 addr 起的 count 个寄存器；缺位补 0（RTU 读保持寄存器近似）。"""
    return [registers.get(addr + i, 0) for i in range(count)]


@dataclass
class DeviceAdapter:
    """协议设备适配（对照 device.go:59 Device：ID/协议/字段映射）。"""
    device_id: str
    protocol: str                # modbus-rtu / modbus-tcp / dlt645 ...
    base_addr: int
    fields: dict[str, tuple[int, float, str]]   # 字段名 -> (寄存器偏移, 缩放/单位换算系数, 单位)


@dataclass
class ProtocolGateway:
    """协议终结网关：读适配设备 → JSON 载荷 → MQTT topic。"""
    devices: dict[str, DeviceAdapter] = field(default_factory=dict)

    def register(self, adapter: DeviceAdapter) -> None:
        self.devices[adapter.device_id] = adapter

    def map_to_payload(self, adapter: DeviceAdapter, raw: list[int]) -> dict[str, Any]:
        """原始寄存器值 → 物理量 JSON（对照协议转换层）。"""
        payload: dict[str, Any] = {"device_id": adapter.device_id, "protocol": adapter.protocol}
        for name, (offset, scale, unit) in adapter.fields.items():
            payload[name] = {"value": round(raw[offset] * scale, 4), "unit": unit}
        return payload

    def read_and_publish(self, registers: MockRegisters, sink: list[tuple[str, dict]]) -> int:
        """读取全部已注册设备并发布；返回发布条数。"""
        for adapter in self.devices.values():
            raw = modbus_read(registers, adapter.base_addr, 16)
            payload = self.map_to_payload(adapter, raw)
            sink.append((self.topic_for(adapter.device_id), payload))
        return len(self.devices)

    @staticmethod
    def topic_for(device_id: str) -> str:
        """topic 规范：gateway/{device_id}/data（对照 mqtt_handler.go:139 的层级拼接）。"""
        return f"gateway/{device_id}/data"