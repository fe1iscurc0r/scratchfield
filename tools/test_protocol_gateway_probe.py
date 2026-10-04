"""protocol_gateway_probe 验收硬线（卷102 W102-03）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.protocol_gateway_probe import DeviceAdapter, ProtocolGateway, modbus_read  # noqa: E402


def test_modbus_register_read():
    """寄存器读取：起址+数量，缺位补 0。"""
    regs = {0: 2205, 1: 123, 2: 456}
    assert modbus_read(regs, 0, 3) == [2205, 123, 456]
    assert modbus_read(regs, 2, 4) == [456, 0, 0, 0]


def test_payload_mapping_with_scale():
    """寄存器→物理量：缩放换算与单位标注。"""
    adapter = DeviceAdapter(
        device_id="meter-01", protocol="modbus-rtu", base_addr=0,
        fields={"voltage": (0, 0.1, "V"), "current": (1, 0.001, "A")},
    )
    gw = ProtocolGateway()
    gw.register(adapter)
    payload = gw.map_to_payload(adapter, [2205, 1234])
    assert payload["voltage"] == {"value": 220.5, "unit": "V"}
    assert payload["current"] == {"value": 1.234, "unit": "A"}
    assert payload["device_id"] == "meter-01" and payload["protocol"] == "modbus-rtu"


def test_gateway_publish_topics():
    """多设备发布：topic 规范 gateway/{id}/data 且载荷一一对应。"""
    gw = ProtocolGateway()
    gw.register(DeviceAdapter("meter-01", "modbus-rtu", 0, {"v": (0, 0.1, "V")}))
    gw.register(DeviceAdapter("meter-02", "dlt645", 8, {"e": (0, 1.0, "kWh")}))
    regs = {0: 2205, 8: 37}
    sink: list[tuple[str, dict]] = []
    n = gw.read_and_publish(regs, sink)
    assert n == 2
    topics = [t for t, _ in sink]
    assert topics == ["gateway/meter-01/data", "gateway/meter-02/data"]
    assert sink[0][1]["v"]["value"] == 220.5
    assert sink[1][1]["e"] == {"value": 37.0, "unit": "kWh"}