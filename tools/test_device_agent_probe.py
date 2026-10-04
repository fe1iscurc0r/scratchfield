"""device_agent_probe 验收硬线（卷102 W102-02）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.device_agent_probe import DeviceAgent, MockDeviceHub  # noqa: E402


def test_bootstrap_requires_key_and_registers():
    """无密钥拒绝注册；有密钥注册并落中心表。"""
    hub = MockDeviceHub()
    agent = DeviceAgent(device_id="gw-01", bootstrap_key="")
    assert agent.device_id == "gw-01"
    with pytest.raises(ValueError, match="bootstrap"):
        agent.bootstrap(hub)
    assert hub.get("gw-01") is None

    agent2 = DeviceAgent(device_id="gw-02", bootstrap_key="secret-key")
    agent2.bootstrap(hub)
    assert agent2.registered is True
    entry = hub.get("gw-02")
    assert entry is not None and entry["status"] == "registered"
    assert "bootstrap_at" in entry


def test_heartbeat_updates_center():
    """心跳上报字段齐全且中心侧 last_seen/status 随之更新。"""
    hub = MockDeviceHub()
    agent = DeviceAgent(device_id="gw-01", bootstrap_key="k")
    agent.bootstrap(hub)
    payload = agent.heartbeat(hub, cpu=23.5, mem=61.2, status="ok")
    assert payload["cpu_percent"] == 23.5 and payload["mem_percent"] == 61.2
    assert payload["status"] == "ok" and "ts" in payload
    entry = hub.get("gw-01")
    assert entry["last_seen"] == payload["ts"] and entry["status"] == "ok"
    assert len(hub.hb_records) == 1


def test_inventory_and_command_records():
    """清单与远程命令记录均入中心台账。"""
    hub = MockDeviceHub()
    agent = DeviceAgent(device_id="gw-01", bootstrap_key="k")
    agent.bootstrap(hub)
    agent.report_inventory(hub, {"os": "linux", "arch": "aarch64", "lan": "10.0.0.9"})
    agent.handle_command(hub, {"name": "set_config", "params": {"interval": 30}})
    assert hub.inventory_records == [("gw-01", {"os": "linux", "arch": "aarch64", "lan": "10.0.0.9"})]
    entry = hub.get("gw-01")
    assert entry["inventory"]["arch"] == "aarch64"
    assert entry["last_cmd"]["cmd"] == "set_config"
    assert len(hub.command_records) == 1