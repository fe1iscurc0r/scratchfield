"""mcporter 懒加载验收（卷189-A1 遗留项：外部 MCP 服务此前在启动期即实例化）。

覆盖：懒加载下只登记冷表不实例化 / 关闭懒加载保持旧行为（写热表）/
冷表项（kind=mcporter）能正确转热 / 冷热清单口径一致 / 名称冲突跳过。
"""
from __future__ import annotations

import pytest

from mcpserver import mcp_registry as R
from mcpserver.mcporter_bridge import ExternalMCPAgent


class _FakeService:
    """最小 ExternalMCPService 替身（只需 name/config/manifest 三属性）。"""

    def __init__(self, name: str = "fake_ext_svc") -> None:
        self.name = name
        self.config = {"command": "echo", "args": ["hi"]}
        self.manifest = {"name": name, "source": "mcporter", "displayName": "Fake"}


@pytest.fixture(autouse=True)
def _isolate_registry():
    """备份/还原模块级注册表，避免测试间污染。"""
    snap = (dict(R.MANIFEST_CACHE), dict(R.MCP_REGISTRY), dict(R._COLD_TABLE),
            dict(R._COLD_HOT_FAILED))
    yield
    R.MANIFEST_CACHE.clear(); R.MANIFEST_CACHE.update(snap[0])
    R.MCP_REGISTRY.clear(); R.MCP_REGISTRY.update(snap[1])
    R._COLD_TABLE.clear(); R._COLD_TABLE.update(snap[2])
    R._COLD_HOT_FAILED.clear(); R._COLD_HOT_FAILED.update(snap[3])


def _patch_services(monkeypatch, services):
    monkeypatch.setattr(R, "load_external_mcp_services", lambda enabled_only=True: services)


def test_lazy_mode_registers_cold_only(monkeypatch):
    """默认（懒加载开）：只写冷表 + MANIFEST_CACHE，**不实例化**。"""
    monkeypatch.setenv("MCP_LAZY_REGISTRY", "1")
    svc = _FakeService("ext_lazy_a")
    _patch_services(monkeypatch, [svc])

    registered = R.register_external_mcp_agents()

    assert "ext_lazy_a" in registered
    assert R._COLD_TABLE["ext_lazy_a"]["kind"] == "mcporter"
    assert R._COLD_TABLE["ext_lazy_a"]["service_config"] == svc.config
    assert "ext_lazy_a" in R.MANIFEST_CACHE
    assert "ext_lazy_a" not in R.MCP_REGISTRY, "懒加载下不得实例化"
    assert R.all_service_names() == sorted(set(R.MCP_REGISTRY) | set(R._COLD_TABLE))
    assert "ext_lazy_a" in R.cold_service_names()
    assert R.is_hot("ext_lazy_a") is False


def test_non_lazy_mode_keeps_legacy_behaviour(monkeypatch):
    """MCP_LAZY_REGISTRY=0：回退旧行为（扫到即实例化、写热表）。"""
    monkeypatch.setenv("MCP_LAZY_REGISTRY", "0")
    svc = _FakeService("ext_hot_b")
    _patch_services(monkeypatch, [svc])

    registered = R.register_external_mcp_agents()

    assert "ext_hot_b" in registered
    assert "ext_hot_b" in R.MCP_REGISTRY, "关闭懒加载必须立即实例化"
    assert isinstance(R.MCP_REGISTRY["ext_hot_b"], ExternalMCPAgent)
    assert "ext_hot_b" not in R._COLD_TABLE


def test_cold_mcporter_entry_goes_hot(monkeypatch):
    """冷表 mcporter 项 → ensure_hot 走 ExternalMCPAgent 分支并转入热表。"""
    svc = _FakeService("ext_cold_c")
    R.MANIFEST_CACHE[svc.name] = svc.manifest
    R._COLD_TABLE[svc.name] = {"kind": "mcporter", "service_config": svc.config,
                               "manifest": svc.manifest}

    inst = R.ensure_hot(svc.name)

    assert isinstance(inst, ExternalMCPAgent)
    assert inst.service_name == svc.name and inst.config == svc.config
    assert R.is_hot(svc.name) is True
    assert svc.name not in R._COLD_TABLE, "转热后应移出冷表"
    assert R.ensure_hot(svc.name) is inst, "ensure_hot 幂等"


def test_manifest_kind_still_uses_create_agent_instance(monkeypatch):
    """manifest 型冷项仍走 create_agent_instance（改造不得影响既有路径）。"""
    sentinel = object()
    called: dict[str, object] = {}

    def _fake_create(manifest, agent_dir=""):
        called["manifest"] = manifest
        called["agent_dir"] = agent_dir
        return sentinel

    monkeypatch.setattr(R, "create_agent_instance", _fake_create)
    R.MANIFEST_CACHE["mani_d"] = {"name": "mani_d"}
    R._COLD_TABLE["mani_d"] = {"manifest": {"name": "mani_d"}, "agent_dir": "/x/y",
                               "manifest_path": "mani_d/agent-manifest.json"}

    inst = R.ensure_hot("mani_d")

    assert inst is sentinel
    assert called["agent_dir"] == "/x/y"
    assert R.is_hot("mani_d") is True


def test_lazy_registers_and_then_conflict_skipped(monkeypatch):
    """已登记同名服务 → 跳过（不覆盖既有登记）。"""
    monkeypatch.setenv("MCP_LAZY_REGISTRY", "1")
    svc = _FakeService("ext_dup_e")
    R.MANIFEST_CACHE["ext_dup_e"] = {"name": "ext_dup_e", "keep": True}
    _patch_services(monkeypatch, [svc])

    registered = R.register_external_mcp_agents()

    assert "ext_dup_e" not in registered
    assert R.MANIFEST_CACHE["ext_dup_e"].get("keep") is True, "既有登记不得被覆盖"
    assert "ext_dup_e" not in R._COLD_TABLE


def test_lazy_enabled_env_matrix(monkeypatch):
    for value, expected in [("1", True), ("", True), ("0", False),
                            ("false", False), ("no", False), ("off", False), ("yes", True)]:
        monkeypatch.setenv("MCP_LAZY_REGISTRY", value)
        assert R._lazy_enabled() is expected, value
