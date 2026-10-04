"""卷189-A1 验收测试：manifest 懒加载（冷热分层）。

工单验收：冷启动只登记不实例化（冷表占位）、首次调用转热、开关可回退旧行为。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver import mcp_registry as reg  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    reg.clear_registry()
    yield
    reg.clear_registry()
    reg._COLD_TABLE.clear()
    reg._COLD_HOT_FAILED.clear()


def test_lazy_scan_does_not_instantiate():
    names = reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    assert len(names) >= 40
    # 懒加载：全部进冷表，热表为空（未实例化任何 agent）
    assert len(reg.MCP_REGISTRY) == 0
    assert len(reg._COLD_TABLE) == len(names)
    assert len(reg.MANIFEST_CACHE) == len(names)      # manifest 已缓存（轻量）


def test_eager_scan_instantiates(monkeypatch):
    names = reg.scan_and_register_mcp_agents("mcpserver", lazy=False)
    assert len(reg.MCP_REGISTRY) >= 1
    assert len(reg._COLD_TABLE) == 0
    assert len(reg.MCP_REGISTRY) <= len(names)        # 实例化失败的会少


def test_lazy_env_switch(monkeypatch):
    monkeypatch.setenv("MCP_LAZY_REGISTRY", "0")
    assert reg._lazy_enabled() is False
    monkeypatch.setenv("MCP_LAZY_REGISTRY", "1")
    assert reg._lazy_enabled() is True
    monkeypatch.delenv("MCP_LAZY_REGISTRY")
    assert reg._lazy_enabled() is True                # 缺省启用


def test_ensure_hot_promotes():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    assert reg.is_hot("academic") is False
    inst = reg.ensure_hot("academic")
    assert inst is not None
    assert reg.is_hot("academic") is True
    assert "academic" not in reg._COLD_TABLE          # 转热后移出冷表
    # 幂等：再次 ensure_hot 返回同一实例
    assert reg.ensure_hot("academic") is inst


def test_all_service_names_merges_hot_and_cold():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    total = len(reg.all_service_names())
    assert total == len(reg.MCP_REGISTRY) + len(reg._COLD_TABLE)
    reg.ensure_hot("academic")
    assert len(reg.all_service_names()) == total      # 转热不改总清单


def test_stats_report_hot_cold():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    st = reg.get_service_statistics()
    assert st["total_services"] == len(reg.all_service_names())
    assert st["hot_services"] == 0
    assert st["cold_services"] == st["total_services"]


def test_get_service_instance_triggers_hot():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    assert reg.get_service_instance("chembl") is not None
    assert reg.is_hot("chembl")


def test_ensure_hot_unknown_returns_none():
    assert reg.ensure_hot("no_such_service") is None


def test_service_source_for_breaker_exemption():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    assert reg.get_service_source("academic") == "manifest"   # 内置 → 不熔断
    reg.MANIFEST_CACHE["ext_svc"] = {"name": "ext_svc", "source": "mcporter"}
    assert reg.get_service_source("ext_svc") == "mcporter"


def test_registry_status_reports_lazy():
    reg.scan_and_register_mcp_agents("mcpserver", lazy=True)
    s = reg.get_registry_status()
    assert s["lazy_enabled"] is True
    assert s["cold_services"] >= 40
